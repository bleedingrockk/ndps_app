from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from typing import List
from app.rag.query_all import query_forensic
from app.utils.retry import exponential_backoff_retry
from app.utils.format_cases import format_historical_cases_for_prompt
import logging

logger = logging.getLogger(__name__)

class EvidenceChecklist(BaseModel):
    evidence_checklist: str = Field(
        description="Formatted evidence checklist as a single string with bullet points and descriptions"
    )

class InvestigationCheckpoints(BaseModel):
    investigation_checkpoints: List[str] = Field(
        description="List of investigation checkpoints extracted from the FIR text. Each checkpoint must be something that needs to be investigated or verified. Maximum 10 high-quality checkpoints.",
        max_items=10
    )

def generate_evidence_checklist(state: WorkflowState) -> dict:
    """
    Generate comprehensive evidence checklist from FIR content and forensic guidelines.
    """
    logger.info("Starting evidence checklist generation")
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for evidence checklist generation")
    
    pdf_content = state["pdf_content_in_english"]
    logger.debug(f"FIR content length: {len(pdf_content)} characters")
    
    # Get historical cases if available
    historical_cases = state.get("historical_cases", [])
    historical_cases_text = format_historical_cases_for_prompt(historical_cases)
    
    llm_with_structured_output = llm_model.with_structured_output(InvestigationCheckpoints)
    
    prompt = f"""
You are an expert in forensic investigation procedures for NDPS cases.

Task: Identify investigation gaps and procedural verification points from the FIR text below.

Rules:
- Extract 6-10 investigation checkpoints that need verification or completion.
- Focus on: missing procedures, incomplete documentation, evidence handling steps, timeline gaps, witness requirements, legal compliance points.
- Frame each point as something that needs to be INVESTIGATED or VERIFIED, not just stated facts.
- Prioritize actionable items that an investigating officer should check or complete.
- Examples of good extraction:
  ✓ "Verify if Section 50 notice was served in writing"
  ✓ "Confirm presence of lady officer during search procedures"
  ✗ "Bundles of ganja were found" (this is just a fact)

FIR Text:
{pdf_content}

Output: List investigation checkpoints that need verification/action."""

    response = llm_with_structured_output.invoke(prompt)
    checkpoints = response.investigation_checkpoints
    logger.info(f"Extracted {len(checkpoints)} investigation checkpoints")
    
    # Collect all forensic guidelines for comprehensive analysis
    all_guidelines_text = ""
    
    for idx, checkpoint in enumerate(checkpoints, 1):
        logger.debug(f"Processing checkpoint {idx}/{len(checkpoints)}")
        results = query_forensic(checkpoint, k=5)
        logger.debug(f"Found {len(results)} relevant guidelines for checkpoint {idx}")
        
        # Format retrieved guidelines
        for i, result in enumerate(results):
            chunk = result['chunk']
            chapter = chunk.get('chapter', 'N/A')
            chapter_title = chunk.get('chapter_title', 'N/A')
            headings = chunk.get('headings', [])
            content = chunk['content']
            page_number = chunk.get('page_number')
            source_url = chunk.get('source_url')
            pdf_name = chunk.get('pdf_name', 'N/A')
            
            all_guidelines_text += f"\n--- Checkpoint {idx}: {checkpoint} ---\n"
            all_guidelines_text += f"Chapter: {chapter} - {chapter_title}\n"
            if headings:
                all_guidelines_text += f"Headings: {' > '.join(headings) if isinstance(headings, list) else headings}\n"
            all_guidelines_text += f"Source: Page {page_number if page_number is not None else 'N/A'}\n"
            if source_url:
                all_guidelines_text += f"Source URL: {source_url}\n"
            all_guidelines_text += f"Document: {pdf_name}\n"
            all_guidelines_text += f"Content:\n{content}\n"
            all_guidelines_text += "-" * 80 + "\n"
    
    # Generate comprehensive evidence checklist
    llm_with_checklist_output = llm_model.with_structured_output(EvidenceChecklist)
    
    checklist_prompt = f"""
You are an expert forensic investigator and legal consultant for NDPS cases.

{historical_cases_text}
FIR Content:
{pdf_content}

Forensic Guidelines Retrieved:
{all_guidelines_text}

Task: Create a COMPREHENSIVE EVIDENCE CHECKLIST with critical items and admissibility requirements.

USE THE PROVIDED HISTORICAL CASES: Reference the actual historical cases provided above that illustrate:
- Evidence admissibility requirements and standards
- Cases where evidence was rejected due to procedural lapses
- Successful prosecution strategies based on proper evidence handling
- Legal precedents on chain of custody, sealing, sampling, and witness requirements
- Case law that clarifies what makes evidence admissible or inadmissible in NDPS cases

Output Format (EXACT - Use Markdown formatting):
## Evidence Checklist (Critical Items & Admissibility)

### Physical Evidence
- **Evidence Name**: Detailed description (3-5 sentences) covering:
  * Its importance and role in establishing the case
  * Chain of custody requirements and procedures
  * Admissibility formalities and legal compliance requirements
  * Specific details from FIR (exhibit numbers, dates, witness names, locations, quantities, times)
  * Potential weaknesses or compliance gaps that could affect admissibility
  * Reference to historical cases if relevant

### Documentary Evidence
- **Evidence Name**: [Same detailed format as above]

### Forensic Evidence
- **Evidence Name**: [Same detailed format as above]

### Electronic Evidence
- **Evidence Name**: [Same detailed format as above]

### Witness Evidence
- **Evidence Name**: [Same detailed format as above]

### Procedural Compliance Records
- **Evidence Name**: [Same detailed format as above]

EXAMPLE FORMAT:
 - Seized Ganji Bundles: The 5 bundles weighing 25.5 kg (exhibits Mark-A,B) seized on 15-Jan-2024 at 14:30 hrs at Secunderabad Railway Station Platform No. 3 are primary evidence. Must be sealed and stored with clear chain of custody. Admissibility requires all seizure formalities (panchnama, seals, signatures) be impeccable.
 - Seizure Panchnama & Inventory: Documented panchnama dated 15-Jan-2024 (with RPF officers SI Ramesh Kumar and CWO Priya Sharma as panchas) showing marking of each bundle at the scene is crucial. It must note exact date/time (14:30 hrs), precise location (Platform 3, near coach S-7), and witness signatures. Any lapse (e.g. missing signature of pancha Priya Sharma) could raise doubts.

EVIDENCE CATEGORIES TO COVER:
- Physical evidence (seized contraband, packaging, seals, exhibits)
- Documentary evidence (panchnama, inventory, tickets, receipts, arrest memos)
- Forensic reports (FSL certificate, field tests, fingerprints, DNA analysis)
- Electronic evidence (mobile phones, SIM cards, digital records with Sec.65B compliance)
- Witness statements (police, RPF, CWO, independent witnesses, panchas)
- Procedural compliance records (Sec.50 waiver, Sec.43 consent, search warrants)
- Accused's statements (confessions, admissions with voluntariness verification)
- Age verification documents (birth certificate, school records for juvenile cases)
- Supporting circumstantial evidence (travel records, cash, communications)
- Legal notices and compliance documentation

REQUIREMENTS:
- Organize evidence into clear categories (Physical, Documentary, Forensic, Electronic, Witness, Procedural Compliance)
- Each bullet point should be ONE evidence item with its name in **bold** followed by colon
- Write detailed paragraph descriptions (3-5 sentences minimum per item) covering all aspects
- MANDATORY: Include SPECIFIC details from FIR in EVERY point - names of accused/witnesses, exact dates, times, locations, quantities, exhibit numbers, case numbers, station names
- Include specific legal sections (NDPS Sec.50, Evidence Act Sec.65B, etc.)
- Mention chain of custody, sealing procedures, witness requirements
- Note potential weaknesses or compliance gaps that could affect admissibility
- Reference concrete FIR details (not generic placeholders)
- Cover 15-20 evidence items comprehensively across all categories
- Use actual names, numbers, and specifics from the FIR wherever available
- Use proper Markdown formatting with headers, bold text, and bullet points for better readability
- INCORPORATE THE PROVIDED HISTORICAL CASES: Where relevant, cite the actual historical cases provided above that illustrate:
  * Evidence admissibility standards (e.g., "As seen in Case 1: [case title from above], the panchnama must...")
  * Cases where evidence was rejected (e.g., "In Case 2: [case title from above], the court rejected evidence because...")
  * Successful prosecution precedents (e.g., "Following Case 3: [case title from above], ensure that...")
  * Legal requirements established by courts (e.g., "As established in Case 4: [case title from above], the court held that...")
- Use the provided case citations to strengthen the importance and admissibility requirements of each evidence item

End with:
(Legal importance: Each piece ties the accused to possession for sale. NDPS requires physical possession + intent to traffic. The combination of large quantity, travel documents, cash, and confession strongly establishes intent. Proper packaging and sealing with video/photos under e-Sakshya provides chain-of-custody.)

Output the complete formatted checklist as a single text string."""


    @exponential_backoff_retry(max_retries=5, max_wait=60)
    def _invoke_generate_checklist():
        return llm_with_checklist_output.invoke(checklist_prompt)
    
    checklist_response = _invoke_generate_checklist()
    evidence_checklist = checklist_response.evidence_checklist
    
    logger.info(f"Generated evidence checklist")
    
    print("🍺")
    print(evidence_checklist)
    
    return {
        "evidence_checklist": evidence_checklist
    }