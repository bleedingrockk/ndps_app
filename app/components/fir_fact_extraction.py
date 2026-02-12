from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from typing import List

class FirFactField(BaseModel):
    field_name: str = Field(
        description="Name of the fact category (e.g., 'Date, Time and Location', 'Search and Seizure')"
    )
    field_description: str = Field(
        description="Detailed description of the facts extracted from the FIR for this category. Must be between 40-100 words. Use markdown bold (**text**) for important details."
    )

class FirFactExtraction(BaseModel):
    facts: List[FirFactField] = Field(
        description="List of relevant fact categories extracted from the FIR. Only include categories that have substantial information in the FIR.",
        min_items=1,
        max_items=15
    )

def extract_fir_fact(state: WorkflowState) -> dict:
    """
    Extract FIR facts from translated PDF content using structured output.
    Works as a LangGraph node that accepts state and returns updated state.
    
    Args:
        state: WorkflowState containing pdf_content_in_english
        
    Returns:
        Dictionary with FIR facts added to state
        
    Raises:
        ValueError: If pdf_content_in_english is missing
        Exception: If extraction fails
    """
    import logging
    import sys
    logger = logging.getLogger(__name__)
    logger.info("🔍 [extract_fir_fact] Starting FIR fact extraction...")
    sys.stdout.flush()
    
    if not state.get("pdf_content_in_english"):
        logger.error("❌ [extract_fir_fact] pdf_content_in_english is missing")
        sys.stdout.flush()
        raise ValueError("pdf_content_in_english is required for FIR fact extraction")
    
    pdf_content = state["pdf_content_in_english"]
    logger.debug(f"📄 [extract_fir_fact] Processing FIR content ({len(pdf_content)} characters)")
    sys.stdout.flush()

    try:
        prompt = f"""Extract relevant factual information from the FIR text below.

CRITICAL REQUIREMENTS:
1. Extract ONLY facts directly stated in the FIR text - do not add, interpret, or infer anything
2. Each field description must contain between 40-100 words
3. Do NOT add legal interpretations, conclusions, or assumptions not explicitly stated in the FIR
4. ONLY include fact categories that are ACTUALLY PRESENT and RELEVANT in this FIR
5. **INCLUDE NAMES OF PEOPLE** (accused, witnesses, officers, informants, etc.) when mentioned in the FIR - at least one name should appear in the facts if names are present in the FIR
6. Use markdown bold formatting (**text**) to highlight important information such as:
   - **Names of people** (accused, witnesses, officers, informants, etc.) - MUST include if mentioned
   - Dates, times, locations
   - Section numbers, legal references
   - Quantities, amounts, measurements
   - Key actions, procedures, or facts directly mentioned

POSSIBLE FACT CATEGORIES (include only if relevant and explicitly mentioned in FIR):

1. **Date, Time and Location**
   - Exact date, time and place of incident
   - Train/station/platform/vehicle details if mentioned

2. **Initial Detention/Interception**
   - How the accused was first intercepted or detained
   - Suspicion, behaviour, dog sniff, public tip-off, etc.

3. **Identity of Accused**
   - **Name** (MUST include if mentioned in FIR), age, gender, address, occupation of accused
   - Physical description if mentioned

4. **Police Order and Transport**
   - Which officer was informed (include **name and designation** if mentioned) and instructions given
   - How the accused was taken to police station

5. **Presence of Required Officer** (ONLY if applicable)
   - Presence of Child Welfare Officer if accused is a minor
   - Presence of woman police officer if accused is female
   - Include **name and designation** if mentioned (MUST include if present in FIR)
   - SKIP this category if accused is adult male or if no such officer is mentioned

6. **Search and Seizure**
   - Legal procedure of search and consent
   - Section 50 compliance (if applicable)
   - Items recovered from person, bags, or location
   - Search witnesses if mentioned

7. **Weighment and Packaging**
   - Details of weighing and field testing
   - Total quantity recovered
   - Sealing, marking of exhibits
   - Packaging method

8. **Procedural Documentation**
   - Sampling rules and procedures
   - Documentation maintained
   - Videography/photography
   - Signatures and witnesses

9. **Statement of Accused**
   - Voluntary disclosure by accused
   - Source, purpose, payment details
   - Intended delivery or destination

10. **Offences Charged**
    - Sections of law applied (NDPS, BNS, IPC, etc.)
    - Specific charges mentioned

11. **Evidence and Forensic Details**
    - Laboratory testing mentioned
    - Chemical analysis or field tests
    - Sample collection procedure

12. **Witnesses**
    - **Names and roles of witnesses** (MUST include names if mentioned in FIR)
    - Independent witnesses if mentioned

13. **Contraband Details**
    - Type and description of seized items
    - Packaging and concealment method
    - Physical characteristics

14. **Rights Information**
    - Whether accused was informed of rights
    - Lawyer notification if mentioned

15. **Other Relevant Facts**
    - Any other significant facts from the FIR not covered above

FIR Text:
{pdf_content}

OUTPUT FORMAT (valid JSON):
{{
  "facts": [
    {{
      "field_name": "Date, Time and Location",
      "field_description": "Extract 40-100 words of facts with **bold** for important details..."
    }},
    {{
      "field_name": "Search and Seizure",
      "field_description": "Extract 40-100 words of facts with **bold** for important details..."
    }}
  ]
}}

INSTRUCTIONS:
- Only include categories that have substantial information explicitly stated in the FIR
- Skip categories that are not applicable or not mentioned
- Each field_description must be 40-100 words
- Use only facts directly from the FIR text
- **MUST include names of people** (accused, witnesses, officers, informants, etc.) when mentioned in the FIR - at least one name should appear in the extracted facts if names are present in the FIR
- Make important details bold using **text** syntax, especially names of people
- Return valid JSON only
"""
        
        # Use structured output to get Pydantic model
        llm_with_structured_output = llm_model.with_structured_output(FirFactExtraction)
        response = llm_with_structured_output.invoke(prompt)
        
        # Convert list of FirFactField to dictionary format
        fir_facts = {}
        for fact in response.facts:
            # Clean field name to make it a valid dict key
            key = fact.field_name.lower().replace(" ", "_").replace(",", "").replace("/", "_")
            fir_facts[key] = fact.field_description
        
        logger.info(f"✅ [extract_fir_fact] Extracted {len(fir_facts)} fact categories")
        sys.stdout.flush()
        
        return {
            "fir_facts": fir_facts
        }
    
    except Exception as e:
        logger.error(f"❌ [extract_fir_fact] Error: {str(e)}")
        sys.stdout.flush()
        raise Exception(f"Error extracting FIR facts: {str(e)}")