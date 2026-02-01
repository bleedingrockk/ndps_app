from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model

class FirFactExtraction(BaseModel):
    date_time_location: str = Field(
        description="Extract ONLY facts directly stated in FIR: exact date, time and place of incident, including train/station/platform if mentioned. Use only what is written in the FIR. Must be between 40-100 words."
    )
    initial_detention: str = Field(
        description="Extract ONLY facts directly stated in FIR: how the accused was first intercepted (suspicion, behaviour, dog sniff, public tip-off, etc.). Use only what is written in the FIR. Must be between 40-100 words."
    )
    identity_of_accused: str = Field(
        description="Extract ONLY facts directly stated in FIR: details of accused such as name, age, gender, address, occupation, minor status if any. Use only what is written in the FIR. Must be between 40-100 words."
    )
    police_order_and_transport: str = Field(
        description="Extract ONLY facts directly stated in FIR: which officer was informed, instructions given, and how the accused was taken to police station. Use only what is written in the FIR. Must be between 40-100 words."
    )
    presence_of_required_officer: str = Field(
        description="Extract ONLY facts directly stated in FIR: presence of mandatory officer as per law, such as Child Welfare Officer for a minor accused or woman police officer for a female accused, including name/designation if mentioned. Use only what is written in the FIR. Must be between 40-100 words."
    )
    search_and_seizure: str = Field(
        description="Extract ONLY facts directly stated in FIR: legal procedure of search, consent, Section 50 compliance, items recovered from person and bags. Use only what is written in the FIR. Must be between 40-100 words."
    )
    weighment_and_packaging: str = Field(
        description="Extract ONLY facts directly stated in FIR: details of weighing, field test, total quantity, sealing, marking of exhibits and packaging method. Use only what is written in the FIR. Must be between 40-100 words."
    )
    procedural_notes: str = Field(
        description="Extract ONLY facts directly stated in FIR: important legal procedures followed such as sampling rules, documentation, videography, signatures, etc. Use only what is written in the FIR. Must be between 40-100 words."
    )
    statement_of_accused: str = Field(
        description="Extract ONLY facts directly stated in FIR: voluntary disclosure made by accused regarding source, purpose, payment, and intended delivery. Use only what is written in the FIR. Must be between 40-100 words."
    )
    offences_charged: str = Field(
        description="Extract ONLY facts directly stated in FIR: sections of law applied against accused (NDPS sections, IPC if any). Use only what is written in the FIR. Must be between 40-100 words."
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
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for FIR fact extraction")
    
    pdf_content = state["pdf_content_in_english"]

    try:
        prompt = f"""Extract the following information from the FIR text. 
        CRITICAL REQUIREMENTS:
        1. Extract ONLY facts directly stated in the FIR text - do not add, interpret, or infer anything
        2. Each field must contain between 40-100 words
        3. Do NOT add legal interpretations, conclusions, or assumptions not explicitly stated in the FIR
        4. Use markdown bold formatting (**text**) to highlight important/relevant information such as:
           - Names, dates, times, locations
           - Section numbers, legal references
           - Quantities, amounts, measurements
           - Key actions, procedures, or facts directly mentioned
           - Important details that stand out in the FIR

        FIR Text:
        {pdf_content}

        Extract all relevant information for each field using ONLY facts directly from the FIR text above.
        Do not add anything that is not explicitly stated in the FIR. 
        Each field must contain between 40-100 words of actual FIR content.
        Be thorough but only use what is written in the FIR. 
        Make important information bold using **text** markdown syntax."""
        
        # Use structured output to get Pydantic model
        llm_with_structured_output = llm_model.with_structured_output(FirFactExtraction)
        response = llm_with_structured_output.invoke(prompt)
        
        # Convert Pydantic model to dict and return
        fir_facts = response.model_dump()
        
        return {
            "fir_facts": fir_facts
        }
    
    except Exception as e:
        raise Exception(f"Error extracting FIR facts: {str(e)}")