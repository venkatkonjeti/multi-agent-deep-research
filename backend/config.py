"""
Deep Research Agent Platform — Configuration
All tunable constants, model names, thresholds, and paths.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from the backend/ directory (where this file lives)
_env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(_env_path)

# ─── Project Paths ───────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CHROMA_DB_DIR = os.path.join(DATA_DIR, "chroma_db")
SQLITE_DB_PATH = os.path.join(DATA_DIR, "conversations.db")
UPLOADS_DIR = os.path.join(DATA_DIR, "uploads")

# Ensure directories exist
for d in [DATA_DIR, CHROMA_DB_DIR, UPLOADS_DIR]:
    os.makedirs(d, exist_ok=True)

# ─── Ollama Settings (Primary) ──────────────────────────────
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Primary models (Ollama local)
INFERENCE_MODEL = os.getenv("OLLAMA_INFERENCE_MODEL", "qwen3-vl:8b")
EMBEDDING_MODEL = os.getenv("OLLAMA_EMBEDDING_MODEL", "MedAIBase/Qwen3-VL-Embedding:2b")

# ─── OpenAI Settings (Fallback) ─────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_INFERENCE_MODEL = os.getenv("OPENAI_INFERENCE_MODEL", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")

# ─── Vector DB (ChromaDB) ───────────────────────────────────
COLLECTION_RESEARCH_CACHE = "research_cache"
COLLECTION_INGESTED_DOCS = "ingested_documents"
COLLECTION_WEB_KNOWLEDGE = "web_knowledge"

# Similarity threshold — above this, vector DB result is considered sufficient
# ChromaDB returns distances (lower = more similar). Threshold is max distance.
SIMILARITY_THRESHOLD = 0.45

# Max results to return from vector DB search
VECTOR_SEARCH_TOP_K = 5

# ─── Chunking Settings ──────────────────────────────────────
CHUNK_SIZE = 512          # characters per chunk
CHUNK_OVERLAP = 50        # overlapping characters between chunks
CHUNK_SEPARATORS = ["\n\n", "\n", ". ", " ", ""]

# ─── Web Search Settings ────────────────────────────────────
WEB_SEARCH_MAX_RESULTS = 5
WEB_SCRAPE_TIMEOUT = 15           # seconds
WEB_SCRAPE_MAX_CONTENT_LENGTH = 8000   # chars per page

# ─── Knowledge Agent ────────────────────────────────────────
LOW_CONFIDENCE_INDICATORS = [
    "i'm not sure",
    "i don't have",
    "i cannot confirm",
    "i'm unable to",
    "my knowledge",
    "my training data",
    "i don't know",
    "not enough information",
    "i cannot provide",
    "as of my last",
    "i do not have access",
    "i'm not certain",
    "beyond my knowledge",
]

# ─── Synthesis Agent ────────────────────────────────────────
MAX_CONTEXT_LENGTH = 6000   # max chars from sources fed to synthesis prompt

# ─── PDF Processing ─────────────────────────────────────────
PDF_IMAGE_MIN_SIZE = 50      # minimum width/height in pixels to extract
PDF_IMAGE_DPI = 150          # DPI for image extraction

# ─── Session / Conversation ─────────────────────────────────
CONVERSATION_TITLE_MAX_LENGTH = 80
MAX_CONVERSATION_HISTORY = 20   # messages to include as context

# ─── Backend Server ─────────────────────────────────────────
API_HOST = "0.0.0.0"
API_PORT = 8000
CORS_ORIGINS = [
    "http://localhost:5173",   # Vite dev server
    "http://localhost:3000",
    "http://127.0.0.1:5173",
]
