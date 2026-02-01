from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from typing import List
from app.utils.retry import exponential_backoff_retry
import logging

logger = logging.getLogger(__name__)

class SummaryForTheCourt(BaseModel):
    """Court summary for NDPS case prosecution"""
    case_title: str = Field(description="Case title in format: STATE OF [STATE] vs. [ACCUSED NAME] (with any relevant qualifiers like JUVENILE, etc.)")
    ndps_sections: List[str] = Field(description="List of NDPS Act sections applicable to the case (e.g., ['8(c)', '20(b)(ii)(B)', '29'])")
    core_issue: str = Field(description="Core legal issue/question that the court needs to decide, framed as a question")
    date_and_place: str = Field(description="Date and place of incident in format: DD.MM.YYYY, [Location]")
    recovery: str = Field(description="Description of what was recovered, from where, quantity")
    quantity: str = Field(description="Classification (small/intermediate/commercial) and actual quantity")
    safeguards: List[str] = Field(description="List of compliance points (e.g., 'Section 50 NDPS – explained & waived')")
    conscious_possession_proven: List[str] = Field(description="List of facts proving conscious possession")
    procedural_compliance: List[str] = Field(description="List of procedural safeguards complied with")
    legal_position: List[str] = Field(description="List of legal points supporting prosecution")
    judicial_balance: str = Field(description="Balanced judicial perspective considering both prosecution and defence aspects, public interest, and legal principles")
    prosecution_prayer: List[str] = Field(description="List of specific prayers/requests to the court (e.g., 'Cognizance of offence', 'Framing of charges', 'Bail to be denied', etc.)")

def generate_summary_for_the_court(state: WorkflowState) -> dict:
    """
    Generate a comprehensive court summary for NDPS case prosecution.
    """
    logger.info("Starting summary for the court generation")
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for summary for the court generation")
    
    pdf_content = state["pdf_content_in_english"]
    
    # Get FIR facts if available
    fir_facts = state.get("fir_facts", {})
    
    # Get NDPS sections if available
    ndps_sections = state.get("ndps_sections_mapped", [])
    ndps_section_numbers = [s.get('section_number', '') for s in ndps_sections if isinstance(s, dict) and s.get('section_number')]
    
    # Construct content for LLM
    content_for_llm = f"""You are an expert NDPS Act prosecutor preparing a comprehensive court summary for a criminal case.

Your task is to analyse the FIR content provided below and generate a **professional court summary** that presents the prosecution's case clearly and persuasively.

You MUST strictly follow these rules:

1. Base every point ONLY on the facts available in the FIR.
2. Extract specific details: names, dates, times, locations, quantities, sections, procedural compliance points
3. Frame the case in a legally sound and persuasive manner
4. Use formal legal language appropriate for court documents
5. Structure the output exactly as per the schema provided

### FIR CONTENT:
{pdf_content}

### ADDITIONAL CONTEXT:
"""
    
    # Add FIR facts if available
    if fir_facts:
        content_for_llm += f"\n### FIR FACTS:\n"
        for key, value in fir_facts.items():
            content_for_llm += f"- {key}: {value}\n"
    
    # Add NDPS sections if available
    if ndps_section_numbers:
        content_for_llm += f"\n### APPLICABLE NDPS SECTIONS:\n"
        content_for_llm += f"{', '.join(ndps_section_numbers)}\n"
    
    content_for_llm += f"""

### INSTRUCTIONS FOR GENERATING COURT SUMMARY:

1. **Case Title**: Format as "STATE OF [STATE NAME] vs. [ACCUSED NAME]" with qualifiers like "(JUVENILE)" if applicable. Extract state and accused name from FIR.

2. **NDPS Sections**: List all applicable NDPS Act sections based on the offence. Include sections for possession, quantity, conspiracy if applicable.

3. **Core Issue**: Frame as a question that captures the central legal question the court must decide. Example: "Whether the accused was found in conscious and exclusive possession of [quantity] of [substance], in compliance with mandatory NDPS safeguards, warranting prosecution under NDPS Act."

4. **Date and Place**: "DD.MM.YYYY, [Location]" format

5. **Recovery**: Description of what was recovered, from where, quantity

6. **Quantity**: Classification (small/intermediate/commercial) and actual quantity

7. **Safeguards**: List of compliance points (e.g., "Section 50 NDPS – explained & waived", "Section 43 NDPS – public place search", "Videography & sealing done")

8. **Conscious Possession Proven**: List of facts proving conscious possession (admissions, exclusive custody, no licence, corroborating evidence)

9. **Procedural Compliance**: List of procedural safeguards complied with (sections, documentation, chain of custody)

10. **Legal Position**: List of legal points supporting prosecution (jurisdiction, applicability of sections, precedent if relevant)

11. **Judicial Balance**: Write 2-3 sentences that balance the seriousness of the offence with any mitigating factors, public interest, and legal principles. Acknowledge both prosecution and defence perspectives where appropriate.

12. **Prosecution Prayer**: List specific requests to the court, typically:
   - "Cognizance of offence"
   - "Framing of charges"
   - "Bail to be denied in interest of justice" (if applicable)
   - "Trial to proceed under [relevant Act] with NDPS rigour preserved"

### CRITICAL REQUIREMENTS:
- Extract ALL specific details from FIR: names, dates, times, locations, quantities, exhibit numbers, seal numbers
- Reference specific NDPS sections and compliance points
- Use formal legal language
- Be precise and factual - no speculation
- Present the prosecution case persuasively but accurately
- If accused is a juvenile, mention it in case title and address JJ Act implications

Generate the court summary now:
"""
    
    # Generate summary with structured output
    @exponential_backoff_retry(max_retries=5, max_wait=60)
    def _generate_summary():
        return llm_model.with_structured_output(SummaryForTheCourt).invoke(content_for_llm)
    
    result = _generate_summary()
    
    logger.info(f"Generated summary for the court: {result.case_title}")

    # Convert Pydantic model to dict for JSON serialization
    return {
        "summary_for_the_court": result.model_dump()
    }
