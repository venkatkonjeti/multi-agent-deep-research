"""
Session Manager — SQLite-backed multi-conversation tracking.
Stores conversations, messages, uploads, and agent traces.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import time
import uuid

from ..config import SQLITE_DB_PATH, CONVERSATION_TITLE_MAX_LENGTH

logger = logging.getLogger(__name__)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(SQLITE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist."""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL DEFAULT 'New Conversation',
            created_at REAL NOT NULL,
            updated_at REAL NOT NULL
        );

        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
            content TEXT NOT NULL,
            sources TEXT DEFAULT '[]',
            agent_trace TEXT DEFAULT '[]',
            timestamp REAL NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS uploads (
            id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            file_type TEXT NOT NULL DEFAULT 'pdf',
            collection_name TEXT,
            doc_count INTEGER DEFAULT 0,
            timestamp REAL NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, timestamp);
        CREATE INDEX IF NOT EXISTS idx_uploads_conv ON uploads(conversation_id);
    """)
    conn.commit()
    conn.close()
    logger.info("Database initialized")


# ─── Conversations ───────────────────────────────────────────

def create_conversation(title: str = "New Conversation") -> dict:
    """Create a new conversation and return it."""
    conv_id = str(uuid.uuid4())
    now = time.time()
    title = title[:CONVERSATION_TITLE_MAX_LENGTH]

    conn = _get_conn()
    conn.execute(
        "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
        (conv_id, title, now, now),
    )
    conn.commit()
    conn.close()
    return {"id": conv_id, "title": title, "created_at": now, "updated_at": now}


def list_conversations() -> list[dict]:
    """List all conversations, most recent first."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM conversations ORDER BY updated_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_conversation(conv_id: str) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM conversations WHERE id = ?", (conv_id,)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def update_conversation_title(conv_id: str, title: str) -> None:
    title = title[:CONVERSATION_TITLE_MAX_LENGTH]
    conn = _get_conn()
    conn.execute(
        "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
        (title, time.time(), conv_id),
    )
    conn.commit()
    conn.close()


def delete_conversation(conv_id: str) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
    conn.commit()
    conn.close()


def touch_conversation(conv_id: str) -> None:
    """Update the updated_at timestamp."""
    conn = _get_conn()
    conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (time.time(), conv_id),
    )
    conn.commit()
    conn.close()


# ─── Messages ────────────────────────────────────────────────

def add_message(
    conversation_id: str,
    role: str,
    content: str,
    sources: list | None = None,
    agent_trace: list | None = None,
) -> dict:
    """Add a message to a conversation."""
    msg_id = str(uuid.uuid4())
    now = time.time()
    conn = _get_conn()
    conn.execute(
        """INSERT INTO messages (id, conversation_id, role, content, sources, agent_trace, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (
            msg_id,
            conversation_id,
            role,
            content,
            json.dumps(sources or []),
            json.dumps(agent_trace or []),
            now,
        ),
    )
    conn.execute(
        "UPDATE conversations SET updated_at = ? WHERE id = ?",
        (now, conversation_id),
    )
    conn.commit()
    conn.close()
    return {
        "id": msg_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "sources": sources or [],
        "agent_trace": agent_trace or [],
        "timestamp": now,
    }


def get_messages(
    conversation_id: str, limit: int = 50
) -> list[dict]:
    """Get messages for a conversation, ordered by timestamp."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC LIMIT ?",
        (conversation_id, limit),
    ).fetchall()
    conn.close()
    results = []
    for r in rows:
        d = dict(r)
        d["sources"] = json.loads(d["sources"]) if d["sources"] else []
        d["agent_trace"] = json.loads(d["agent_trace"]) if d["agent_trace"] else []
        results.append(d)
    return results


# ─── Uploads ─────────────────────────────────────────────────

def add_upload(
    conversation_id: str,
    filename: str,
    file_type: str = "pdf",
    collection_name: str = "",
    doc_count: int = 0,
) -> dict:
    """Record a file upload."""
    upload_id = str(uuid.uuid4())
    now = time.time()
    conn = _get_conn()
    conn.execute(
        """INSERT INTO uploads (id, conversation_id, filename, file_type, collection_name, doc_count, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (upload_id, conversation_id, filename, file_type, collection_name, doc_count, now),
    )
    conn.commit()
    conn.close()
    return {
        "id": upload_id,
        "conversation_id": conversation_id,
        "filename": filename,
        "file_type": file_type,
        "collection_name": collection_name,
        "doc_count": doc_count,
        "timestamp": now,
    }


def get_uploads(conversation_id: str) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM uploads WHERE conversation_id = ? ORDER BY timestamp DESC",
        (conversation_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# Initialize on import
init_db()
