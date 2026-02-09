"""
Chunker — Recursive text splitter with configurable overlap.
Splits text into chunks suitable for embedding and vector storage.
"""

from ..config import CHUNK_SIZE, CHUNK_OVERLAP, CHUNK_SEPARATORS


def chunk_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
    separators: list[str] | None = None,
) -> list[str]:
    """
    Recursively split text into chunks using a hierarchy of separators.
    Ensures each chunk is ≤ chunk_size with overlap between consecutive chunks.
    """
    if separators is None:
        separators = CHUNK_SEPARATORS

    text = text.strip()
    if not text:
        return []

    if len(text) <= chunk_size:
        return [text]

    # Try each separator in order of preference
    for sep in separators:
        if sep and sep in text:
            parts = text.split(sep)
            chunks = _merge_parts(parts, sep, chunk_size, chunk_overlap)
            if chunks:
                return chunks

    # Fallback: hard split by chunk_size with overlap
    return _hard_split(text, chunk_size, chunk_overlap)


def _merge_parts(
    parts: list[str],
    separator: str,
    chunk_size: int,
    chunk_overlap: int,
) -> list[str]:
    """Merge split parts back into chunks that respect size limits."""
    chunks = []
    current_chunk = ""

    for part in parts:
        part = part.strip()
        if not part:
            continue

        candidate = (
            f"{current_chunk}{separator}{part}" if current_chunk else part
        )

        if len(candidate) <= chunk_size:
            current_chunk = candidate
        else:
            if current_chunk:
                chunks.append(current_chunk.strip())

                # Create overlap from end of current chunk
                if chunk_overlap > 0 and len(current_chunk) > chunk_overlap:
                    overlap_text = current_chunk[-chunk_overlap:]
                    current_chunk = f"{overlap_text}{separator}{part}"
                    if len(current_chunk) > chunk_size:
                        current_chunk = part
                else:
                    current_chunk = part
            else:
                # Single part exceeds chunk_size, need to split further
                if len(part) > chunk_size:
                    sub_chunks = _hard_split(part, chunk_size, chunk_overlap)
                    chunks.extend(sub_chunks[:-1])
                    current_chunk = sub_chunks[-1] if sub_chunks else ""
                else:
                    current_chunk = part

    if current_chunk.strip():
        chunks.append(current_chunk.strip())

    return chunks


def _hard_split(
    text: str, chunk_size: int, chunk_overlap: int
) -> list[str]:
    """Split text by character count with overlap."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        start = end - chunk_overlap if chunk_overlap > 0 else end
        if start >= len(text):
            break
        # Safety: prevent infinite loop
        if end >= len(text):
            break
    return chunks


def chunk_text_with_metadata(
    text: str,
    base_metadata: dict | None = None,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> list[tuple[str, dict]]:
    """
    Chunk text and attach metadata (including chunk_index) to each chunk.
    Returns list of (chunk_text, metadata) tuples.
    """
    chunks = chunk_text(text, chunk_size, chunk_overlap)
    base = base_metadata or {}
    result = []
    for i, chunk in enumerate(chunks):
        meta = {**base, "chunk_index": i, "total_chunks": len(chunks)}
        result.append((chunk, meta))
    return result
