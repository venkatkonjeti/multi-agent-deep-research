# Deep Research Agent Platform

A multi-agent deep research platform with local-first Ollama inference and automatic OpenAI fallback. Built with a FastAPI backend, React + TypeScript frontend, and ChromaDB vector storage.

---

## Features

### Multi-Agent Architecture

Six specialised agents collaborate through an event bus:

| Agent | Role |
|-------|------|
| **Orchestrator** | Plans execution strategy and coordinates the agent chain |
| **Retrieval** | Searches ChromaDB vector store for previously indexed knowledge |
| **Knowledge** | Queries the LLM's parametric knowledge with confidence detection |
| **Web Search** | Falls back to live web search and scraping when local sources are insufficient |
| **Ingestion** | Chunks, embeds, and indexes documents and web pages into the vector DB |
| **Synthesis** | Generates the final, citation-backed research response |

### Retrieval-Priority Chain

Queries follow a cost-efficient path: **Vector DB → Model Knowledge → Web Search**, with automatic caching of results for future retrieval.

### Dual-Provider LLM Support

- **Primary — Ollama** (local): Chat, vision, and streaming inference via any Ollama-hosted model (default: `qwen3-vl:8b`)
- **Fallback — OpenAI**: Automatic failover for chat, vision, and streaming when Ollama is unavailable
- **Embeddings — OpenAI direct**: Text embeddings use OpenAI exclusively for stability (default: `text-embedding-3-small`)
- All models are configurable via environment variables

### Document & Web Ingestion

- **PDF Upload**: Multimodal extraction of text, tables, images, and diagrams with vision-based descriptions
- **URL Ingestion**: Scrape and index web pages for future retrieval
- Smart chunking with configurable size, overlap, and separators

### Conversation Management

- **Persistent Sessions**: SQLite-backed multi-conversation storage
- **Auto-Load**: Most recent conversation restored on page refresh
- **Rename**: Double-click a conversation title in the sidebar to edit inline
- **Delete**: Remove conversations with automatic selection of the next one
- **Search**: `Ctrl+K` / `⌘K` opens a centred search modal with fuzzy filtering, keyboard navigation, and sidebar flash-highlight on selection

### Real-Time UI

- **Streaming Responses**: Server-Sent Events for token-by-token output
- **Live Agent Trace**: Expandable trace panel showing each agent's planning, tool calls, and timing in real time
- **Vector Store Stats**: Live display of indexed collection sizes
- **Dark Theme**: Professional dark slate + indigo accent UI with Inter and JetBrains Mono fonts

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, [uv](https://docs.astral.sh/uv/) package manager |
| Frontend | React 18, TypeScript, Vite |
| Vector DB | ChromaDB (persistent, cosine similarity) |
| LLM (primary) | Ollama (local) |
| LLM (fallback) | OpenAI API |
| Database | SQLite (conversations & messages) |
| Styling | Custom CSS (dark theme, no frameworks) |

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/) — Python package manager
- [Ollama](https://ollama.ai) running locally (optional if using OpenAI-only)
- An [OpenAI API key](https://platform.openai.com/api-keys) (required for embeddings; used as chat fallback)

---

## Quick Start

### 1. Pull Ollama models (if using Ollama)

```bash
ollama pull qwen3-vl:8b
```

### 2. Configure environment

```bash
cd backend
cp .env.example .env
# Edit .env — at minimum set OPENAI_API_KEY
```

### 3. Install dependencies

```bash
# Backend
cd backend && uv sync

# Frontend
cd ../frontend && npm install
```

### 4. Start the platform

```bash
# Terminal 1 — Backend (from backend/)
cd backend && uv run deep-research

# Terminal 2 — Frontend (from frontend/)
cd frontend && npm run dev
```

Open **http://localhost:5173** in your browser.

---

## Environment Variables

All configuration lives in `backend/.env`. See `backend/.env.example` for the full template.

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_INFERENCE_MODEL` | `qwen3-vl:8b` | Model for chat & vision (Ollama) |
| `OPENAI_API_KEY` | — | Required for embeddings and fallback |
| `OPENAI_INFERENCE_MODEL` | `gpt-4o-mini` | Chat fallback model (OpenAI) |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model (OpenAI) |
| `OPENAI_VISION_MODEL` | `gpt-4o-mini` | Vision fallback model (OpenAI) |

---

## Project Structure

```
ollama-demo/
├── backend/
│   ├── config.py              # Central configuration & env loading
│   ├── main.py                # FastAPI app — SSE chat, PDF upload, CRUD
│   ├── pyproject.toml         # Python dependencies (uv)
│   ├── .env.example           # Environment template (safe to commit)
│   ├── core/
│   │   ├── llm_client.py      # Unified LLM abstraction (Ollama + OpenAI)
│   │   ├── vector_store.py    # ChromaDB wrapper (3 collections)
│   │   ├── chunker.py         # Text chunking with overlap
│   │   ├── pdf_processor.py   # Multimodal PDF extraction
│   │   ├── session_manager.py # SQLite conversation CRUD
│   │   └── event_bus.py       # Inter-agent event system
│   ├── agents/
│   │   ├── orchestrator.py    # Execution planner
│   │   ├── retrieval.py       # Vector DB searcher
│   │   ├── knowledge.py       # LLM knowledge querier
│   │   ├── web_search.py      # Web search & scrape
│   │   ├── ingestion.py       # Document indexer
│   │   └── synthesis.py       # Response generator
│   ├── tools/
│   │   ├── search_engine.py   # DuckDuckGo search
│   │   └── web_scraper.py     # Page content extractor
│   └── data/                  # Runtime data (git-ignored)
│       ├── chroma_db/         # Vector store persistence
│       ├── conversations.db   # SQLite database
│       └── uploads/           # Uploaded PDFs
├── frontend/
│   ├── index.html
│   ├── public/favicon.svg
│   ├── src/
│   │   ├── App.tsx            # Root component & state
│   │   ├── api.ts             # Backend API client (SSE, REST)
│   │   ├── types.ts           # TypeScript interfaces
│   │   ├── index.css          # Full application styles
│   │   └── components/
│   │       ├── Sidebar.tsx    # Conversation list & actions
│   │       ├── ChatArea.tsx   # Message thread & streaming
│   │       ├── InputBar.tsx   # Message input & PDF upload
│   │       ├── MessageBubble.tsx  # Individual message rendering
│   │       ├── AgentTrace.tsx # Live agent execution trace
│   │       └── SearchModal.tsx # Conversation search (⌘K)
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── .gitignore
└── README.md
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check (Ollama + OpenAI status) |
| `GET` | `/api/conversations` | List all conversations |
| `POST` | `/api/conversations` | Create a new conversation |
| `GET` | `/api/conversations/{id}` | Get conversation details |
| `PUT` | `/api/conversations/{id}` | Rename a conversation |
| `DELETE` | `/api/conversations/{id}` | Delete a conversation |
| `GET` | `/api/conversations/{id}/messages` | Get message history |
| `POST` | `/api/chat` | Send a query (SSE streaming response) |
| `POST` | `/api/upload` | Upload a PDF for ingestion |

---

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+K` / `⌘K` | Open conversation search |
| `↑` `↓` | Navigate search results |
| `Enter` | Select search result |
| `Escape` | Close search modal |
| Double-click title | Rename conversation inline |

---

## License

MIT
