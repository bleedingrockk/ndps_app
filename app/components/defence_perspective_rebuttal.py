from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from typing import List
from app.utils.retry import exponential_backoff_retry
from app.utils.format_cases import format_historical_cases_for_prompt
import logging
import json

logger = logging.getLogger(__name__)

class DefencePerspectiveRebuttal(BaseModel):
    """Case-specific defence perspective and rebuttal pair"""
    defence_perspective: List[str] = Field(
        description="Case-specific defence arguments that reference specific details from the FIR (names, dates, locations, quantities, exhibit numbers, etc.). Each argument must be actionable and tied to this particular case's facts, evidence, accused, witnesses, dates, and legal requirements."
    )
    rebuttal: List[str] = Field(
        description="Case-specific prosecution rebuttals that reference specific details from the FIR (names, dates, locations, quantities, exhibit numbers, etc.). Each rebuttal must be actionable and tied to this particular case's facts, evidence, accused, witnesses, dates, and legal requirements."
    )
    
class DefencePerspectiveRebuttalList(BaseModel):
    defence_perspective_rebuttal: List[DefencePerspectiveRebuttal] = Field(
        description="List of defence perspective and rebuttal pairs"
    )
def generate_defence_perspective_rebuttal(state: WorkflowState) -> dict:
    """
    Generate defence perspective and rebuttal from FIR content and forensic guidelines.
    """
    logger.info("Starting defence perspective and rebuttal generation")
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for defence perspective and rebuttal generation")
    
    pdf_content = state["pdf_content_in_english"]
    
    # Get historical cases if available
    historical_cases = state.get("historical_cases", [])
    historical_cases_text = format_historical_cases_for_prompt(historical_cases)
    
    # Construct content for LLM
    content_for_llm = f"""You are an expert NDPS Act criminal law analyst, trial lawyer, and prosecution strategy advisor with deep knowledge of Supreme Court and High Court NDPS jurisprudence.

Your task is to analyse the FIR content provided below and generate a **case-specific Defence Perspective and corresponding Prosecution Rebuttal**.

You MUST strictly follow these rules:

1. Base every point ONLY on the facts available in the FIR.
2. Each defence point must mirror real NDPS acquittal grounds recognised by Indian courts.
3. Each rebuttal must show how the prosecution can legally, factually, and procedurally counter that defence.
4. Avoid generic statements. Every point must reference FIR-specific details such as:
   - names of accused/witnesses
   - dates and times
   - place of recovery
   - quantity and nature of contraband
   - seal numbers, exhibit numbers
   - sections of NDPS Act
5. USE THE PROVIDED HISTORICAL CASES: Reference the actual historical cases provided below that illustrate:
   - Successful defence arguments that led to acquittals (for defence perspective)
   - Prosecution strategies that successfully countered defence arguments (for rebuttal)
   - Legal precedents that establish procedural requirements or evidentiary standards
   - Case law that clarifies what constitutes valid compliance or non-compliance
   - Examples of cases where similar facts resulted in conviction or acquittal
6. Structure the output exactly as per the schema:
   - defence_perspective: list of defence arguments (cite the provided historical cases where applicable)
   - rebuttal: list of prosecution counter-arguments (cite the provided historical cases where applicable)

### You must consider and intelligently apply ALL the following recognised REASONS OF ACQUITTAL IN NDPS ACT CASES while generating defence and rebuttal:

A. **Mismatch of documents and timelines**
   - Timing mismatch between secret information, interception, recovery, seizure, arrest, rukka, FIR, test memo, and statements.

B. **Improper or defective sealing**
   - Broken/defective seals
   - Seal not legible
   - Seal not handed over to independent witness
   - No seal handing-over memo

C. **Non-compliance of Section 50 NDPS Act**
   - No option given for Gazetted Officer/Magistrate
   - Improper or ambiguous Section 50 notice
   - Language of notice not understood by accused
   - Non-recording of refusal/consent

D. **Loopholes in recovery proceedings**
   - Non-joining of independent public witnesses
   - No videography/photography
   - Recovery from open/public place
   - Absence of female officer during search involving females

E. **Procedural lacunae in investigation**
   - Unsealed or improperly sealed pullandas
   - FIR number mentioned on seizure memo without explanation
   - Missing signatures on seizure memo/site plan/arrest memo
   - Missing arrival/departure DD entries of raiding party

F. **Failure to examine material witnesses**
   - Non-examination of public witnesses
   - Missing link witnesses
   - Witnesses unavailable without explanation

G. **Weak scientific and technical evidence**
   - Delay in sending samples to FSL
   - Improper handling/packaging of samples
   - No FSL forwarding memo
   - No digital evidence where legally required
   - Lack of scientific linkage to accused

H. **Delay in sending samples for testing**

I. **Failure to establish conscious possession**
   - No proof linking accused to contraband
   - Recovery not from exclusive possession
   - No ownership/control evidence

J. **Lack of coordination with Special Public Prosecutor**
   - Investigation gaps not cured during trial
   - Sanction issues
   - Improper legal briefing

K. **Poor pairvi (trial follow-up)**
   - Star witnesses not produced on time
   - Case property not produced
   - Sanction orders missing

L. **Witnesses not properly briefed**
   - Contradictions between statements
   - Vague or inconsistent testimony

### Output expectations:
- Defence Perspective: Argue how the above lapses create doubt and favour acquittal. Reference the provided historical cases where similar procedural lapses led to acquittals (e.g., "As seen in Case 1: [case title from above], failure to comply with Section 50 resulted in acquittal...", "Following the precedent in Case 2: [case title from above], the defence can argue that...")
- Rebuttal: Show how prosecution can neutralise the defence using FIR facts, legal presumptions (Sections 35, 54 NDPS Act), explanations, and case-law-consistent reasoning. Cite the provided cases where prosecution successfully countered similar defence arguments (e.g., "As established in Case 3: [case title from above], the prosecution can establish...", "As seen in Case 4: [case title from above], the court clarified that...", "Following Case 5: [case title from above], the prosecution can argue that...")

### Incorporating the Provided Historical Cases:
- For Defence Perspective: Cite the provided cases where similar procedural defects, non-compliance, or evidentiary gaps led to acquittals. Reference specific case titles and summaries from the provided historical cases.
- For Rebuttal: Cite the provided cases where prosecution successfully overcame similar challenges, established compliance, or where courts upheld convictions despite defence arguments. Reference specific case titles and summaries from the provided historical cases.

### Tone:
- Formal legal language
- Court-ready
- Practical and realistic
- No speculation beyond FIR
- Authoritative with citations to the provided historical cases where relevant

{historical_cases_text}
### FIR CONTENT:
{pdf_content}

"""
    
    # Generate defence perspective and rebuttal with structured output
    @exponential_backoff_retry(max_retries=5, max_wait=60)
    def _generate_defence_perspective_rebuttal():
        return llm_model.with_structured_output(DefencePerspectiveRebuttalList).invoke(content_for_llm)
    
    result = _generate_defence_perspective_rebuttal()
    
    # Extract the list from the result
    defence_perspective_rebuttal_list_data = result.defence_perspective_rebuttal if hasattr(result, 'defence_perspective_rebuttal') else []
    
    total_items = len(defence_perspective_rebuttal_list_data)
    logger.info(f"Generated {total_items} defence perspective and rebuttal pairs")

    # Return updated state
    return {
        "defence_perspective_rebuttal": defence_perspective_rebuttal_list_data
    }