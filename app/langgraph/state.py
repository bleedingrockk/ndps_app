from langgraph.graph import MessagesState
from typing import List, Any, Dict

class WorkflowState(MessagesState):
    pdf_path: str | None = None
    pdf_bytes: bytes | None = None
    pdf_filename: str | None = None
    pdf_content: str | None = None
    pdf_content_in_english: str | None = None
    sections: List[str] | None = None  # Selected sections to process
    fir_facts: dict | None = None
    ndps_sections_mapped: List[dict] | None = None
    bns_sections_mapped: List[dict] | None = None
    bnss_sections_mapped: List[dict] | None = None
    bsa_sections_mapped: List[dict] | None = None
    forensic_guidelines_mapped: List[dict] | None = None
    investigation_plan: List[dict] | None = None
    next_steps: List[str] | None = None
    evidence_checklist: str | List[str] | None = None
    dos: List[str] | None = None
    donts: List[str] | None = None
    potential_prosecution_weaknesses: Dict[str, str] | None = None
    historical_cases: List[dict] | None = None
    investigation_and_legal_timeline: Dict[str, str] | None = None
    defence_perspective_rebuttal: List[dict] | None = None
    summary_for_the_court: dict | None = None
    chargesheet: dict | None = None