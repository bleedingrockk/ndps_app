from tavily import TavilyClient
from pydantic import BaseModel, Field
from app.langgraph.state import WorkflowState
from app.models.openai import llm_model
import logging
import os

logger = logging.getLogger(__name__)

# Initialize Tavily client with API key from environment
tavily_api_key = os.getenv("TAVILY_API_KEY", "")
client = TavilyClient(tavily_api_key)

class Question(BaseModel):
    question: str = Field(description="Question that I can search on the internet to find historical cases related to the given FIR")

def historical_cases(state: WorkflowState) -> dict:
    """
    Search for historical cases related to the FIR and return summarized results.
    """
    logger.info("Starting historical cases search")
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for historical cases search")
    
    pdf_content = state["pdf_content_in_english"]
    logger.debug(f"FIR content length: {len(pdf_content)} characters")
    
    # Generate search question based on FIR content
    prompt = f"""Based on the following FIR content, create one specific search query to find relevant court judgments in NDPS cases.

FIR Content: {pdf_content}

CRITICAL REQUIREMENTS:
1. You MUST identify the specific substance/drug mentioned in the FIR (e.g., Ganja, Cannabis, Heroin, Cocaine, etc.)
2. The search query MUST include the substance name to ensure relevance
3. Extract other key facts: age of accused, quantity seized (small/intermediate/commercial), procedural issues, etc.

Examples of good search queries:
- "NDPS Ganja cases where the accused is a minor"
- "NDPS Cannabis cases involving commercial quantity"
- "NDPS Heroin cases with procedural lapses in search and seizure"

Instructions:
1. First identify the specific substance/drug mentioned in the FIR
2. Extract other key facts (age of accused, quantity seized, procedural issues, etc.)
3. Create a focused search query that includes the substance name and other relevant facts
4. Keep the query concise but specific - MUST include the substance type
5. Focus on legally significant aspects (quantities, procedures, accused characteristics)

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
        # Search using Tavily
        response = client.search(
            query=search_query,
            search_depth="advanced",
            include_usage=True,
            max_results=10,  # Increased to account for filtering
            include_raw_content=True,
            exclude_domains=["https://indiankanoon.org"]
        )
        
        # Process results
        results = response.get('results', []) if isinstance(response, dict) else response.results
        
        for result in results:
            # Handle both dict and object result formats
            if isinstance(result, dict):
                title = result.get('title', '')
                url = result.get('url', '')
                raw_content = result.get('raw_content', '') or ''
            else:
                title = result.title
                url = result.url
                raw_content = result.raw_content if hasattr(result, 'raw_content') and result.raw_content else ""
            
            # Skip duplicates
            if any(case['url'] == url for case in historical_cases_list):
                logger.debug(f"Skipping duplicate: {title}")
                continue
            
            # Validate that result mentions the substance from FIR
            if fir_substance:
                result_text = (title + " " + raw_content).lower()
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
                    logger.debug(f"Skipping result - doesn't mention {fir_substance}: {title}")
                    continue
            
            # Summarize raw_content using LLM
            summary = ""
            if raw_content:
                # Limit content to avoid token limits
                truncated_raw = raw_content[:4000] if len(raw_content) > 4000 else raw_content
                
                # Better summarization prompt
                summary_prompt = f"""Analyze this legal case and provide a concise summary in 3-4 sentences covering:
1. Case name and court
2. Key facts and circumstances
3. Legal issues/sections involved
4. Court's decision and reasoning

Legal Case Content:
{truncated_raw}
"""
                
                try:
                    summary_response = llm_model.invoke(summary_prompt)
                    summary = summary_response.content if hasattr(summary_response, 'content') else str(summary_response)
                    logger.debug(f"Summarized case: {title}")
                except Exception as e:
                    logger.error(f"Error summarizing case {title}: {e}")
                    summary = "Summary unavailable"
            
            case_data = {
                "title": title,
                "url": url,
                "summary": summary
            }
            historical_cases_list.append(case_data)
            
            # Stop if we have enough cases
            if len(historical_cases_list) >= 5:
                break
                
    except Exception as e:
        logger.error(f"Error searching with query '{search_query}': {e}")
    
    logger.info(f"Found {len(historical_cases_list)} historical cases")
    
    return {
        "historical_cases": historical_cases_list
    }