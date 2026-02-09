"""
Deep Research Agent — FastAPI Backend
Provides REST API + SSE streaming for the React frontend.
"""

import json
import logging
import os
import shutil
import uuid

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel

from .config import (
    API_HOST,
    API_PORT,
    CORS_ORIGINS,
    UPLOADS_DIR,
    MAX_CONVERSATION_HISTORY,
)
from .core.event_bus import EventBus
from .core.vector_store import VectorStore
from .core import session_manager
from .core.llm_client import chat, check_health
from .agents import orchestrator

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# ─── App Setup ───────────────────────────────────────────────
app = FastAPI(
    title="Deep Research Agent API",
    description="Multi-agent deep research platform with local Ollama inference",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Singleton vector store
vector_store = VectorStore()


# ─── Request/Response Models ────────────────────────────────

class ChatRequest(BaseModel):
    conversation_id: str
    message: str


class ConversationCreate(BaseModel):
    title: str = "New Conversation"


class ConversationUpdate(BaseModel):
    title: str


# ─── Health ──────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    provider_status = await check_health()
    db_stats = vector_store.get_stats()
    return {
        "status": "ok",
        **provider_status,
        "vector_db": db_stats,
    }


# ─── Conversations CRUD ─────────────────────────────────────

@app.get("/api/conversations")
async def list_conversations():
    return session_manager.list_conversations()


@app.post("/api/conversations")
async def create_conversation(body: ConversationCreate):
    return session_manager.create_conversation(body.title)


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str):
    conv = session_manager.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conv


@app.put("/api/conversations/{conv_id}")
async def update_conversation(conv_id: str, body: ConversationUpdate):
    session_manager.update_conversation_title(conv_id, body.title)
    return {"status": "updated"}


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str):
    session_manager.delete_conversation(conv_id)
    return {"status": "deleted"}


# ─── Messages ───────────────────────────────────────────────

@app.get("/api/conversations/{conv_id}/messages")
async def get_messages(conv_id: str):
    return session_manager.get_messages(conv_id)


# ─── Chat (SSE Streaming) ───────────────────────────────────

@app.post("/api/chat")
async def chat_endpoint(body: ChatRequest):
    """
    Main chat endpoint. Returns SSE stream with:
      - Agent trace events (type: agent_start, agent_progress, agent_result, plan_step)
      - Streaming tokens (type: stream_token)
      - Stream end (type: stream_end)
    """
    conv_id = body.conversation_id
    message = body.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Ensure conversation exists
    conv = session_manager.get_conversation(conv_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Save user message
    session_manager.add_message(conv_id, "user", message)

    # Auto-generate title from first message
    if conv["title"] == "New Conversation":
        try:
            title = await chat(
                messages=[
                    {
                        "role": "system",
                        "content": "Generate a very short title (max 6 words) for a conversation that starts with this message. Reply with ONLY the title, no quotes.",
                    },
                    {"role": "user", "content": message},
                ],
                temperature=0.3,
            )
            title = title.strip().strip('"').strip("'")[:80]
            session_manager.update_conversation_title(conv_id, title)
        except Exception:
            pass

    # Get conversation history
    history = session_manager.get_messages(conv_id, limit=MAX_CONVERSATION_HISTORY)
    conv_history = [
        {"role": m["role"], "content": m["content"]}
        for m in history[:-1]  # exclude the message we just added
    ]

    async def event_stream():
        event_bus = EventBus()
        full_response = ""

        try:
            async for token in orchestrator.handle_query(
                query=message,
                event_bus=event_bus,
                vector_store=vector_store,
                conversation_history=conv_history,
                conversation_id=conv_id,
            ):
                full_response += token

            # Drain any remaining events from the bus
            event_bus.close()

            # Build the complete trace and send it
            trace = event_bus.get_trace()

            # Send all trace events
            for event in trace:
                if event["event_type"] not in ("stream_token", "stream_end"):
                    yield f"data: {json.dumps(event)}\n\n"

            # Send tokens
            yield f"data: {json.dumps({'type': 'full_response', 'message': full_response})}\n\n"

            # Send done signal
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

            # Save assistant message with trace
            sources = []
            for e in trace:
                if e.get("agent_name") == "synthesis":
                    sources = e.get("data", {}).get("sources", [])
                    break

            session_manager.add_message(
                conv_id,
                "assistant",
                full_response,
                sources=sources,
                agent_trace=trace,
            )

        except Exception as e:
            logger.error(f"Chat error: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ─── PDF Upload ──────────────────────────────────────────────

@app.post("/api/upload")
async def upload_file(
    file: UploadFile = File(...),
    conversation_id: str = Form(...),
):
    """Upload a PDF file for ingestion into the vector DB."""
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=400, detail="Only PDF files are supported"
        )

    conv = session_manager.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Save file to disk
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOADS_DIR, f"{file_id}_{file.filename}")

    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Process via ingestion agent
    event_bus = EventBus()

    result = await orchestrator.handle_pdf_upload(
        file_path=file_path,
        filename=file.filename,
        event_bus=event_bus,
        vector_store=vector_store,
        conversation_id=conversation_id,
    )

    # Record upload
    if result["success"]:
        session_manager.add_upload(
            conversation_id=conversation_id,
            filename=file.filename,
            file_type="pdf",
            collection_name="ingested_documents",
            doc_count=result["chunks_stored"],
        )

        session_manager.add_message(
            conversation_id,
            "assistant",
            f"📄 **PDF Uploaded: {file.filename}**\n\n"
            f"- **Pages:** {result['pages']}\n"
            f"- **Text chunks stored:** {result['chunks_stored']}\n"
            f"- **Images/diagrams processed:** {result['images_processed']}\n"
            f"- **Tables extracted:** {result['tables_found']}\n\n"
            f"You can now ask me questions about this document.",
            agent_trace=event_bus.get_trace(),
        )

    return {
        "success": result["success"],
        "filename": file.filename,
        "pages": result.get("pages", 0),
        "chunks_stored": result.get("chunks_stored", 0),
        "images_processed": result.get("images_processed", 0),
        "tables_found": result.get("tables_found", 0),
        "error": result.get("error"),
        "trace": event_bus.get_trace(),
    }


# ─── Uploads ─────────────────────────────────────────────────

@app.get("/api/conversations/{conv_id}/uploads")
async def get_uploads(conv_id: str):
    return session_manager.get_uploads(conv_id)


# ─── Vector DB Stats ────────────────────────────────────────

@app.get("/api/vector-db/stats")
async def get_vector_stats():
    return vector_store.get_stats()


# ─── Entrypoint ──────────────────────────────────────────────

def start():
    """Entrypoint for `deep-research` CLI command."""
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=API_HOST,
        port=API_PORT,
        reload=True,
    )


if __name__ == "__main__":
    start()
