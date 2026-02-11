import fitz  # pip install pymupdf
import logging

logger = logging.getLogger(__name__)


def read_pdf(state: dict) -> dict:
    """
    Read PDF from state (pdf_bytes or pdf_path) and return {"pdf_content_in_english": text}.
    Assumes PDF is already in English - no translation needed.
    No files are written to disk.
    """
    import sys
    logger.info("📖 [read_pdf] Starting PDF reading...")
    sys.stdout.flush()  # Force flush to see logs immediately
    
    pdf_bytes = state.get("pdf_bytes")
    pdf_path = state.get("pdf_path")

    if pdf_bytes is not None:
        logger.debug(f"📄 [read_pdf] Reading from pdf_bytes (size: {len(pdf_bytes)} bytes)")
        sys.stdout.flush()
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    elif pdf_path:
        logger.debug(f"📄 [read_pdf] Reading from pdf_path: {pdf_path}")
        sys.stdout.flush()
        doc = fitz.open(pdf_path)
    else:
        logger.error("❌ [read_pdf] Neither pdf_bytes nor pdf_path found in state")
        sys.stdout.flush()
        raise ValueError("Either pdf_bytes or pdf_path is required in state.")

    text = [page.get_text() for page in doc]
    doc.close()
    final_text = "\n".join(text)
    logger.info(f"✅ [read_pdf] PDF read successfully. Extracted {len(final_text)} characters from {len(text)} pages")
    sys.stdout.flush()  # Force flush to see logs immediately
    # Return as pdf_content_in_english since PDF is already in English
    return {"pdf_content_in_english": final_text}
