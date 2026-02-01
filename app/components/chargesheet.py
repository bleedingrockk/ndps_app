from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from typing import List
from app.utils.retry import exponential_backoff_retry
import logging

logger = logging.getLogger(__name__)

class Chargesheet(BaseModel):
    """Chargesheet for NDPS case prosecution"""
    case_title: str = Field(description="Case title in format: STATE OF [STATE] vs. [ACCUSED NAME] (with any relevant qualifiers like JUVENILE, etc.)")
    ndps_sections: List[str] = Field(description="List of most relevant NDPS Act sections applicable to the case")
    bns_sections: List[str] = Field(description="List of most relevant BNS sections applicable to the case (if any)")
    bnss_sections: List[str] = Field(description="List of most relevant BNSS sections applicable to the case (if any)")
    bsa_sections: List[str] = Field(description="List of most relevant BSA sections applicable to the case (if any)")
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

def generate_chargesheet(state: WorkflowState) -> dict:
    """
    Generate a comprehensive chargesheet for NDPS case prosecution.
    """
    logger.info("Starting chargesheet generation")
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for chargesheet generation")
    
    pdf_content = state["pdf_content_in_english"]
    
    # Get FIR facts if available
    fir_facts = state.get("fir_facts", {})
    
    # Get all legal sections
    ndps_sections = state.get("ndps_sections_mapped", [])
    bns_sections = state.get("bns_sections_mapped", [])
    bnss_sections = state.get("bnss_sections_mapped", [])
    bsa_sections = state.get("bsa_sections_mapped", [])
    
    # Format sections for LLM
    def format_sections(sections_list, act_name):
        if not sections_list:
            return "None"
        formatted = []
        for section in sections_list:
            if isinstance(section, dict):
                section_num = section.get('section_number', '')
                description = section.get('section_description', '')[:100]  # Truncate for context
                if section_num:
                    formatted.append(f"Section {section_num}: {description}")
        return "\n".join(formatted) if formatted else "None"
    
    ndps_sections_text = format_sections(ndps_sections, "NDPS")
    bns_sections_text = format_sections(bns_sections, "BNS")
    bnss_sections_text = format_sections(bnss_sections, "BNSS")
    bsa_sections_text = format_sections(bsa_sections, "BSA")
    
    # Construct content for LLM
    content_for_llm = f"""You are an expert NDPS Act prosecutor preparing a comprehensive chargesheet for a criminal case.

Your task is to analyse the FIR content and available legal sections, then generate a **professional chargesheet** that presents the prosecution's case clearly and persuasively.

You MUST strictly follow these rules:

1. Base every point ONLY on the facts available in the FIR.
2. Select ONLY the MOST RELEVANT sections from each Act (NDPS, BNS, BNSS, BSA) based on the FIR facts.
3. Do NOT include sections that are not directly applicable to this specific case.
4. Extract specific details: names, dates, times, locations, quantities, sections, procedural compliance points
5. Frame the case in a legally sound and persuasive manner
6. Use formal legal language appropriate for court documents
7. Structure the output exactly as per the schema provided

### FIR CONTENT:
{pdf_content}

### AVAILABLE LEGAL SECTIONS:

**NDPS Act Sections:**
{ndps_sections_text}

**BNS (Bharatiya Nyaya Sanhita) Sections:**
{bns_sections_text}

**BNSS (Bharatiya Nagarik Suraksha Sanhita) Sections:**
{bnss_sections_text}

**BSA (Bharatiya Sakshya Adhiniyam) Sections:**
{bsa_sections_text}

### ADDITIONAL CONTEXT:
"""
    
    # Add FIR facts if available
    if fir_facts:
        content_for_llm += f"\n### FIR FACTS:\n"
        for key, value in fir_facts.items():
            content_for_llm += f"- {key}: {value}\n"
    
    content_for_llm += f"""

### INSTRUCTIONS FOR GENERATING CHARGESHEET:

1. **Case Title**: Format as "STATE OF [STATE NAME] vs. [ACCUSED NAME]" with qualifiers like "(JUVENILE)" if applicable. Extract state and accused name from FIR.

2. **Section Selection**: Select ONLY the most relevant sections from each Act:
   - **NDPS Sections**: Include sections for possession, quantity classification, conspiracy if applicable. Usually 2-5 sections.
   - **BNS Sections**: Include only if there are general criminal law provisions applicable (e.g., conspiracy, attempt). May be empty if not applicable.
   - **BNSS Sections**: Include only if there are procedural provisions applicable (e.g., search, seizure, arrest procedures). May be empty if not applicable.
   - **BSA Sections**: Include only if there are evidence-related provisions applicable. May be empty if not applicable.
   
   IMPORTANT: Only include sections that are DIRECTLY relevant to this specific case based on FIR facts. Do not include generic or marginally relevant sections.

3. **Core Issue**: Frame as a question that captures the central legal question the court must decide. Example: "Whether the accused was found in conscious and exclusive possession of [quantity] of [substance], in compliance with mandatory NDPS safeguards, warranting prosecution under NDPS Act."

4. **Date and Place**: "DD.MM.YYYY, [Location]" format extracted from FIR.

5. **Recovery**: Description of what was recovered, from where, quantity - be specific with details from FIR.

6. **Quantity**: Classification (small/intermediate/commercial) and actual quantity with legal implications.

7. **Safeguards**: List of compliance points (e.g., "Section 50 NDPS – explained & waived", "Section 43 NDPS – public place search", "Videography & sealing done contemporaneously")

8. **Conscious Possession Proven**: List of facts proving conscious possession (admissions, exclusive custody, no licence, corroborating evidence like train tickets, etc.)

9. **Procedural Compliance**: List of procedural safeguards complied with (sections, documentation, chain of custody, FSL status)

10. **Legal Position**: List of legal points supporting prosecution (jurisdiction, applicability of sections, precedent if relevant, juvenile law position if applicable)

11. **Judicial Balance**: Write 2-3 sentences that balance the seriousness of the offence with any mitigating factors, public interest, and legal principles. Acknowledge both prosecution and defence perspectives where appropriate.

12. **Prosecution Prayer**: List specific requests to the court, typically:
   - "Cognizance of offence"
   - "Framing of charges"
   - "Bail to be denied in interest of justice" (if applicable)
   - "Trial to proceed under [relevant Act] with NDPS rigour preserved"

### CRITICAL REQUIREMENTS:
- Extract ALL specific details from FIR: names, dates, times, locations, quantities, exhibit numbers, seal numbers
- Select ONLY the most relevant sections - quality over quantity
- Reference specific NDPS sections and compliance points
- Use formal legal language
- Be precise and factual - no speculation
- Present the prosecution case persuasively but accurately
- If accused is a juvenile, mention it in case title and address JJ Act implications
- If no relevant sections from BNS/BNSS/BSA, return empty lists

Generate the chargesheet now:
"""
    
    # Generate chargesheet with structured output
    @exponential_backoff_retry(max_retries=5, max_wait=60)
    def _generate_chargesheet():
        return llm_model.with_structured_output(Chargesheet).invoke(content_for_llm)
    
    result = _generate_chargesheet()
    
    logger.info(f"Generated chargesheet: {result.case_title}")

    # Convert Pydantic model to dict for JSON serialization
    return {
        "chargesheet": result.model_dump()
    }
