"""
Utility function to format historical cases for LLM prompts
"""
from typing import List, Dict, Optional


def format_historical_cases_for_prompt(historical_cases: Optional[List[Dict]]) -> str:
    """
    Format historical cases from state into a readable string for LLM prompts.
    
    Args:
        historical_cases: List of historical case dictionaries from state
        
    Returns:
        Formatted string with case information, or empty string if no cases
    """
    if not historical_cases or len(historical_cases) == 0:
        return ""
    
    formatted_text = "\n\n========================\nRELEVANT HISTORICAL CASES\n========================\n\n"
    formatted_text += "The following are actual NDPS cases retrieved from Indian Kanoon that are relevant to this FIR:\n\n"
    
    for idx, case in enumerate(historical_cases, 1):
        title = case.get("title", "NDPS Case")
        summary = case.get("summary", "")
        case_number = case.get("case_number")
        year = case.get("year")
        url = case.get("url", "")
        score = case.get("score", 0.0)
        
        formatted_text += f"Case {idx}: {title}\n"
        
        if case_number:
            formatted_text += f"Case Number: {case_number}\n"
        if year:
            formatted_text += f"Year: {year}\n"
        if url:
            formatted_text += f"Source: {url}\n"
        if score:
            formatted_text += f"Relevancy Score: {score}/10\n"
        
        formatted_text += f"Summary: {summary}\n"
        formatted_text += "-" * 80 + "\n\n"
    
    formatted_text += "\nUse these actual historical cases to:\n"
    formatted_text += "- Reference specific case law and precedents\n"
    formatted_text += "- Cite relevant legal principles established in these cases\n"
    formatted_text += "- Learn from successful prosecution strategies or common pitfalls\n"
    formatted_text += "- Strengthen your analysis with real-world examples\n\n"
    
    return formatted_text
