"""
Ingestion Agent — Processes uploaded PDFs and public URLs.
Extracts content, chunks it, embeds, and stores in the vector DB.
Images/diagrams in PDFs are described via the vision model.
"""

import logging
import os

from ..core.event_bus import EventBus
from ..core.llm_client import get_embeddings_batch, describe_image
from ..core.vector_store import VectorStore
from ..core.chunker import chunk_text
from ..core.pdf_processor import extract_pdf, describe_pdf_images
from ..tools.web_scraper import scrape_url

from ..config import COLLECTION_INGESTED_DOCS, UPLOADS_DIR

logger = logging.getLogger(__name__)


async def ingest_pdf(
    file_path: str,
    filename: str,
    event_bus: EventBus,
    vector_store: VectorStore,
    conversation_id: str = "",
) -> dict:
    """
    Ingest a PDF file: extract text, tables, images → embed → store.

    Returns:
        {
            "success": bool,
            "filename": str,
            "pages": int,
            "chunks_stored": int,
            "images_processed": int,
            "tables_found": int,
        }
    """
    await event_bus.agent_start("ingestion", f"Processing PDF: {filename}...")

    try:
        # Step 1: Extract PDF content
        await event_bus.agent_progress(
            "ingestion", "Extracting text, tables, and images from PDF..."
        )
        pdf_content = extract_pdf(file_path)

        await event_bus.agent_progress(
            "ingestion",
            f"Extracted {pdf_content.total_pages} pages, "
            f"{len(pdf_content.all_images)} images, "
            f"{len(pdf_content.all_tables)} tables",
        )

        # Step 2: Describe images using vision model
        if pdf_content.all_images:
            await event_bus.agent_progress(
                "ingestion",
                f"Describing {len(pdf_content.all_images)} images with vision model...",
            )
            pdf_content = await describe_pdf_images(pdf_content, describe_image)

        # Step 3: Build chunks from all content types
        all_texts = []
        all_metas = []

        # Text chunks
        text_chunks = chunk_text(pdf_content.full_text)
        for i, chunk in enumerate(text_chunks):
            all_texts.append(chunk)
            all_metas.append({
                "filename": filename,
                "content_type": "text",
                "page_number": -1,  # hard to map back after full text chunking
                "chunk_index": i,
                "conversation_id": conversation_id,
                "source": f"pdf:{filename}",
            })

        # Table chunks
        for table in pdf_content.all_tables:
            all_texts.append(
                f"[Table from page {table.page_number} of {filename}]\n{table.markdown}"
            )
            all_metas.append({
                "filename": filename,
                "content_type": "table",
                "page_number": table.page_number,
                "conversation_id": conversation_id,
                "source": f"pdf:{filename}",
            })

        # Image descriptions (with base64 stored in metadata for rendering)
        for img in pdf_content.all_images:
            if img.description:
                all_texts.append(
                    f"[Image/Diagram from page {img.page_number} of {filename}]\n"
                    f"{img.description}"
                )
                all_metas.append({
                    "filename": filename,
                    "content_type": "image",
                    "page_number": img.page_number,
                    "image_b64": img.image_b64[:500],  # store truncated ref
                    "image_width": img.width,
                    "image_height": img.height,
                    "conversation_id": conversation_id,
                    "source": f"pdf:{filename}",
                })

        # Step 4: Embed and store
        if all_texts:
            await event_bus.agent_progress(
                "ingestion",
                f"Embedding {len(all_texts)} chunks...",
            )
            embeddings = await get_embeddings_batch(all_texts)
            vector_store.add_documents(
                collection_name=COLLECTION_INGESTED_DOCS,
                texts=all_texts,
                embeddings=embeddings,
                metadatas=all_metas,
            )

        # Save full images to disk for later retrieval
        for img in pdf_content.all_images:
            img_path = os.path.join(
                UPLOADS_DIR,
                f"{filename}_page{img.page_number}_{img.width}x{img.height}.png",
            )
            with open(img_path, "wb") as f:
                f.write(img.image_bytes)

        await event_bus.agent_result(
            "ingestion",
            f"PDF ingested: {len(all_texts)} chunks stored from {pdf_content.total_pages} pages",
            chunks_stored=len(all_texts),
            pages=pdf_content.total_pages,
            images=len(pdf_content.all_images),
            tables=len(pdf_content.all_tables),
        )

        return {
            "success": True,
            "filename": filename,
            "pages": pdf_content.total_pages,
            "chunks_stored": len(all_texts),
            "images_processed": len(pdf_content.all_images),
            "tables_found": len(pdf_content.all_tables),
        }

    except Exception as e:
        logger.error(f"PDF ingestion error for {filename}: {e}")
        await event_bus.agent_error("ingestion", f"Error processing PDF: {e}")
        return {
            "success": False,
            "filename": filename,
            "pages": 0,
            "chunks_stored": 0,
            "images_processed": 0,
            "tables_found": 0,
            "error": str(e),
        }


async def ingest_url(
    url: str,
    event_bus: EventBus,
    vector_store: VectorStore,
    conversation_id: str = "",
) -> dict:
    """
    Ingest content from a public URL: scrape → chunk → embed → store.
    """
    await event_bus.agent_start("ingestion", f"Fetching content from URL: {url}")

    try:
        scraped = await scrape_url(url)

        if not scraped["success"] or not scraped["content"]:
            await event_bus.agent_error(
                "ingestion",
                f"Failed to fetch URL: {scraped.get('error', 'No content')}",
            )
            return {"success": False, "url": url, "chunks_stored": 0}

        await event_bus.agent_progress(
            "ingestion",
            f"Extracted {len(scraped['content'])} chars from '{scraped['title']}'",
        )

        # Chunk the content
        chunks = chunk_text(scraped["content"])
        metas = [
            {
                "url": url,
                "title": scraped["title"][:200],
                "content_type": "web_page",
                "chunk_index": i,
                "conversation_id": conversation_id,
                "source": f"url:{url}",
            }
            for i in range(len(chunks))
        ]

        # Embed and store
        if chunks:
            embeddings = await get_embeddings_batch(chunks)
            vector_store.add_documents(
                collection_name=COLLECTION_INGESTED_DOCS,
                texts=chunks,
                embeddings=embeddings,
                metadatas=metas,
            )

        await event_bus.agent_result(
            "ingestion",
            f"URL ingested: {len(chunks)} chunks stored from '{scraped['title']}'",
            chunks_stored=len(chunks),
            title=scraped["title"],
        )

        return {
            "success": True,
            "url": url,
            "title": scraped["title"],
            "chunks_stored": len(chunks),
        }

    except Exception as e:
        logger.error(f"URL ingestion error for {url}: {e}")
        await event_bus.agent_error("ingestion", f"Error: {e}")
        return {"success": False, "url": url, "chunks_stored": 0, "error": str(e)}
