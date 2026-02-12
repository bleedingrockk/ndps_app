from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from typing import List, Dict
from app.utils.retry import exponential_backoff_retry
from app.utils.format_cases import format_historical_cases_for_prompt
import logging
import json

logger = logging.getLogger(__name__)

prompt = """ Mismatch of document:
Mismatch between timing of receipt of information, interception, recovery, seizure, search in follow up action, preparation of test memo, recording of statements leads to failure of a case. If these documents are prepared with care ensuring that the times do not mismatch, the conviction rate can go up significantly.

Improper affixation of Seal:
Courts attribute a great deal of importance to the affixation of proper seal on the seized exhibits. Defective/broken seals creates doubt on the seizure of exhibits.

Non compliance of provisions of Section 50:
Not giving the accused an opportunity to be searched before a Gazetted Officer or Magistrate as per Section 50, or not recording the fact that this opportunity has been given to the suspect, is one of the main reasons for failure of prosecution. Sometimes, the language used in notice under section 50 of NDPS Act is not known to the accused.

Loopholes in recovery proceedings:
a) Independent public witnesses are not joined during recovery  
b) No videography/photography of recovery proceedings is done  
c) Recovery of case property from open place creates doubt on recovery proceedings  
d) Female officers are not joined in search of a house where there are females  

Procedural lacunae in investigation:
a) Seal after use is not handed over to independent witness  
b) Handed over memo of seal is not prepared  
c) Sketch of site plan, seizure memo/arrest memo does not bear the signature of witness/complainant  
d) Pullanda is not sealed properly  
e) Reason for mentioning the details of FIR over seizure memo is not given  
f) Arrival/departure entries of raiding team/IO are not placed on record  

Failure to examine material witness:
Sometimes it becomes difficult to examine a material witness as either he is from a foreign country or is no more residing at his old address and his current address is not available.

Courts are laying more emphasis on technical evidence but IOs lack scientific temper, hence:
a) Proper evidence not collected from the scene of crime  
b) Lack of proper training in handling/packaging/sealing the exhibits  
c) Delay in sending exhibits to FSL  
d) Non-collection of digital evidence as per mandate of law  

Delay in sending samples for testing.

Inadequate evidence to link the consignment to the suspect.

Lack of coordination and interaction:
The lack of coordination between the IO and the SPP causes communication gap and may result in acquittal. The Investigation Officer should brief the SPP properly and ensure that the SPP himself and not one of his juniors attends the case and argues it properly.

Lack of proper pairvi strategy:
Usually the focus of IOs remains on the case up to the filing of charge-sheet. Thereafter, no effective pairvi of cases is made:
a) To ensure timely presence of primary/star witnesses  
b) For proper and advance briefing of witnesses including police witnesses before deposition in Court  
c) To ensure production of case property / filing of statutory sanction in Court  

Witnesses not being briefed properly:
If the witnesses are not briefed properly, they may make inaccurate and vague statements resulting in contradictions and failure of prosecution.
"""

class POINTS(BaseModel):
    """Individual weakness point with heading and details"""
    point_heading: str = Field(
        description="Brief heading summarizing the potential prosecution weakness"
    )
    points: str = Field(
        description="Detailed explanation of the weakness and how it could impact the case"
    )

class PotentialProsecutionWeaknesses(BaseModel):
    """Complete potential prosecution weaknesses for the case"""
    points: List[POINTS] = Field(
        description="List of potential prosecution weaknesses based on FIR content and guidelines",
        max_length=15
    )

def generate_potential_prosecution_weaknesses(state: WorkflowState) -> dict:
    """
    Generate potential prosecution weaknesses from FIR content and prosecution guidelines.
    """
    logger.info("Starting Potential Prosecution Weaknesses generation")
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for prosecution weaknesses generation")
    
    pdf_content = state["pdf_content_in_english"]
    
    # Get historical cases if available
    historical_cases = state.get("historical_cases", [])
    historical_cases_text = format_historical_cases_for_prompt(historical_cases)

    # Construct content for LLM
    content_for_llm = f"""Based on the following FIR content, prosecution guidelines, and relevant historical cases, identify potential prosecution weaknesses that could affect this case:

{historical_cases_text}
FIR Content:
{pdf_content}

PROSECUTION GUIDELINES AND COMMON WEAKNESSES:
{prompt}

Analyze the FIR content against these common prosecution weaknesses and the provided historical cases. For each relevant weakness you identify:
1. Provide a clear heading describing the weakness
2. Explain specifically how this weakness applies to the current case
3. Reference specific details from the FIR that indicate this potential weakness
4. Where relevant, reference the provided historical cases that illustrate similar weaknesses that led to acquittals or case failures

USE THE PROVIDED HISTORICAL CASES: Reference the actual historical cases provided above to illustrate how similar weaknesses affected other cases. For example: "As seen in Case 1: [case title], failure to [weakness] resulted in [outcome]..."

Generate a comprehensive list of potential prosecution weaknesses that investigators should address to strengthen the case."""
    
    # Generate prosecution weaknesses with structured output
    @exponential_backoff_retry(max_retries=5, max_wait=60)
    def generate_weaknesses():
        return llm_model.with_structured_output(PotentialProsecutionWeaknesses).invoke(content_for_llm)
    
    prosecution_weaknesses = generate_weaknesses()
    
    logger.info(f"Generated {len(prosecution_weaknesses.points)} potential prosecution weaknesses")
    
    # Convert to dict with heading as key and details as value
    weaknesses_dict = {
        point.point_heading: point.points
        for point in prosecution_weaknesses.points
    }
    
    # Return updated state
    return {
        "potential_prosecution_weaknesses": weaknesses_dict
    }