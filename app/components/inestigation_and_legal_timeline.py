from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
import logging
import os

logger = logging.getLogger(__name__)

class InvestigationAndLegalTimeline(BaseModel):
    date_string: str = Field(description="Date string in the format of YYYY-MM-DD")
    investigation_or_legal_plan: str = Field(description="Investigation plan for the given date string")
    
ENHANCED_LEGAL_FACTS_FOR_TIMELINES = """
-- ESSENTIAL STATUTORY DEADLINES / RULES (use these as fixed inputs) --

1) PERSONS ARRESTED / PRODUCTION
- Produce arrested person before Magistrate/JJB within 24 hours of arrest (CrPC S.57 / Art.22(2)). Exclude travel time to Court when computing. :contentReference[oaicite:0]{index=0}

2) DEFAULT BAIL (police detention -> charge-sheet)
- Section 167(2) CrPC: If investigation not completed, accused entitled to 'default bail':
  * 60 days if offence punishable with < 10 years (use statute to decide). 
  * 90 days if offence punishable with ≥ 10 years (many NDPS commercial/serious matters fall here). 
  * Right lost if chargesheet is filed within the relevant period or statutory extensions apply. :contentReference[oaicite:1]{index=1}

3) NDPS ACT - SAMPLING / SEARCH / BAIL RIGOUR
- Section 50 NDPS: Person has RIGHT to be searched before nearest Gazetted Officer or Magistrate for personal search — mandatory compliance; failure vitiates recovery. (Highlight: Arif Khan decision re-iterates mandatory nature). :contentReference[oaicite:2]{index=2}
- Section 52A NDPS: Representative samples must be drawn in presence of Magistrate (or as per standing orders), sealed, inventory prepared and maintained; Magistrate certification often required before dispatch to FSL. :contentReference[oaicite:3]{index=3}
- Section 37 NDPS: Bail embargo for offences involving commercial quantity; court may grant bail only if Public Prosecutor heard and court is satisfied on twin conditions (reasonable grounds to believe accused is not guilty; accused not likely to commit offence while on bail). Treat this as a strict filter for adults. :contentReference[oaicite:4]{index=4}

4) JUVENILE (CHILD IN CONFLICT WITH LAW) OVERRIDES
- JJ Act S.10 / S.12: Child must not be kept in ordinary police lock-up; must be produced before Juvenile Justice Board within 24 hours; JJ Act presumes bail is the rule (Sec.12) unless narrow exceptions apply (risk of association with criminals / danger / would defeat ends of justice). Always apply JJ safeguards first for accused <18 on date of offence. :contentReference[oaicite:5]{index=5}

5) WOMEN ACCUSED – ADDITIONAL SAFEGUARDS
- CrPC S.46(4) and proviso to S.437: Special protections for women (no arrest at night ordinarily; courts may lean towards bail for women under proviso). Apply privacy/dignity and female-officer search rules. :contentReference[oaicite:6]{index=6}

6) ARREST / CUSTODY PRACTICALS (DK BASU)
- Follow DK Basu arrest memo rules: arrest memo, signatures of witness, identification of arresting officers, weekly diary entries, medical exam instructions — non-compliance is a factual red flag for timeline and bail arguments. :contentReference[oaicite:7]{index=7}

7) FSL / SAMPLE HANDLING / CHARGESHEET STRATEGY
- FSL turnaround times vary widely by city and exam type; courts prefer FSL report obtained promptly (many courts expect chemical analysis within 30–60 days for routine NDPS samples; real-world TATs often range from days to many months). Unexplained or excessive delay in sampling/dispatch/report weakens prosecution and can support bail/default bail arguments. :contentReference[oaicite:8]{index=8}
- Best-practice: (a) draw & seal representative samples on spot or before Magistrate (S.52A); (b) prepare panchnama and chain-of-custody entries (Malkhana entry) with seal numbers and witness signatures; (c) dispatch with recorded receipt and courier/ERP reference; (d) log FSL submission date + expected TAT field.

-- EXACT FACTS YOU MUST EXTRACT FROM ANY FIR (these fields avoid LLM guesswork) --
(If any are missing from FIR, timeline must mark those as 'MISSING' and show conservative assumptions.)

A) EVENT BASICS
- FIR number / FIR registration datetime (exact) — use that as Day 0 baseline.
- Place of occurrence (district / police station / railway station / public place / private premises).
- Precise timestamp of seizure / arrest (HH:MM). If only date given, assume time of day = 10:00 unless FIR states otherwise — but mark as ASSUMPTION.

B) PERSONS & STATUS
- Age of accused (in FIR). If age not stated, capture: claimed age, available documents (school cert, Aadhaar, PAN), whether medical age requested.
- Gender (male/female/other).
- Whether described as 'juvenile' / 'CICL' / 'minor' or if police have alleged age.

C) SEIZURE DETAILS (critical for NDPS timelines)
- Substance(s) alleged and exact declared weight (grams / kg). Classify quantity immediately: small / intermediate / commercial (use NDPS Schedule thresholds — if not provided, mark as MISSING).
- Location of seizure: person, baggage, house, vehicle, consignment (public place vs private).
- Who performed search: RPF / Railway police / local police / STF / NIA / ATS — record investigating agency.
- Whether personal search performed before Magistrate or Gazetted Officer (Section 50 compliance flag: YES / NO / UNKNOWN).
- Presence of independent witnesses at seizure (names if given) and their signatures on panchnama.
- Whether samples were drawn on spot and whether Magistrate was called for sampling (S.52A) — record sample dates and serial numbers. If the sample date != FIR date, mark delay.

D) CUSTODY / PRODUCTION LOG
- Time arrested / detained.
- Time produced before Magistrate or JJB (timestamp). If missing, calculate deadline (arrest + 24 hours) and mark as critical.
- Copy of arrest memo / panchanama attached? (Y/N)

E) FSL / LAB INFO
- Date samples sent to FSL (if present).
- Type of test required (chemical analysis: narcotic test, GC-MS, TLC; toxicology; DNA) — affects TAT.
- Number of exhibits / samples (estimate to pick reasonable TAT).

F) PRIOR CASES / ANTECEDENTS / NEXUS
- Any mention of prior NDPS cases against accused.
- Any named co-accused or cross-state links (NIA / ATS trigger).

G) BAIL / CHARGESHEET STATUS (as of FIR)
- Whether anticipatory/regular bail applied already and outcome (if FIR is later stage).
- Whether chargesheet filed and date (if yes, then default-bail not available).

-- PRACTICAL TIMELINE TRIGGERS (use these to compute Day X items) --
- If arrest_time present → Day0: arrest, seizure, panchnama, personal/search compliance check, sample draw attempt, produce-before-court deadline = arrest_time + 24h.
- If juvenile → Day0 evening: record CWO/SJPU involvement and immediate intimation to JJB; DO NOT keep in police lock-up.
- If samples drawn but NOT sent to FSL within 48–72 hrs → flag "dispatch delay" and mark as litigation risk.
- If sample sent to FSL → add expected FSL-report window:
   * simple chemical test / <10 exhibits: 3–14 days (typical best-case). :contentReference[oaicite:9]{index=9}
   * complex heroin/opiates GC-MS / multiple exhibits: 30–90 days typical; in backlog cities expect 90–180+ days. :contentReference[oaicite:10]{index=10}
- If NDPS commercial quantity → immediately trigger Section 37 bail-rigour in timeline (public prosecutor hearing + court satisfaction step must appear before any bail event).
- If no FSL / samples not drawn / Section 50 non-compliance / missing independent witnesses → insert a "procedural challenge" milestone (day X) where defence can file application for suppression/discharge/default bail.

-- FORMATTED FLAGS TO RETURN (for timeline engine)
- MANDATORY_FLAGS = {
  "produce_by_24h": True/False/UNKNOWN,
  "section50_complied": True/False/UNKNOWN,
  "samples_drawn_before_magistrate": True/False/UNKNOWN,
  "samples_sent_to_fsl_date": DATE or UNKNOWN,
  "fsl_expected_tat_days": INT or RANGE or UNKNOWN,
  "ndps_quantity_class": "small/intermediate/commercial/UNKNOWN",
  "accused_is_juvenile": True/False/UNKNOWN,
  "accused_is_woman": True/False/UNKNOWN,
  "prior_ndps_antecedent": True/False/UNKNOWN
}

-- QUICK CHECKLIST (when building timeline from FIR)
- Do you have exact arrest timestamp? If NO, mark Day0 time as 'ASSUMED' and show conservative deadlines.
- Is Section 50 search recorded (who witnessed, gazetted officer / magistrate)? If NO, place 'Sec50_noncompliance' warning into timeline.
- Were samples drawn before a Magistrate (S.52A)? If NO, mark 'sampling_gap' and expect defence challenge.
- Is sample dispatch to FSL logged (date + LR / courier ref)? If NO, flag 'dispatch_missing'.
- Is accused juvenile or female? If YES, override adult NDPS steps with JJ Act / women safeguards immediately.

-- MOST IMPORTANT CITED REFERENCES (verify as needed)
- Section 37 NDPS bail constraints and judicial treatment. :contentReference[oaicite:11]{index=11}
- Section 50 NDPS mandatory personal-search & Arif Khan decision. :contentReference[oaicite:12]{index=12}
- Section 52A NDPS sampling / magistrate involvement. :contentReference[oaicite:13]{index=13}
- CrPC S.57 (24-hour produce) and Section 167 default bail timelines (60/90 days). :contentReference[oaicite:14]{index=14}
- DK Basu arrest-memo / custody safeguards. :contentReference[oaicite:15]{index=15}
- FSL turnaround variability and judicial concern about delayed reports. :contentReference[oaicite:16]{index=16}

"""

investigation_and_legal_timeline_llm = llm_model.with_structured_output(InvestigationAndLegalTimeline)

def investigation_and_legal_timeline(state: WorkflowState) -> dict:
    """
    Generate investigation and legal timeline based on FIR content.
    
    Args:
        state: WorkflowState containing pdf_content_in_english
        
    Returns:
        dict with investigation_and_legal_timeline key
        
    Raises:
        ValueError: If pdf_content_in_english is missing or invalid
    """
    logger.info("Starting investigation and legal timeline generation")
    
    if not state.get("pdf_content_in_english"):
        logger.error("pdf_content_in_english is required but not found in state")
        raise ValueError("pdf_content_in_english is required for timeline generation")
    
    pdf_content = state["pdf_content_in_english"]
    
    # Validate PDF content is not empty
    if not isinstance(pdf_content, str) or len(pdf_content.strip()) == 0:
        logger.error(f"Invalid pdf_content_in_english: type={type(pdf_content)}, length={len(pdf_content) if isinstance(pdf_content, str) else 'N/A'}")
        raise ValueError("pdf_content_in_english must be a non-empty string")
    
    logger.debug(f"Processing PDF content of length: {len(pdf_content)} characters")
    
    try:
        # Invoke LLM with legal facts template and PDF content
        response = investigation_and_legal_timeline_llm.invoke(
            ENHANCED_LEGAL_FACTS_FOR_TIMELINES + "\n\n--- FIR DOCUMENT ---\n" + pdf_content
        )
        
        # Validate response
        if not response or not response.investigation_or_legal_plan:
            logger.warning("LLM returned empty or incomplete response")
            raise ValueError("Failed to generate valid timeline from LLM")
        
        logger.info(f"Successfully generated timeline for date: {response.date_string}")
        
        # Return structured output with date and timeline
        return {
            "investigation_and_legal_timeline": {
                "date_string": response.date_string,
                "timeline": response.investigation_or_legal_plan
            }
        }
        
    except Exception as e:
        logger.error(f"Error during timeline generation: {str(e)}", exc_info=True)
        raise