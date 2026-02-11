import fitz  # pip install pymupdf


def read_pdf(state: dict) -> dict:
    """
    Read PDF from state (pdf_bytes or pdf_path) and return {"pdf_content_in_english": text}.
    Assumes PDF is already in English - no translation needed.
    No files are written to disk.
    """
    print("Reading PDF...")
    pdf_bytes = state.get("pdf_bytes")
    pdf_path = state.get("pdf_path")

    if pdf_bytes is not None:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    elif pdf_path:
        doc = fitz.open(pdf_path)
    else:
        raise ValueError("Either pdf_bytes or pdf_path is required in state.")

    text = [page.get_text() for page in doc]
    doc.close()
    final_text = "\n".join(text)
    print("PDF read successfully.")
    # Return as pdf_content_in_english since PDF is already in English
    return {"pdf_content_in_english": final_text}
