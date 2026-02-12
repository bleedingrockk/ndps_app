from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver

from app.langgraph.state import WorkflowState
from app.utils.read_pdf import read_pdf

from app.components.fir_fact_extraction import extract_fir_fact
from app.components.ndps_legal_mapping import ndps_legal_mapping
from app.components.bns_legal_mapping import bns_legal_mapping
from app.components.bnss_legal_mapping import bnss_legal_mapping
from app.components.bsa_legal_mapping import bsa_legal_mapping
from app.components.investigation_plan import investigation_plan
from app.components.evidence_checklist import generate_evidence_checklist
from app.components.dos_and_dont import generate_dos_and_donts
from app.components.potential_prosecution_weaknesses import generate_potential_prosecution_weaknesses
from app.components.historical_cases import historical_cases
from app.components.inestigation_and_legal_timeline import investigation_and_legal_timeline
from app.components.defence_perspective_rebuttal import generate_defence_perspective_rebuttal
from app.components.summary_for_the_court import generate_summary_for_the_court
from app.components.chargesheet import generate_chargesheet


checkpointer = MemorySaver()

# Components that need historical cases
COMPONENTS_NEEDING_HISTORICAL_CASES = [
    "generate_evidence_checklist",
    "generate_dos_and_donts",
    "generate_potential_prosecution_weaknesses",
    "generate_defence_perspective_rebuttal",
    "generate_summary_for_the_court",
    "generate_chargesheet",
    "investigation_plan"
]

def route_all_sections(state: WorkflowState) -> list[str]:
    """Route to ALL selected sections - they all run in PARALLEL"""
    selected_sections = state.get("sections", [])
    routes = []
    historical_cases_selected = "historical_cases" in selected_sections
    
    if "ndps" in selected_sections:
        routes.append("ndps_legal_mapping")
    if "bns" in selected_sections:
        routes.append("bns_legal_mapping")
    if "bnss" in selected_sections:
        routes.append("bnss_legal_mapping")
    if "bsa" in selected_sections:
        routes.append("bsa_legal_mapping")
    # Only route investigation_plan directly if historical_cases is not selected
    # Otherwise, it will be routed from historical_cases
    if "investigation_plan" in selected_sections and not historical_cases_selected:
        routes.append("investigation_plan")
    if "historical_cases" in selected_sections:
        routes.append("historical_cases")
    if "timeline" in selected_sections:
        routes.append("investigation_and_legal_timeline")
    # Only route components that need historical cases directly if historical_cases is not selected
    # Otherwise, they will be routed from historical_cases
    if "evidence" in selected_sections and not historical_cases_selected:
        routes.append("generate_evidence_checklist")
    if "dos_and_donts" in selected_sections and not historical_cases_selected:
        routes.append("generate_dos_and_donts")
    if "weaknesses" in selected_sections and not historical_cases_selected:
        routes.append("generate_potential_prosecution_weaknesses")
    if "defence_rebuttal" in selected_sections and not historical_cases_selected:
        routes.append("generate_defence_perspective_rebuttal")
    if "court_summary" in selected_sections and not historical_cases_selected:
        routes.append("generate_summary_for_the_court")
    if "chargesheet" in selected_sections and not historical_cases_selected:
        routes.append("generate_chargesheet")
    
    return routes if routes else [END]

def route_from_historical_cases(state: WorkflowState) -> list[str]:
    """Route to components that need historical cases after historical_cases completes"""
    selected_sections = state.get("sections", [])
    routes = []
    
    if "investigation_plan" in selected_sections:
        routes.append("investigation_plan")
    if "evidence" in selected_sections:
        routes.append("generate_evidence_checklist")
    if "dos_and_donts" in selected_sections:
        routes.append("generate_dos_and_donts")
    if "weaknesses" in selected_sections:
        routes.append("generate_potential_prosecution_weaknesses")
    if "defence_rebuttal" in selected_sections:
        routes.append("generate_defence_perspective_rebuttal")
    if "court_summary" in selected_sections:
        routes.append("generate_summary_for_the_court")
    if "chargesheet" in selected_sections:
        routes.append("generate_chargesheet")
    
    return routes if routes else [END]

# Build graph
workflow_graph = StateGraph(WorkflowState)

# Add all nodes
workflow_graph.add_node("read_pdf", read_pdf)
workflow_graph.add_node("extract_fir_fact", extract_fir_fact)
workflow_graph.add_node("ndps_legal_mapping", ndps_legal_mapping)
workflow_graph.add_node("bns_legal_mapping", bns_legal_mapping)
workflow_graph.add_node("bnss_legal_mapping", bnss_legal_mapping)
workflow_graph.add_node("bsa_legal_mapping", bsa_legal_mapping)
workflow_graph.add_node("investigation_plan", investigation_plan)
workflow_graph.add_node("investigation_and_legal_timeline", investigation_and_legal_timeline)
workflow_graph.add_node("historical_cases", historical_cases)
workflow_graph.add_node("generate_evidence_checklist", generate_evidence_checklist)
workflow_graph.add_node("generate_dos_and_donts", generate_dos_and_donts)
workflow_graph.add_node("generate_potential_prosecution_weaknesses", generate_potential_prosecution_weaknesses)
workflow_graph.add_node("generate_defence_perspective_rebuttal", generate_defence_perspective_rebuttal)
workflow_graph.add_node("generate_summary_for_the_court", generate_summary_for_the_court)
workflow_graph.add_node("generate_chargesheet", generate_chargesheet)

# Permanent sequential path
workflow_graph.add_edge(START, "read_pdf")
workflow_graph.add_edge("read_pdf", "extract_fir_fact")
# workflow_graph.add_edge("translate_to_english", "extract_fir_fact")

# Route to ALL selected sections at once - they ALL run in PARALLEL
workflow_graph.add_conditional_edges(
    "extract_fir_fact",
    route_all_sections,
    {
        "ndps_legal_mapping": "ndps_legal_mapping",
        "bns_legal_mapping": "bns_legal_mapping",
        "bnss_legal_mapping": "bnss_legal_mapping",
        "bsa_legal_mapping": "bsa_legal_mapping",
        "investigation_plan": "investigation_plan",
        "investigation_and_legal_timeline": "investigation_and_legal_timeline",
        "historical_cases": "historical_cases",
        "generate_evidence_checklist": "generate_evidence_checklist",
        "generate_dos_and_donts": "generate_dos_and_donts",
        "generate_potential_prosecution_weaknesses": "generate_potential_prosecution_weaknesses",
        "generate_defence_perspective_rebuttal": "generate_defence_perspective_rebuttal",
        "generate_summary_for_the_court": "generate_summary_for_the_court",
        "generate_chargesheet": "generate_chargesheet",
        END: END,
    }
)

# Add conditional edge from historical_cases to route to components that need it
workflow_graph.add_conditional_edges(
    "historical_cases",
    route_from_historical_cases,
    {
        "investigation_plan": "investigation_plan",
        "generate_evidence_checklist": "generate_evidence_checklist",
        "generate_dos_and_donts": "generate_dos_and_donts",
        "generate_potential_prosecution_weaknesses": "generate_potential_prosecution_weaknesses",
        "generate_defence_perspective_rebuttal": "generate_defence_perspective_rebuttal",
        "generate_summary_for_the_court": "generate_summary_for_the_court",
        "generate_chargesheet": "generate_chargesheet",
        END: END,
    }
)

# All selected nodes go straight to END
workflow_graph.add_edge("ndps_legal_mapping", END)
workflow_graph.add_edge("bns_legal_mapping", END)
workflow_graph.add_edge("bnss_legal_mapping", END)
workflow_graph.add_edge("bsa_legal_mapping", END)
workflow_graph.add_edge("investigation_and_legal_timeline", END)
workflow_graph.add_edge("historical_cases", END)  # historical_cases can also go directly to END if no dependent components
workflow_graph.add_edge("generate_evidence_checklist", END)
workflow_graph.add_edge("generate_dos_and_donts", END)
workflow_graph.add_edge("generate_potential_prosecution_weaknesses", END)
workflow_graph.add_edge("generate_defence_perspective_rebuttal", END)
workflow_graph.add_edge("generate_summary_for_the_court", END)
workflow_graph.add_edge("generate_chargesheet", END)
workflow_graph.add_edge("investigation_plan", END)

graph = workflow_graph.compile(checkpointer=checkpointer)