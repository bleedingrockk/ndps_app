from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from typing import List
from app.rag.query_all import query_bnss
from app.utils.retry import exponential_backoff_retry
import logging

logger = logging.getLogger(__name__)

class SectionsCharged(BaseModel):
    section_number: str = Field(
        description="The section number of the legal provision"
    )
    section_description: str = Field(
        description="A clear definition of what the section covers based ONLY on the retrieved legal text. Describe the section's scope, provisions, and legal meaning. Do NOT explain why it's relevant to the FIR - that goes in why_section_is_relevant."
    )
    why_section_is_relevant: str = Field(
        description="A clear explanation of why this section is valid and applicable to the legal point/charge from the FIR. Explain the connection between the FIR facts and this specific section, making it clear why this section should be charged."
    )
    source: str = Field(
        description="Source information including page number, PDF document name, and source URL from the BNSS document (format: Page X, Document: [pdf_name], Source URL: [source_url])"
    )

class BnssLegalMapping(BaseModel):
    sections: List[SectionsCharged] = Field(
        description=""
    )

class PointsToBeCharged(BaseModel):
    points_to_be_charged: List[str] = Field(
        description="List of factual points extracted directly and explicitly from the FIR text. Each point must be a direct factual statement that is explicitly stated in the FIR, with no interpretations, inferences, or additions. Maximum 10 high-quality points.",
        max_items=10
    )


def bnss_legal_mapping(state: WorkflowState) -> dict:
    """
    Map Bharatiya Nagarik Suraksha Sanhita (BNSS) legal provisions to FIR facts.
    """
    logger.info("Starting BNSS legal mapping")

    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for FIR fact extraction")

    pdf_content = state["pdf_content_in_english"]
    logger.debug(f"FIR content length: {len(pdf_content)} characters")
    llm_with_structured_output = llm_model.with_structured_output(PointsToBeCharged)
    prompt = f"""
You are an expert in Indian criminal procedure (Bharatiya Nagarik Suraksha Sanhita / BNSS).

Task: Extract only factual points from the FIR text below.

Rules:
- Extract MAXIMUM 10 high-quality factual points.
- Prioritize the most legally significant and relevant facts.
- Use only facts that are explicitly written in the FIR.
- Do not infer, assume, interpret, or add anything.
- Do not mention any section numbers.
- Extract only BNSS-related facts (acts, substances, quantities, locations, actions, procedures).
- Each point must be a separate, clear, high-quality factual statement.
- Focus on facts that are most relevant for legal charging and prosecution.
- If something is not written in the FIR, do not include it.
- Quality over quantity - select only the most important and legally significant points.

FIR Text:
{pdf_content}

Output: List only the factual points (maximum 10 high-quality points).
"""
    
    @exponential_backoff_retry(max_retries=5, max_wait=60)
    def _invoke_extract_points():
        return llm_with_structured_output.invoke(prompt)
    
    response = _invoke_extract_points()
    points = response.points_to_be_charged
    logger.info(f"Extracted {len(points)} legal points")

    sections_mapped = []
    for idx, point in enumerate(points, 1):
        logger.debug(f"Processing point {idx}/{len(points)}")
        results = query_bnss(point, k=5)
        logger.debug(f"Found {len(results)} relevant sections for point {idx}")

        # Format retrieved sections with section heading, exact legal wording, and source
        # query_bnss returns [{'chunk': {...}, 'score': float}]; chunk structure: section, subsection (may be null), chapter, chapter_heading, content, page_number, source_url, pdf_name
        sections_found = ""
        for i, result in enumerate(results):
            chunk = result['chunk']
            section = chunk['section']
            subsection = chunk.get('subsection')  # May be null
            chapter = chunk['chapter']
            chapter_heading = chunk['chapter_heading']
            content = chunk['content']
            page_number = chunk['page_number']
            source_url = chunk['source_url']
            pdf_name = chunk['pdf_name']
            chunk_id = i + 1
            
            # Build section number (section + subsection if present)
            section_num = section + (f' {subsection}' if subsection else '')
            
            sections_found += f"{section_num}\n"
            sections_found += f"Chapter: {chapter} - {chapter_heading}\n"
            sections_found += f"Source: Page {page_number}, Chunk {chunk_id}\n"
            sections_found += f"Source URL: {source_url}\n"
            sections_found += f"Document: {pdf_name}\n"
            sections_found += f"Legal Text:\n{content}\n"
            sections_found += "-" * 80 + "\n"

        # Create prompt with the legal point and retrieved sections
        llm_with_structured_output = llm_model.with_structured_output(BnssLegalMapping)
        prompt = f"""
You are an expert in BNSS (Bharatiya Nagarik Suraksha Sanhita) law.

Legal Point (from FIR):
{point}

Retrieved BNSS Act Text:
{sections_found}

Task:
Identify only the BNSS sections that are directly applicable to the legal point from the FIR.

CRITICAL RULES:
1. Use ONLY the retrieved BNSS Act text above. Do not add external knowledge, legal interpretations, or assumptions.
2. Each section must be clearly supported by the retrieved text.
3. The legal point must directly match facts that the section addresses according to the retrieved text.
4. You are NOT required to use all retrieved sections - select only what is important and relevant to the legal point.
5. If a section is not clearly and directly applicable based on the retrieved text, exclude it.
6. Prefer fewer accurate sections over many weak ones.
7. Do NOT interpret or infer connections - use only what is explicitly stated in the retrieved BNSS Act text.

For each included section, return:

- section_number:
  Must match exactly as shown in retrieved text (e.g. "Section 1 (1)", "Section 20", including sub-clauses like 20(b-ii)(B), 29(1), etc.)
  Format: Include subsection if shown (e.g. "Section 20 (1)" or "Section 20").

- section_description:
  Describe what the section states using ONLY the retrieved Legal Text above.
  Do not add interpretations or external knowledge.
  Base this description solely on the exact words from the retrieved text.

- why_section_is_relevant:
  Explain how the legal point from the FIR relates to this section, based ONLY on what the retrieved Legal Text states.
  Reference specific facts from the legal point that align with what the section text describes.
  Do not make assumptions or interpretations beyond what is explicitly stated.

- source:
  Format: "Page X, Document: [pdf_name], Source URL: [source_url]"
  Use the exact values from "Source:", "Document:", and "Source URL:" fields above.
  Example: "Page 15, Document: THE_BHARATIYA_NAGARIK_SURAKSHA_SANHITA_2023.pdf, Source URL: https://www.mha.gov.in/..."

If no section from the retrieved text directly applies to the legal point, return an empty list [].
Return output as JSON list only.
"""
        
        @exponential_backoff_retry(max_retries=5, max_wait=60)
        def _invoke_map_sections():
            return llm_with_structured_output.invoke(prompt)
        
        response = _invoke_map_sections()
        sections_mapped.append(response.sections)
        logger.debug(f"Mapped point {idx} to {len(response.sections)} sections")

    # Flatten the list of lists into a single list
    flattened_sections = []
    for chunk_sections in sections_mapped:
        flattened_sections.extend(chunk_sections)
    
    # Convert back to list of dicts
    final_sections = [section.model_dump() if hasattr(section, 'model_dump') else section for section in flattened_sections]
    
    logger.info(f"Mapped {len(final_sections)} BNSS sections")

    return {
        "bnss_sections_mapped": final_sections
    }
