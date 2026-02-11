from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from typing import List
from app.rag.query_all import query_bsa
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
        description="Source information including page number, PDF document name, and source URL from the BSA document (format: Page X, Document: [pdf_name], Source URL: [source_url])"
    )

class BsaLegalMapping(BaseModel):
    sections: List[SectionsCharged] = Field(
        description="List of BSA sections applicable to the FIR. Return ONLY the top 5 most relevant and important sections."
    )

class PointsToBeCharged(BaseModel):
    points_to_be_charged: List[str] = Field(
        description="List of factual points extracted directly and explicitly from the FIR text. Each point must be a direct factual statement that is explicitly stated in the FIR, with no interpretations, inferences, or additions. Maximum 5 high-quality points.",
        max_items=5
    )


def bsa_legal_mapping(state: WorkflowState) -> dict:
    """
    Map Bharatiya Sakshya Adhiniyam (BSA) legal provisions to FIR facts.
    New approach: Extract 5 points -> Get top 5 sections per point -> Single LLM call with full context -> Deduplicate
    """
    logger.info("Starting BSA legal mapping")

    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for FIR fact extraction")

    pdf_content = state["pdf_content_in_english"]
    logger.debug(f"FIR content length: {len(pdf_content)} characters")
    
    # STEP 1: Extract top 5 legal points from FIR
    logger.info("Step 1: Extracting top 5 legal points from FIR")
    llm_with_structured_output = llm_model.with_structured_output(PointsToBeCharged)
    extract_prompt = f"""
You are an expert in Indian evidence law (Bharatiya Sakshya Adhiniyam / BSA).

Task: Extract only factual points from the FIR text below.

Rules:
- Extract EXACTLY 5 high-quality factual points.
- Prioritize the most legally significant and relevant facts.
- Use only facts that are explicitly written in the FIR.
- Do not infer, assume, interpret, or add anything.
- Do not mention any section numbers.
- Extract only BSA-related facts (acts, substances, quantities, locations, actions, procedures).
- Each point must be a separate, clear, high-quality factual statement.
- Focus on facts that are most relevant for legal charging and prosecution.
- If something is not written in the FIR, do not include it.
- Quality over quantity - select only the most important and legally significant points.

FIR Text:
{pdf_content}

Output: List exactly 5 factual points.
"""
    
    @exponential_backoff_retry(max_retries=5, max_wait=60)
    def _invoke_extract_points():
        return llm_with_structured_output.invoke(extract_prompt)
    
    response = _invoke_extract_points()
    points = response.points_to_be_charged
    logger.info(f"Extracted {len(points)} legal points")
    for idx, point in enumerate(points, 1):
        logger.debug(f"Point {idx}: {point[:150]}...")

    # STEP 2: Query RAG for each point and collect all unique sections
    logger.info("Step 2: Querying RAG for relevant BSA sections")
    all_sections_dict = {}  # Use dict to deduplicate by section_number
    
    for idx, point in enumerate(points, 1):
        logger.debug(f"Querying RAG for point {idx}/{len(points)}")
        results = query_bsa(point, k=5)
        logger.debug(f"Found {len(results)} results for point {idx}")

        for result in results:
            chunk = result['chunk']
            section = chunk['section']
            subsection = chunk.get('subsection')  # May be null
            
            # Build unique section identifier
            section_num = section + (f' {subsection}' if subsection else '')
            
            # Store only if not already present (avoid duplicates)
            if section_num not in all_sections_dict:
                all_sections_dict[section_num] = chunk
                logger.debug(f"Added new section: {section_num}")
            else:
                logger.debug(f"Skipped duplicate section: {section_num}")
    
    logger.info(f"Collected {len(all_sections_dict)} unique BSA sections")

    # STEP 3: Format all retrieved sections for the final LLM prompt
    logger.info("Step 3: Formatting retrieved sections")
    sections_text = ""
    for section_num, chunk in all_sections_dict.items():
        chapter = chunk['chapter']
        chapter_heading = chunk['chapter_heading']
        content = chunk['content']
        page_number = chunk['page_number']
        source_url = chunk['source_url']
        pdf_name = chunk['pdf_name']
        
        sections_text += f"{section_num}\n"
        sections_text += f"Chapter: {chapter} - {chapter_heading}\n"
        sections_text += f"Source: Page {page_number}\n"
        sections_text += f"Source URL: {source_url}\n"
        sections_text += f"Document: {pdf_name}\n"
        sections_text += f"Legal Text:\n{content}\n"
        sections_text += "=" * 80 + "\n\n"

    # STEP 4: Single LLM call with full FIR + all retrieved sections
    logger.info("Step 4: Final LLM mapping with full context")
    llm_with_structured_output = llm_model.with_structured_output(BsaLegalMapping)
    final_prompt = f"""
You are an expert in BSA (Bharatiya Sakshya Adhiniyam) law.

Complete FIR Text:
{pdf_content}

Retrieved BSA Act Sections:
{sections_text}

Task:
Identify ONLY THE TOP 5 MOST RELEVANT AND IMPORTANT BSA sections from the retrieved text above that are directly applicable to the FIR.

CRITICAL RULES:
1. Return EXACTLY 5 sections maximum - the most important and directly applicable ones.
2. Use ONLY the retrieved BSA Act text above. Do not add external knowledge, legal interpretations, or assumptions.
3. Each section must be clearly supported by the retrieved text.
4. The facts in the FIR must directly match what the section addresses according to the retrieved text.
5. Prioritize sections that are most critical for prosecution (e.g., substantive offenses over procedural sections).
6. Do NOT interpret or infer connections - use only what is explicitly stated in the retrieved BSA Act text.
7. Review the ENTIRE FIR to understand the full context before selecting sections.
8. Avoid including duplicate or similar sections - each section should cover a distinct legal aspect.
9. If fewer than 5 sections are truly applicable, return only those that are clearly relevant.

For each included section, return:

- section_number:
  Must match exactly as shown in retrieved text (e.g. "Section 1 (1)", "Section 20", including sub-clauses like 20(b-ii)(B), 29(1), etc.)
  Format: Include subsection if shown (e.g. "Section 20 (1)" or "Section 20").

- section_description:
  Describe what the section states using ONLY the retrieved Legal Text above.
  Do not add interpretations or external knowledge.
  Base this description solely on the exact words from the retrieved text.

- why_section_is_relevant:
  Explain how the facts from the FIR relate to this section, based ONLY on what the retrieved Legal Text states.
  Reference specific facts from the FIR that align with what the section text describes.
  Be specific and clear about the connection.
  Do not make assumptions or interpretations beyond what is explicitly stated.

- source:
  Format: "Page X, Document: [pdf_name], Source URL: [source_url]"
  Use the exact values from the retrieved sections above.
  Example: "Page 15, Document: THE_BHARATIYA_SAKSHYA_ADHINIYAM_2023.pdf, Source URL: https://www.mha.gov.in/..."

Return output as JSON with the top 5 most relevant sections only.
"""
    
    @exponential_backoff_retry(max_retries=5, max_wait=60)
    def _invoke_final_mapping():
        return llm_with_structured_output.invoke(final_prompt)
    
    final_response = _invoke_final_mapping()
    final_sections_raw = [section.model_dump() for section in final_response.sections]
    
    logger.info(f"LLM returned {len(final_sections_raw)} sections")

    # STEP 5: Deduplicate sections by section_number (safety measure)
    logger.info("Step 5: Deduplicating sections")
    seen_sections = {}
    for section in final_sections_raw:
        section_num = section['section_number']
        if section_num not in seen_sections:
            seen_sections[section_num] = section
            logger.debug(f"Kept section: {section_num}")
        else:
            logger.warning(f"Duplicate section removed: {section_num}")
    
    final_sections = list(seen_sections.values())
    
    logger.info(f"Final mapping complete: {len(final_sections)} unique BSA sections mapped")
    for idx, section in enumerate(final_sections, 1):
        logger.info(f"Section {idx}: {section['section_number']}")

    return {
        "bsa_sections_mapped": final_sections
    }
