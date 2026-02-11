from typing import List, Optional
from pydantic import BaseModel
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from app.utils.retry import exponential_backoff_retry
import logging

logger = logging.getLogger(__name__)

class PlanPoint(BaseModel):
    title: str                 # e.g. "Immediate Action"
    date_range: Optional[str]  # e.g. "19/09/2025" or "19–20 Sep"
    description: str           # Full paragraph of actions

class InvestigationPlan(BaseModel):
    points: List[PlanPoint]


PROMPT = """
You are a senior Indian criminal law expert and investigation officer.

You must strictly follow the official NDPS procedural guidance given below while preparing the investigation plan.

========================
OFFICIAL NDPS INVESTIGATION GUIDELINES
========================

PUNISHMENT SYSTEM UNDER NDPS ACT:

The Narcotic Drugs and Psychotropic Substances Act, 1985 views drug offences very seriously and prescribes stringent penalties. The Act follows a graded system of punishment varying with the recovered quantities (small, commercial and intermediate quantity) as defined in the act of narcotic drugs and psychotropic substances. The punishment prescribed for different quantities is as follows:

Small quantity: Rigorous imprisonment for a term which may extend to "one year", or with fine which may extend to Rs.10,000 or with both.

Intermediate quantity: Rigorous imprisonment for a term which may extend to ten years and with fine which may extend to Rs. 1,00,000.

Commercial quantity: Rigorous imprisonment for a term which shall not be less than ten years but which may extend to twenty years and shall also be liable to fine which shall not be less than Rs. 1,00,000 but which may extend to Rs. 2,00,000. Provided that the court may for reasons to be recorded in the judgement impose a fine exceeding 2 lakh rupees.

MANDATORY COMPLIANCES:

SECTION 41 (Issue of warrant/authorization by a Magistrate or a G.O.):
Section 41 of the Act empowers a Magistrate or a Gazetted Officer to issue a warrant/authorization for a search and seizure. Such authorization has to be based on information taken down in writing. If G.O. himself has to carry out search or to conduct raid under section 41, it is not necessary for him to get any authorization from other G.O.

SECTION 42 (Search, Seizure & Arrest at private place without authorization/warrant):
This section relates to entry into and search of any building, conveyance or enclosed place without a warrant/an authorization.
a) During day time any empowered officer is authorized to conduct search, seizure and arrest.
b) During night time any empowered officer is authorized to conduct search, seizure and arrest only after recording his satisfaction for non-compliance of section 41.
c) Any SI can search any licensed manufacturing unit.
However this section should not be invoked and a warrant/authorization as per section 41 of NDPS Act should mandatorily be obtained.

SECTION 50:
Section 50 of the NDPS Act provides the provisions of personal search of a person suspected to be carrying NDPS drugs on him. The section mandates:
i. Any person who is intended to be searched has a right to be searched before a gazette officer or a magistrate.
ii. It is the responsibility of the empowered officer to apprise the person in writing of his right to be searched before the nearest Gazetted Officer or a Magistrate. The denial should also be recorded. The right does not apply to search of bags being carried by the person; it applies only to search of his person as expounded by the Apex court/High courts in several judgements.

SECTION 51 (Procedure of Search, Seizure and Arrest):
a) Search – Search to be in front of two independent witnesses, search of self and search party before accused and independent witnesses.
b) Seizure – Empowered Officer should ascertain the genuineness and the quantity of the recovered contraband and proceed to draw a Seizure Memo. As per Notification 899 E dated 23.12.2022 Seizure, Storage, Sampling and Disposal Rule 2022 seized items to be brought to the nearest Magistrate.
c) Arrest – as defined under section 52 and draw an arrest memo as per u/s 49 of BNSS previously u/s 46 of Cr.PC.

SECTION 52 (Grounds of Arrest):
This section casts a duty on the arresting officer to inform the accused person about the grounds of his arrest and to forward the accused along with the seized NDPS article to the Magistrate or to the nearest SHO as the case may be.

SECTION 52A (Disposal of Seized Articles):
This section mandates about the disposal of seized contrabands by forwarding it to the nearest Magistrate as per DOR Notification.

SECTION 57 (Report to immediate Superior officer):
All Arrests and Seizures to be informed within 48 hours to immediate Superior Officer.

Steps to be taken during Investigation:

1. Recording of Statements:
The next important step that is required to be taken is interrogation/examination of the suspects (accused) and the witnesses. Notice under Section 67 of the NDPS Act may be issued and statements about the identity of the person, address, background, education, occupation, involvement in the drug trade, etc., are to be recorded. This notice should be served under the signature of the concerned person. It must be ensured that the statement that is recorded is written in the language which is understood by the suspects/witnesses. The officer in whose presence the statement is given should also put his signature. If the statement is not written by the person himself, the officer should keep a note that the statement was read out and explained to the person in the language known to him.

2. Disposal of Persons Arrested and Articles Seized:
While arresting a person memo may be served to the person under his dated signature as a token of receipt of the same. The person being arrested should be informed of grounds for such arrest as per Sec. 52(1) of the NDPS Act. Other provisions of Section 52 have also to be complied with regard to arrested persons and seized article.

3. Withdrawal of Sample:
As per the amended provisions, the procedure of sampling is done by the learned Illaqa/Duty Magistrate under section 52A of NDPS Act. In other words, the process of withdrawing of samples has to be in the presence and under the supervision of the Magistrate only and the entire exercise has to be certified by him to be correct. Therefore, it is incumbent upon the SHO to forward the samples immediately to the Ld. MM Court for:
a) For withdrawing representative samples in the presence of the Magistrate and certifying the correctness of the list of samples so drawn.
b) Certifying the correctness of the inventory and
c) Certifying photographs of such drugs or substances taken before the Magistrate as true.

After withdrawing of the samples, the same should be sent to the laboratory within 72 hrs. Sometimes when the sample is sent to FSL, it is returned by the lab by raising some objection which is fatal for the case of prosecution. MHC must make sure that there should be no infirmity when the sample and the docket are sent to the lab.

4. Informing the Superior about Seizure and Arrest:
As per requirement of the Act, the immediate superior officer is to be sent a full report of all the particulars of an arrest. This requirement of law is not to be forgotten. Such report should be given within 48 hours of seizure or arrest in terms 57 of the NDPS Act.

5. PC Remand of accused:
The accused should be taken on PC remand to unearth the entire chain of suppliers, drug dealers involved in drug trafficking.

6. Financial Investigation:
Drug offences, unlike most other offences, are committed only with profit motive. One of the strategies to fight drug trafficking is denying the traffickers the fruits of their trafficking. Chapter VA of the NDPS Act provides for forfeiture of such illegally acquired properties. The property derived from or used in illicit traffic of drugs is liable to forfeiture. The provisions apply to convicted persons, detainees under PITNDPS, absconders, relatives and associates.

7. Forfeiture of Property:
i. Freezing of property under section 68F  
ii. Confirmation by Competent Authority within 30 days  
iii. Show Cause Notice under section 68H  
iv. Forfeiture order under section 68I  
v. Burden of proof on accused  
vi. Fine in lieu of forfeiture  
vii. Management by Competent Authority  
viii. Appeal before Appellate Tribunal  

8. Preparation of Charge-sheet:
After completing investigation and collecting FSL result, charge-sheet must be prepared and filed without delay. Role of each witness must be clearly specified and all documents annexed.

POST FILING CHARGE-SHEET:
Proper pairvi through Pairvi Cell to ensure:
- Supply of charge-sheet  
- Written submissions  
- Coordination with prosecutor  
- Witness intimation  
- Witness briefing  
- Filing of FSL and sanctions  
- Production of case property  
- Court compliance  

========================
TASK
========================

Analyse the FIR text below and generate a professional, chronological, court-ready Step-wise Investigation Plan for the case.

The plan must be realistic, procedural, and compliant with:
- NDPS Act
- CrPC
- Juvenile Justice Act (ONLY if minor is mentioned in the FIR)

Do NOT ask questions.
Do NOT request extra information.
Work only with the FIR content and generate a legally sound investigation roadmap.

If any fact is missing from FIR, write the step as "to be verified" or "to be completed".

IMPORTANT: 
- ONLY include "Child Welfare & Juvenile Safeguards" section if the FIR explicitly mentions a minor/juvenile accused
- ONLY mention women officers or female-specific procedures if the FIR involves a female accused or female-specific search requirements
- Do NOT include generic sections about children or women if not relevant to this specific case

The output must follow this structure (adjust based on case relevance):

1. Immediate Actions (Day 0–1)
2. Child Welfare & Juvenile Safeguards (ONLY if minor involved - check FIR for age/status)
3. Documentation & Procedural Compliance
4. Forensic & Sampling Process
5. Witness Examination
6. Evidence Development
7. NDPS Legal Compliance Review
8. Bail & Custody Considerations
9. Charge-sheet Preparation
10. Timeline Summary

If no minor is involved, skip section 2 entirely. If no female accused, do not mention women officers or female-specific procedures.

Style:
- Formal Indian legal English
- Actionable steps only
- No assumptions
- Use conditional language where FIR is silent

FIR Text:
[PASTE FIR HERE]
"""


def investigation_plan(state: WorkflowState) -> dict:
    """
    Generate investigation plan based on FIR facts.
    """
    logger.info("Starting investigation plan generation")
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for FIR fact extraction")
    
    pdf_content = state["pdf_content_in_english"]
    logger.debug(f"FIR content length: {len(pdf_content)} characters")

    llm_with_structured_output = llm_model.with_structured_output(InvestigationPlan)
    prompt = PROMPT.replace("[PASTE FIR HERE]", pdf_content)
    
    @exponential_backoff_retry(max_retries=5, max_wait=60)
    def _invoke_investigation_plan():
        return llm_with_structured_output.invoke(prompt)
    
    response = _invoke_investigation_plan()
    state["investigation_plan"] = response.points
    logger.info(f"Generated investigation plan with {len(response.points)} points")
    return {
        "investigation_plan": response.points
    }
    