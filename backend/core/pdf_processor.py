"""
PDF Processor — Extracts text, tables, and images/diagrams from PDF files.
Uses PyMuPDF for text & images, pdfplumber for tables.
Images are sent to qwen3-vl:8b for visual description (multimodal).
"""
from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass

import fitz  # PyMuPDF
import pdfplumber
from PIL import Image

from ..config import PDF_IMAGE_MIN_SIZE, PDF_IMAGE_DPI

logger = logging.getLogger(__name__)


@dataclass
class ExtractedImage:
    """An image extracted from a PDF page."""
    page_number: int
    image_bytes: bytes
    image_b64: str
    width: int
    height: int
    description: str = ""  # filled by vision model


@dataclass
class ExtractedTable:
    """A table extracted from a PDF page."""
    page_number: int
    markdown: str


@dataclass
class ExtractedPage:
    """All content from a single PDF page."""
    page_number: int
    text: str
    tables: list[ExtractedTable]
    images: list[ExtractedImage]


@dataclass
class PDFContent:
    """Complete extracted content from a PDF."""
    filename: str
    total_pages: int
    pages: list[ExtractedPage]
    full_text: str  # concatenated text from all pages

    @property
    def all_images(self) -> list[ExtractedImage]:
        return [img for page in self.pages for img in page.images]

    @property
    def all_tables(self) -> list[ExtractedTable]:
        return [tbl for page in self.pages for tbl in page.tables]


def _table_to_markdown(table: list[list]) -> str:
    """Convert a pdfplumber table (list of rows) to markdown format."""
    if not table or not table[0]:
        return ""

    # Clean cells
    clean_table = []
    for row in table:
        clean_row = [str(cell).strip() if cell else "" for cell in row]
        clean_table.append(clean_row)

    # Build markdown
    headers = clean_table[0]
    md = "| " + " | ".join(headers) + " |\n"
    md += "| " + " | ".join(["---"] * len(headers)) + " |\n"
    for row in clean_table[1:]:
        # Pad row if needed
        while len(row) < len(headers):
            row.append("")
        md += "| " + " | ".join(row[: len(headers)]) + " |\n"
    return md


def extract_pdf(file_path: str) -> PDFContent:
    """
    Extract all content from a PDF file.
    - Text via PyMuPDF
    - Tables via pdfplumber
    - Images via PyMuPDF (to be described by vision model separately)
    """
    pages = []
    full_text_parts = []

    # ─── PyMuPDF: text + images ──────────────────────────────
    doc = fitz.open(file_path)

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_num = page_idx + 1

        # Extract text
        text = page.get_text("text").strip()
        full_text_parts.append(text)

        # Extract images
        images = []
        image_list = page.get_images(full=True)
        for img_info in image_list:
            xref = img_info[0]
            try:
                pix = fitz.Pixmap(doc, xref)
                if pix.n < 5:  # not CMYK
                    img_pix = pix
                else:
                    img_pix = fitz.Pixmap(fitz.csRGB, pix)

                if img_pix.width < PDF_IMAGE_MIN_SIZE or img_pix.height < PDF_IMAGE_MIN_SIZE:
                    continue

                img_bytes = img_pix.tobytes("png")
                img_b64 = base64.b64encode(img_bytes).decode("utf-8")

                images.append(ExtractedImage(
                    page_number=page_num,
                    image_bytes=img_bytes,
                    image_b64=img_b64,
                    width=img_pix.width,
                    height=img_pix.height,
                ))
            except Exception as e:
                logger.warning(f"Failed to extract image from page {page_num}: {e}")

        pages.append(ExtractedPage(
            page_number=page_num,
            text=text,
            tables=[],
            images=images,
        ))

    doc.close()

    # ─── pdfplumber: tables ──────────────────────────────────
    try:
        with pdfplumber.open(file_path) as pdf:
            for page_idx, page in enumerate(pdf.pages):
                page_num = page_idx + 1
                tables = page.extract_tables()
                if tables and page_idx < len(pages):
                    for table in tables:
                        md = _table_to_markdown(table)
                        if md.strip():
                            pages[page_idx].tables.append(
                                ExtractedTable(page_number=page_num, markdown=md)
                            )
    except Exception as e:
        logger.warning(f"pdfplumber table extraction failed: {e}")

    return PDFContent(
        filename=file_path.split("/")[-1],
        total_pages=len(pages),
        pages=pages,
        full_text="\n\n".join(full_text_parts),
    )


async def describe_pdf_images(
    pdf_content: PDFContent,
    describe_fn,
) -> PDFContent:
    """
    Send each extracted image to the vision model for description.
    `describe_fn` should be `llm_client.describe_image`.
    """
    for page in pdf_content.pages:
        for img in page.images:
            try:
                prompt = (
                    f"This image is from page {img.page_number} of a PDF document "
                    f"named '{pdf_content.filename}'. "
                    "Describe this image in complete detail: all text, labels, "
                    "arrows, relationships, data flows, chart values, diagram "
                    "structure, colors, and any other visual information. "
                    "If it's a diagram, describe the architecture or flow. "
                    "If it's a table, reproduce it. If it's a chart, state the data."
                )
                img.description = await describe_fn(img.image_bytes, prompt)
                logger.info(
                    f"Described image on page {img.page_number} "
                    f"({img.width}x{img.height})"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to describe image on page {img.page_number}: {e}"
                )
                img.description = f"[Image on page {img.page_number}, {img.width}x{img.height}px — description unavailable]"

    return pdf_content
