# backend/app/components/historical_cases.py
# Historical cases search using Indian Kanoon API
# DOCUMENTATION: https://api.indiankanoon.org/documentation/ 

# ============================================================================
# CONFIGURATION - Modify these parameters to customize your search
# ============================================================================
#
# SEARCH PARAMETERS YOU CAN CHANGE:
#
# 1. SEARCH_QUERY: Your main search query (required)
#    Example: "NDPS case minor caught with Ganja"
#
# 2. PAGENUM: Page number for pagination (starts at 0, not 1)
#    Example: 0 for first page, 1 for second page, etc.
#
# 3. DOCTYPES: Filter by document types (optional)
#    Examples:
#    - "judgments" - All judgments (SC, HC, District Courts)
#    - "laws" - Central Acts and Rules
#    - "tribunals" - All tribunals
#    - "supremecourt" - Supreme Court only
#    - "delhi", "bombay", "kolkata", "chennai" - Specific High Courts
#    - "judgments,supremecourt" - Combine multiple (comma-separated)
#    - "highcourts,cci" - High courts + specific tribunal
#
# 4. FROMDATE: Minimum date filter (optional, format: "DD-MM-YYYY")
#    Example: "01-01-2020" - Only documents after Jan 1, 2020
#
# 5. TODATE: Maximum date filter (optional, format: "DD-MM-YYYY")
#    Example: "31-12-2024" - Only documents before Dec 31, 2024
#
# 6. TITLE_FILTER: Words/phrases that must appear in document title (optional)
#    Example: "NDPS" - Only documents with "NDPS" in title
#
# 7. CITE_FILTER: Filter by citation (optional)
#    Example: "1993 AIR" - Only documents with this citation
#
# 8. AUTHOR_FILTER: Filter by judge/author name (optional)
#    Example: "arijit pasayat" - Only judgments by this judge
#
# 9. BENCH_FILTER: Filter by judge in bench (optional)
#    Example: "arijit pasayat" - Only judgments where this judge was on bench
#
# 10. MAXCITES: Number of citations to return per document (optional, max 50)
#     Example: 20 - Get up to 20 citations for each document
#
# 11. MAXPAGES: Number of pages to fetch in one call (optional, max 1000)
#     Example: 50 - Fetch up to 50 pages in single request
#
# ============================================================================

import requests
import json
import re
import time
from urllib.parse import quote
from datetime import datetime
import os
from dotenv import load_dotenv
import logging
from pydantic import BaseModel, Field
from concurrent.futures import ThreadPoolExecutor, as_completed

# Local imports
from app.models.openai import llm_model
from app.langgraph.state import WorkflowState

load_dotenv()
logger = logging.getLogger(__name__)

class CaseSummary(BaseModel):
    case_relevant: bool = Field(description="Whether the case is about NDPS (Narcotic Drugs and Psychotropic Substances) Act or not")
    case_title: str = Field(description="A concise, descriptive title for the case (7-8 words maximum). Should capture the essence of the case without including names of parties or judges. Focus on the legal issue, substance involved, or key aspect (e.g., 'NDPS Act Ganja Possession Bail Denial Appeal')")
    case_summary: str = Field(description="Concise case summary (200-400 words maximum) covering: sections invoked, crime details, defence arguments, bail status and reasoning, prosecution approach, punishment/outcome, and key legal facts. Do not include names of parties or judges.")
    case_number: str | None = Field(default=None, description="Case number if mentioned in the judgment (e.g., '123', '456/2020', etc.). Return None if not found.")
    year: str | None = Field(default=None, description="Year of the judgment (e.g., '2020', '2021', etc.). Return None if not found.")
    relevancy_score: int = Field(description="Relevancy score from 0-10 indicating how relevant this case is to the FIR. 10 = highly relevant, 0 = not relevant. Consider: substance match, similar facts, similar legal issues, similar procedural aspects.")
    
summary_prompt = """Analyze the following legal case judgment and provide a structured summary focusing on legal aspects and facts.

Case Title: {case_title}

Case Content:
{case_content}

Search Query (for relevancy scoring):
{search_query}

INSTRUCTIONS:
1. First determine if this is an NDPS (Narcotic Drugs and Psychotropic Substances Act) case
2. Generate a concise, descriptive title (7-8 words maximum) that captures the essence of the case. Focus on the legal issue, substance involved, or key aspect. Do NOT include names of parties or judges. Example: "NDPS Act Ganja Possession Bail Denial Appeal"
3. Extract case number and year from the content if mentioned (look for patterns like "Criminal Appeal No. 123 of 2020" or "2020 SCC")
4. Extract and summarize the following information (200-400 words maximum):
   - **Sections Invoked**: List all relevant sections of NDPS Act or other applicable laws mentioned
   - **Crime Details**: Describe the nature of the crime, substance involved, quantity seized, circumstances of arrest/seizure
   - **Defence Arguments**: Summarize key defence arguments, legal points raised, and procedural challenges if any
   - **Bail Status**: 
     * If bail was granted: Explain the reasoning, conditions imposed, and legal basis
     * If bail was denied: Explain the reasoning, legal grounds for denial, and concerns raised by court
   - **Prosecution Approach**: Describe how prosecution proceeded, evidence presented, and legal arguments made
   - **Punishment/Outcome**: Final judgment, sentence imposed (if any), acquittal reasons (if applicable), and court's reasoning
   - **Key Legal Facts**: Important procedural aspects, compliance with legal requirements (e.g., Section 50 NDPS Act), and significant legal precedents cited
5. Assign a relevancy score (0-10) based on how relevant this case is to the search query:
   - 10: Highly relevant - matches search query closely, same substance, similar facts, similar legal issues, similar procedural aspects
   - 7-9: Very relevant - matches search query well, same substance, some similar facts or legal issues
   - 4-6: Moderately relevant - partially matches search query, same substance but different facts, or different substance but similar legal issues
   - 1-3: Low relevance - loosely related to search query, different substance, different facts, but still NDPS case
   - 0: Not relevant - not an NDPS case or completely unrelated to search query

IMPORTANT:
- Keep the summary to 200-400 words maximum (be concise but cover all key points)
- Focus on legal aspects, facts, and reasoning - DO NOT include names of parties, judges, or specific individuals
- Use clear, concise language suitable for legal analysis
- If information is not available in the content, state "Not mentioned" for that aspect
- Ensure the summary is comprehensive, covering all the above points within the word limit
- Extract case_number and year from the content if available
- Provide relevancy_score as an integer from 0-10
"""

summarizer_llm = llm_model.with_structured_output(CaseSummary)

def get_headers():
    """Get headers with authentication"""
    api_token = os.getenv("INDIAN_KANOON_API_TOKEN")
    return {
        "Authorization": f"Token {api_token}",
    "Accept": "application/json"
}

def build_search_url(search_query, pagenum=0, doctypes="judgments", fromdate="01-01-2000", 
                     todate=None, title_filter=None, cite_filter=None, author_filter=None, 
                     bench_filter=None, maxcites=None, maxpages=None):
    """
    Build search URL with all parameters according to Indian Kanoon API documentation.
    
    Args:
        search_query: Main search query (required)
        pagenum: Page number for pagination (starts at 0, not 1)
        doctypes: Filter by document types (e.g., "judgments", "supremecourt", "delhi", "judgments,supremecourt")
        fromdate: Minimum date filter in DD-MM-YYYY format (e.g., "01-01-2000")
        todate: Maximum date filter in DD-MM-YYYY format (e.g., "31-12-2024")
        title_filter: Words/phrases that must appear in document title (e.g., "NDPS")
        cite_filter: Filter by citation (e.g., "1993 AIR")
        author_filter: Filter by judge/author name (e.g., "arijit pasayat")
        bench_filter: Filter by judge in bench (e.g., "arijit pasayat")
        maxcites: Number of citations to return per document (max 50)
        maxpages: Number of pages to fetch in one call (max 1000)
    
    Returns:
        Complete search URL string
    """
    params = []
    
    # Required parameters
    params.append(f"formInput={quote(search_query)}")
    params.append(f"pagenum={pagenum}")
    
    # Optional parameters (only add if provided)
    if doctypes:
        params.append(f"doctypes={doctypes}")
    if fromdate:
        params.append(f"fromdate={fromdate}")
    if todate:
        params.append(f"todate={todate}")
    if title_filter:
        params.append(f"title={quote(title_filter)}")
    if cite_filter:
        params.append(f"cite={quote(cite_filter)}")
    if author_filter:
        params.append(f"author={quote(author_filter)}")
    if bench_filter:
        params.append(f"bench={quote(bench_filter)}")
    if maxcites:
        params.append(f"maxcites={maxcites}")
    if maxpages:
        params.append(f"maxpages={maxpages}")
    
    return f"https://api.indiankanoon.org/search/?{'&'.join(params)}"

def clean_html(text):
    """Remove HTML tags and clean up whitespace"""
    if not text:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)
    # Clean up extra whitespace and newlines
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def fetch_full_document(doc_id):
    """Fetch full document text from Indian Kanoon API"""
    doc_url = f"https://api.indiankanoon.org/doc/{doc_id}/"
    try:
        response = requests.post(doc_url, headers=get_headers(), timeout=30)
        if response.status_code == 200:
            doc_data = response.json()
            # Extract full document text from 'doc' field
            full_text = doc_data.get('doc', '')
            if not full_text:
                return None, None
            return clean_html(full_text), doc_data
        else:
            logger.warning(f"Error fetching document {doc_id}: {response.status_code}")
            return None, None
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout fetching document {doc_id}")
        return None, None
    except Exception as e:
        logger.warning(f"Error fetching document {doc_id}: {str(e)}")
        return None, None

def limit_content_for_llm(content, max_content_tokens=80000):
    """
    Limit content to approximately max_content_tokens.
    
    Model limit: 128,000 tokens total
    Overhead: ~2,000 tokens (prompt ~1K + schema ~222 + response ~500 + buffer)
    Safe content limit: ~80,000 tokens for content (leaves 46K buffer)
    
    For legal text with citations/numbers: 1 token ≈ 2.5-3 characters (very conservative)
    So 80K tokens ≈ 200K-240K characters
    Using 2.5 to be extra safe
    """
    if not content:
        return content
    
    # Very conservative estimate for legal documents: 1 token ≈ 2.5 characters
    # This accounts for legal citations, numbers, and complex formatting
    # Being extra conservative to avoid token limit errors
    max_chars = int(max_content_tokens * 2.5)
    
    if len(content) <= max_chars:
        return content
    
    # Truncate to max_chars, trying to cut at a sentence boundary
    truncated = content[:max_chars]
    # Try to find last sentence boundary
    last_period = truncated.rfind('.')
    last_newline = truncated.rfind('\n')
    cut_point = max(last_period, last_newline)
    
    if cut_point > max_chars * 0.9:  # If we found a good break point
        return truncated[:cut_point + 1] + "\n\n[Content truncated due to length...]"
    
    return truncated + "\n\n[Content truncated due to length...]"

def extract_case_title(content):
    """Extract case title from document content"""
    if not content:
        return None
    
    lines = content.split('\n')
    case_title = ""
    
    # Look for case title in first 10 lines
    for line in lines[:10]:
        line = line.strip()
        if line and len(line) > 10 and not line.isdigit() and not line.startswith('==='):
            # Look for patterns like "vs.", "Vs.", "versus"
            if any(keyword in line.lower() for keyword in ['vs.', 'versus', 'v.', 'v/s']):
                case_title = line
                break
            elif not case_title and len(line) > 20:
                case_title = line
    
    return case_title

def search_indian_kanoon(search_query, max_results=10, fromdate="01-01-2000", 
                        doctypes="judgments", todate=None, title_filter=None, 
                        cite_filter=None, author_filter=None, bench_filter=None, 
                        maxcites=None, maxpages=None, fir_context=None):
    """
    Search Indian Kanoon API for cases and return unique results.
    
    This function:
    1. First collects unique document IDs from search results (across multiple pages if needed)
    2. Then fetches full document content only for unique documents
    3. Returns data in format compatible with historical_cases.py
    
    Reference: https://api.indiankanoon.org/documentation/
    
    Args:
        search_query: Search query string (required)
        max_results: Maximum number of unique cases to return (default: 10)
        fromdate: Minimum date filter in DD-MM-YYYY format (default: "01-01-2000")
        doctypes: Filter by document types (default: "judgments")
            Examples:
            - "judgments" - All judgments (SC, HC, District Courts)
            - "supremecourt" - Supreme Court only
            - "delhi", "bombay", "kolkata", "chennai" - Specific High Courts
            - "judgments,supremecourt" - Combine multiple (comma-separated)
            - "highcourts,cci" - High courts + specific tribunal
            - "laws" - Central Acts and Rules
            - "tribunals" - All tribunals
        todate: Maximum date filter in DD-MM-YYYY format (e.g., "31-12-2024")
        title_filter: Words/phrases that must appear in document title (e.g., "NDPS")
            Use this to ensure results have specific keywords in the title
        cite_filter: Filter by citation (e.g., "1993 AIR")
            Restrict search to documents with a specific citation
        author_filter: Filter by judge/author name (e.g., "arijit pasayat")
            Find judgments written by a particular judge
        bench_filter: Filter by judge in bench (e.g., "arijit pasayat")
            Find judgments where a specific judge was on the bench
        maxcites: Number of citations to return per document (max 50)
            Get list of citations for matching documents in search results
        maxpages: Number of pages to fetch in one call (max 1000)
            Fetch multiple pages in a single API call (only used on first page)
        fir_context: FIR content context for relevancy scoring (optional)
            Used by LLM to determine relevancy score of cases
    
    Returns:
        List of dictionaries with case information:
        [
            {
                "title": case_title,
                "url": f"https://indiankanoon.org/doc/{doc_id}/",
                "summary": content_preview,
                "case_number": case_number,
                "year": year,
                "case_id": f"{case_number}_{year}",
                "score": relevance_score,
                "content": full_document_content
            }
        ]
    
    Example:
        # Basic search
        results = search_indian_kanoon("NDPS bail Ganja", max_results=10)
        
        # Advanced search with filters
        results = search_indian_kanoon(
            search_query="commercial quantity Cannabis",
            max_results=10,
            fromdate="01-01-2020",
            doctypes="judgments,supremecourt",
            title_filter="NDPS",
            author_filter="arijit pasayat"
        )
    """
    
    logger.info(f"Searching Indian Kanoon with query: {search_query}")
    
    # OPTIMIZATION: Use better defaults for relevance
    if doctypes == "judgments":
        doctypes = "judgments,supremecourt,highcourts"  # Prioritize authoritative courts
    
    if title_filter is None:
        title_filter = "NDPS"  # Ensure NDPS relevance
    
    if maxcites is None:
        maxcites = 5  # Get citations for relevance
    
    # STEP 1: First, get unique document IDs from search results
    # Use maxpages to fetch multiple pages in one call for speed
    unique_docs = []
    processed_ids = set()
    pagenum = 0
    max_pages_to_search = 2  # Reduced since we fetch more pages per call
    MAX_DOCSIZE = 500000  # Filter out documents larger than 500K chars
    
    # Use maxpages on first call to get more results quickly
    effective_maxpages = maxpages if maxpages else 10  # Fetch 10 pages in one call
    
    while len(unique_docs) < max_results and pagenum < max_pages_to_search:
        try:
            search_url = build_search_url(
                search_query=search_query,
                pagenum=pagenum,
                doctypes=doctypes,
                fromdate=fromdate,
                todate=todate,
                title_filter=title_filter,
                cite_filter=cite_filter,
                author_filter=author_filter,
                bench_filter=bench_filter,
                maxcites=maxcites,
                maxpages=effective_maxpages if pagenum == 0 else None  # Use maxpages on first page
            )
            
            response = requests.post(search_url, headers=get_headers(), timeout=30)
            
            if response.status_code == 200:
                try:
                    data = response.json()
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON response: {e}")
                    logger.error(f"Response text: {response.text[:500]}")
                    break
                    
                docs = data.get('docs', [])
                
                # Log response details for debugging
                if pagenum == 0:
                    logger.debug(f"Search URL: {search_url}")
                    logger.debug(f"API response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                    logger.debug(f"Total docs in response: {len(docs) if docs else 0}")
                    if isinstance(data, dict):
                        logger.debug(f"Response metadata: {json.dumps({k: v for k, v in data.items() if k != 'docs'}, indent=2)[:500]}")
                
                if not docs:
                    logger.info(f"No more results found at page {pagenum}")
                    if pagenum == 0:
                        logger.warning(f"Initial search returned 0 results. Query: '{search_query}'")
                    break
                
                # Collect unique document IDs with docsize filtering
                for doc in docs:
                    doc_id = doc.get('tid')
                    docsize = doc.get('docsize', 0)  # Get document size from API
                    
                    if doc_id and doc_id not in processed_ids:
                        # Filter out documents that are too large
                        if docsize > MAX_DOCSIZE:
                            logger.debug(f"Skipping document {doc_id} - too large ({docsize:,} chars)")
                            continue
                            
                        processed_ids.add(doc_id)
                        unique_docs.append({
                            'tid': doc_id,
                            'title': doc.get('title', 'N/A'),
                            'headline': doc.get('headline', ''),
                            'docsource': doc.get('docsource', ''),
                            'docsize': docsize,
                        })
                        
                        if len(unique_docs) >= max_results:
                            break
                
                logger.info(f"Found {len(unique_docs)} unique documents so far (searched page {pagenum})")
                
            elif response.status_code == 403:
                logger.error("Authentication failed. Please check your API token.")
                return []
            else:
                logger.warning(f"Search API returned status {response.status_code}: {response.text}")
                break
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error at page {pagenum}: {e}")
            break
        except Exception as e:
            logger.error(f"Unexpected error at page {pagenum}: {e}")
            break
        
        pagenum += 1
        if pagenum > 0:  # Only delay between pages
            time.sleep(0.2)  # Reduced delay
    
    logger.info(f"Found {len(unique_docs)} unique documents, now fetching full content in parallel...")
    
    # STEP 2: Fetch and process documents in parallel for speed
    def fetch_and_process_doc(doc_info):
        """Fetch and process a single document"""
        doc_id = doc_info['tid']
        title = doc_info['title']
        
        try:
            # Fetch full document
            full_content, doc_metadata = fetch_full_document(doc_id)
            
            if not full_content:
                logger.warning(f"Could not fetch content for document {doc_id}")
                return None
            
            # Limit content
            limited_content = limit_content_for_llm(full_content, max_content_tokens=80000)
            
            # Summarize with LLM
            try:
                summary_result = summarizer_llm.invoke(
                    summary_prompt.format(
                        case_title=title,
                        case_content=limited_content,
                        search_query=search_query or "Not provided"
                    )
                )
                
                case_title_llm = summary_result.case_title if hasattr(summary_result, 'case_title') else title
                content_preview = summary_result.case_summary if hasattr(summary_result, 'case_summary') else str(summary_result)
                case_number = summary_result.case_number if hasattr(summary_result, 'case_number') else None
                year = summary_result.year if hasattr(summary_result, 'year') else None
                relevancy_score = summary_result.relevancy_score if hasattr(summary_result, 'relevancy_score') else 5
                
            except Exception as e:
                logger.warning(f"Error summarizing case {title}: {e}")
                content_preview = full_content[:500] + "..." if len(full_content) > 500 else full_content
                relevancy_score = 5
                case_title_llm = title
                case_number = None
                year = None
            
            case_id = f"{case_number}_{year}" if case_number and year else f"doc_{doc_id}"
            
            return {
                "title": case_title_llm,
                "url": f"https://indiankanoon.org/doc/{doc_id}/",
                "summary": content_preview,
                "case_number": case_number,
                "year": year,
                "case_id": case_id,
                "score": float(relevancy_score)
            }
            
        except Exception as e:
            logger.error(f"Error processing document {doc_id}: {e}")
            return None
    
    # Fetch documents in parallel (5 concurrent workers)
    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_doc = {executor.submit(fetch_and_process_doc, doc_info): doc_info 
                         for doc_info in unique_docs[:max_results]}
        
        for future in as_completed(future_to_doc):
            result = future.result()
            if result:
                results.append(result)
    
    # Sort by relevancy score (highest first) to get most relevant cases
    results.sort(key=lambda x: x.get('score', 0), reverse=True)
    
    logger.info(f"Successfully fetched {len(results)} cases from Indian Kanoon")
    return results

# ============================================================================
# LangGraph Node Function
# ============================================================================

class SearchQueryAndKeywords(BaseModel):
    search_query: str = Field(description="A specific search query to find relevant court judgments in NDPS cases from Indian Kanoon database")
    keywords: list[str] = Field(description="List of important keywords extracted from FIR including substance name, legal terms, and case characteristics. MUST always include 'BAIL' as one of the keywords. Include substance name variations if applicable.")
    substance_name: str | None = Field(default=None, description="The specific narcotic drug or psychotropic substance mentioned in the FIR (e.g., Ganja, Cannabis, Heroin, Cocaine, Charas, etc.). Return None if not clearly identifiable.")

def historical_cases(state: WorkflowState) -> dict:
    """
    LangGraph node function to search for historical cases using Indian Kanoon API.
    
    Simple flow:
    1. Generate search query and keywords from FIR content (single LLM call)
    2. Search Indian Kanoon API for relevant NDPS cases (after 2000)
    3. Get full document for each case
    4. Summarize each document individually (max 2000 words) with relevancy score (0-10)
    5. Return results with full text preserved for future use
    
    Args:
        state: WorkflowState containing pdf_content_in_english
        
    Returns:
        Dictionary with "historical_cases" key containing list of case dictionaries
        Each case includes: title, url, summary (max 2K words), case_number, year, 
        case_id, score (0-10 relevancy), and full content
    """
    logger.info("Starting historical cases search using Indian Kanoon API")
    
    if not state.get("pdf_content_in_english"):
        raise ValueError("pdf_content_in_english is required for historical cases search")
    
    pdf_content = state["pdf_content_in_english"]
    logger.debug(f"FIR content length: {len(pdf_content)} characters")
    
    # Generate search query and keywords in one LLM call
    # Focus on contextual details: minor, women, bag, etc.
    prompt = f"""Based on the following FIR content, create a search query and extract important keywords to find relevant court judgments in NDPS cases from Indian Kanoon database.

FIR Content: {pdf_content}

CRITICAL REQUIREMENTS:
1. You MUST identify the specific substance/drug mentioned in the FIR (e.g., Ganja, Cannabis, Heroin, Cocaine, etc.)
2. The search query MUST include the substance name to ensure relevance
3. Pay special attention to:
   - If accused is a MINOR/JUVENILE - include "minor" or "juvenile" in search query
   - If accused is a WOMAN/FEMALE - include "woman" or "female" in search query
   - If contraband was found in BAG/LUGGAGE - include "bag" or "luggage" in search query
   - Quantity seized (small/intermediate/commercial)
   - Procedural issues

For search_query:
- Create a SHORT, focused search query (maximum 6-8 words)
- MUST include the substance name (e.g., "Ganja", "Cannabis", "Heroin")
- Include 1-2 key contextual terms: "bail", "NDPS", "minor" (if applicable), "woman" (if applicable), "bag" (if applicable), "commercial quantity", etc.
- Keep it SIMPLE - avoid exact quantities, specific section numbers, or too many details
- Examples: 
  * "Ganja NDPS minor bail" (if minor involved)
  * "Cannabis NDPS woman bail" (if woman involved)
  * "Heroin NDPS bag bail" (if found in bag)
  * "Ganja NDPS bail" (general)
- DO NOT include: exact quantities (like "36.525 kg"), specific section numbers, or lengthy descriptions

For keywords:
- MUST ALWAYS include "BAIL" as one of the keywords
- Include the substance name and its common variations (e.g., "Ganja", "Cannabis", "Marijuana" for cannabis cases)
- Include "NDPS" 
- Include contextual keywords: "minor" (if applicable), "juvenile" (if applicable), "woman" (if applicable), "female" (if applicable), "bag" (if applicable), "luggage" (if applicable)
- Include other relevant legal terms like: "bail", "commercial quantity", "small quantity", "Section 50", etc.
- Return keywords as a list of strings

For substance_name:
- Identify the primary narcotic drug or psychotropic substance mentioned in the FIR
- Use the most common name (e.g., "Ganja" for cannabis, "Heroin" for diacetylmorphine)
- Return None if substance is not clearly identifiable

Instructions:
1. First identify the specific substance/drug mentioned in the FIR
2. Check if accused is MINOR/JUVENILE - if yes, include in search query
3. Check if accused is WOMAN/FEMALE - if yes, include in search query
4. Check if contraband was found in BAG/LUGGAGE - if yes, include in search query
5. Extract quantity seized and other key facts
6. Create a focused search query that includes substance name + contextual terms (minor/woman/bag if applicable) + "bail"
7. Extract 5-10 important keywords including substance name, variations, "NDPS", "BAIL" (mandatory), and contextual terms
8. Identify the primary substance name

Generate search_query, keywords, and substance_name:
"""
    
    search_data = llm_model.with_structured_output(SearchQueryAndKeywords).invoke(prompt)
    search_query = search_data.search_query
    keywords = search_data.keywords
    fir_substance = search_data.substance_name.lower() if search_data.substance_name else None
    
    # Ensure BAIL is in keywords (add if missing)
    if "BAIL" not in [k.upper() for k in keywords]:
        keywords.append("BAIL")
    
    logger.info(f"Generated search query: {search_query}")
    logger.info(f"Extracted keywords: {keywords}")
    logger.info(f"Identified substance: {fir_substance or 'Not specified'}")
    
    historical_cases_list = []
    processed_case_ids = set()
    
    try:
        # Search using main search query with optimizations
        logger.info("Searching with main query...")
        results = search_indian_kanoon(
            search_query=search_query,
            max_results=6,  # Focus on 5-6 extremely relevant cases
            fromdate="01-01-2010",  # Focus on last 15 years for more relevant cases
            doctypes="judgments",  # Will be upgraded to include supremecourt,highcourts in function
            title_filter="NDPS",  # Ensure NDPS relevance
            maxcites=5,  # Get citations for relevance
            maxpages=10,  # Fetch 10 pages in one call for speed
            fir_context=pdf_content  # Pass FIR content for relevancy scoring
        )
        
        # Process results from main search
        for result in results:
            case_id = result.get('case_id', '')
            if case_id and case_id not in processed_case_ids:
                processed_case_ids.add(case_id)
                historical_cases_list.append(result)
        
        # If main query returned no results, try fallback searches with keywords
        if len(historical_cases_list) == 0:
            logger.warning(f"Main query returned 0 results, trying fallback searches with keywords...")
            
            # Try simpler queries using keywords
            fallback_queries = []
            
            # Build fallback queries from keywords
            if fir_substance:
                # Try substance + "NDPS" + "bail"
                fallback_queries.append(f"{fir_substance.capitalize()} NDPS bail")
                fallback_queries.append(f"{fir_substance.capitalize()} NDPS")
                fallback_queries.append(f"NDPS {fir_substance.capitalize()}")
            
            # Try with "BAIL" and substance
            if "BAIL" in [k.upper() for k in keywords] and fir_substance:
                fallback_queries.append(f"{fir_substance.capitalize()} bail")
            
            # Try just "NDPS bail" if we have substance
            if fir_substance:
                fallback_queries.append("NDPS bail")
            
            # Try each fallback query
            for fallback_query in fallback_queries[:3]:  # Limit to 3 fallback attempts
                if len(historical_cases_list) >= 6:  # Focus on 5-6 cases
                    break
                    
                logger.info(f"Trying fallback query: {fallback_query}")
                try:
                    fallback_results = search_indian_kanoon(
                        search_query=fallback_query,
                        max_results=6 - len(historical_cases_list),  # Focus on 5-6 cases
                        fromdate="01-01-2010",  # Last 15 years
                        doctypes="judgments",
                        title_filter="NDPS",
                        maxcites=5,
                        maxpages=10,
                        fir_context=pdf_content
                    )
                    
                    for result in fallback_results:
                        case_id = result.get('case_id', '')
                        if case_id and case_id not in processed_case_ids:
                            processed_case_ids.add(case_id)
                            historical_cases_list.append(result)
                            
                    if len(historical_cases_list) > 0:
                        logger.info(f"Fallback query '{fallback_query}' found {len(historical_cases_list)} cases")
                        break
                except Exception as e:
                    logger.warning(f"Fallback query '{fallback_query}' failed: {e}")
                    continue
        
        # Simple processing - no additional filtering needed
        filtered_cases = []
        for result in historical_cases_list:
            case_id = result.get('case_id', '')
            case_number = result.get('case_number')
            year = result.get('year')
            title = result.get('title', 'NDPS Case')
            url = result.get('url')
            score = result.get('score', 0.0)
            summary = result.get('summary', '')
            
            case_data = {
                "title": title,
                "url": url,
                "summary": summary,
                "case_number": case_number,
                "year": year,
                "case_id": case_id,
                "score": float(score)
            }
            filtered_cases.append(case_data)
            
            # Stop if we have enough cases (focus on 5-6 extremely relevant)
            if len(filtered_cases) >= 6:
                break
        
        historical_cases_list = filtered_cases
                
    except Exception as e:
        logger.error(f"Error searching Indian Kanoon with query '{search_query}': {e}")
    
    logger.info(f"Found {len(historical_cases_list)} historical cases from Indian Kanoon")
    
    return {
        "historical_cases": historical_cases_list
    }

# Example usage when run as script
if __name__ == "__main__":
    # Example 1: Basic search
    test_query = "NDPS case minor caught with Ganja"
    results = search_indian_kanoon(
        test_query, 
        max_results=10, 
        fromdate="01-01-2000"
    )
    
    # Example 2: Advanced search with optional parameters
    # results = search_indian_kanoon(
    #     search_query="bail application Ganja NDPS",
    #     max_results=10,
    #     fromdate="01-01-2000",
    #     doctypes="judgments,supremecourt",  # Search in judgments and Supreme Court
    #     todate="31-12-2024",
    #     title_filter="NDPS",  # Must have "NDPS" in title
    #     author_filter="arijit pasayat",  # Filter by judge
    #     maxcites=20  # Get up to 20 citations per document
    # )
    
    print(f"\n✓ Found {len(results)} cases")
    for i, case in enumerate(results, 1):
        print(f"\n[{i}] {case['title']}")
        print(f"    URL: {case['url']}")
        print(f"    Case ID: {case['case_id']}")
        print(f"    Summary: {case['summary'][:100]}...")
    
    # Save to JSON file for testing
        output_file = 'cases_simplified.json'
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n✓ Saved results to '{output_file}'")
