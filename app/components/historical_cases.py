from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
from app.rag import query_ndps_judgements
import logging

logger = logging.getLogger(__name__)

class Question(BaseModel):
    question: str = Field(description="Question that I can search in historical NDPS judgements related to the given FIR")

def historical_cases(state: WorkflowState) -> dict:
    """
    Search for historical cases related to the FIR using FAISS index of NDPS judgements.
    """
    logger.info("Starting historical cases search")
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for historical cases search")
    
    pdf_content = state["pdf_content_in_english"]
    logger.debug(f"FIR content length: {len(pdf_content)} characters")
    
    # Generate search question based on FIR content
    prompt = f"""Based on the following FIR content, create one specific search query to find relevant court judgments in NDPS cases from the historical judgements database.

FIR Content: {pdf_content}

CRITICAL REQUIREMENTS:
1. You MUST identify the specific substance/drug mentioned in the FIR (e.g., Ganja, Cannabis, Heroin, Cocaine, etc.)
2. The search query MUST include the substance name to ensure relevance
3. Extract other key facts: age of accused, quantity seized (small/intermediate/commercial), procedural issues, etc.

Examples of good search queries:
- "bail application Ganja NDPS cases"
- "commercial quantity Cannabis search and seizure"
- "Section 50 NDPS Act Heroin procedural compliance"
- "minor accused NDPS cases acquittal"

Instructions:
1. First identify the specific substance/drug mentioned in the FIR
2. Extract other key facts (age of accused, quantity seized, procedural issues, etc.)
3. Create a focused search query that includes the substance name and other relevant facts
4. Keep the query concise but specific - MUST include the substance type
5. Focus on legally significant aspects (quantities, procedures, accused characteristics, sections of NDPS Act)

Create a search query that MUST include the substance name and other relevant facts from the FIR:
"""
    
    question = llm_model.with_structured_output(Question).invoke(prompt)
    search_query = question.question
    logger.info(f"Generated search question: {search_query}")
    
    # Extract substance from FIR for validation
    substance_extraction_prompt = f"""From the following FIR content, identify the specific narcotic drug or psychotropic substance mentioned (e.g., Ganja, Cannabis, Heroin, Cocaine, Charas, etc.). Return only the substance name.

FIR Content: {pdf_content}

Substance name:"""
    
    try:
        substance_response = llm_model.invoke(substance_extraction_prompt)
        fir_substance = substance_response.content if hasattr(substance_response, 'content') else str(substance_response)
        fir_substance = fir_substance.strip().lower()
        logger.info(f"Identified substance from FIR: {fir_substance}")
    except Exception as e:
        logger.warning(f"Could not extract substance from FIR: {e}")
        fir_substance = None
    
    historical_cases_list = []
    
    try:
        # Search using FAISS index
        results = query_ndps_judgements(search_query, k=10)
        
        for result in results:
            chunk = result['chunk']
            score = result['score']
            content = chunk.get('content', '')
            
            # Skip duplicates
            case_number = chunk.get('case_number', '')
            year = chunk.get('year', '')
            case_id = f"{case_number}_{year}"
            if any(case.get('case_id') == case_id for case in historical_cases_list):
                logger.debug(f"Skipping duplicate: Case {case_number}, Year {year}")
                continue
            
            # Validate that result mentions the substance from FIR
            if fir_substance:
                result_text = content.lower()
                # Check for common substance name variations
                substance_variations = {
                    'ganja': ['ganja', 'cannabis', 'marijuana', 'marihuana', 'weed', 'bhang'],
                    'cannabis': ['ganja', 'cannabis', 'marijuana', 'marihuana', 'weed', 'bhang'],
                    'heroin': ['heroin', 'diacetylmorphine', 'smack'],
                    'cocaine': ['cocaine', 'coke'],
                    'charas': ['charas', 'hashish', 'hash'],
                    'opium': ['opium'],
                    'morphine': ['morphine'],
                    'buprenorphine': ['buprenorphine', 'buprenorphine injection'],
                    'avil': ['avil', 'pheniramine']
                }
                
                # Get variations for the substance
                variations = substance_variations.get(fir_substance, [fir_substance])
                
                # Check if any variation is mentioned
                if not any(var in result_text for var in variations):
                    logger.debug(f"Skipping result - doesn't mention {fir_substance}: Case {case_number}")
                    continue
            
            # Extract case title from content (first few lines usually contain case name)
            lines = content.split('\n')
            case_title = ""
            for line in lines[:10]:  # Check first 10 lines
                line = line.strip()
                if line and len(line) > 10 and not line.isdigit() and not line.startswith('==='):
                    # Look for patterns like "vs.", "Vs.", "versus"
                    if any(keyword in line.lower() for keyword in ['vs.', 'versus', 'v.', 'v/s']):
                        case_title = line
                        break
                    elif not case_title and len(line) > 20:
                        case_title = line
            
            if not case_title:
                case_title = f"Case {case_number} ({year})" if case_number and year else "NDPS Case"
            
            # Summarize content using LLM
            summary = ""
            if content:
                # Limit content to avoid token limits
                truncated_content = content[:3000] if len(content) > 3000 else content
                
                # Better summarization prompt
                summary_prompt = f"""Analyze this legal case judgement and provide a concise summary in 3-4 sentences covering:
1. Case name and court
2. Key facts and circumstances
3. Legal issues/sections involved
4. Court's decision and reasoning

Legal Case Content:
{truncated_content}
"""
                
                try:
                    summary_response = llm_model.invoke(summary_prompt)
                    summary = summary_response.content if hasattr(summary_response, 'content') else str(summary_response)
                    logger.debug(f"Summarized case: {case_title}")
                except Exception as e:
                    logger.error(f"Error summarizing case {case_title}: {e}")
                    # Fallback: use first 200 characters
                    summary = content[:200] + "..." if len(content) > 200 else content
            
            case_data = {
                "title": case_title,
                "url": None,  # No URL for indexed judgements
                "summary": summary,
                "case_number": case_number,
                "year": year,
                "case_id": case_id,
                "score": float(score)
            }
            historical_cases_list.append(case_data)
            
            # Stop if we have enough cases
            if len(historical_cases_list) >= 5:
                break
                
    except Exception as e:
        logger.error(f"Error searching judgements with query '{search_query}': {e}")
    
    logger.info(f"Found {len(historical_cases_list)} historical cases")
    
    return {
        "historical_cases": historical_cases_list
    }
