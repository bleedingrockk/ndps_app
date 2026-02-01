import faiss
import numpy as np
import json
from typing import List, Dict
from pathlib import Path
from app.models.openai import embedding_model

# Base path for RAG data
RAG_BASE_PATH = Path(__file__).parent

# Cache for loaded indices and chunks
_index_cache = {}
_chunks_cache = {}


def _load_index(act_code: str):
    """Load index and chunks for an act (cached)"""
    if act_code in _index_cache:
        return _index_cache[act_code], _chunks_cache[act_code]
    
    configs = {
        'bns': {
            'chunks_path': RAG_BASE_PATH / 'bns' / 'chunks.json',
            'index_path': RAG_BASE_PATH / 'bns' / 'legal_index.faiss'
        },
        'bnss': {
            'chunks_path': RAG_BASE_PATH / 'bnss' / 'chunks.json',
            'index_path': RAG_BASE_PATH / 'bnss' / 'legal_index.faiss'
        },
        'bsa': {
            'chunks_path': RAG_BASE_PATH / 'bsa' / 'chunks.json',
            'index_path': RAG_BASE_PATH / 'bsa' / 'legal_index.faiss'
        },
        'ndps': {
            'chunks_path': RAG_BASE_PATH / 'ndps' / 'chunks.json',
            'index_path': RAG_BASE_PATH / 'ndps' / 'legal_index.faiss'
        },
        'forensic': {
            'chunks_path': RAG_BASE_PATH / 'forensic' / 'chunks.json',
            'index_path': RAG_BASE_PATH / 'forensic' / 'legal_index.faiss'
        },
        'ndps_judgements': {
            'chunks_path': RAG_BASE_PATH / 'ndps_judgements' / 'chunks.json',
            'index_path': RAG_BASE_PATH / 'ndps_judgements' / 'legal_index.faiss'
        }
    }
    
    if act_code not in configs:
        raise ValueError(f"Unknown act code: {act_code}")
    
    config = configs[act_code]
    
    if not config['index_path'].exists() or not config['chunks_path'].exists():
        raise FileNotFoundError(f"Index files not found for {act_code}")
    
    index = faiss.read_index(str(config['index_path']))
    with open(config['chunks_path'], 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    
    _index_cache[act_code] = index
    _chunks_cache[act_code] = chunks
    
    return index, chunks


def query_bns(query: str, k: int = 5) -> List[Dict]:
    """
    Query Bharatiya Nyaya Sanhita (BNS)
    
    Args:
        query: Search query
        k: Number of results to return
        
    Returns:
        List of results with 'chunk' and 'score' keys
    """
    index, chunks = _load_index('bns')
    
    # Generate query embedding
    query_vector = embedding_model.embed_query(query)
    query_vector = np.array([query_vector]).astype('float32')
    faiss.normalize_L2(query_vector)
    
    # Search
    scores, indices = index.search(query_vector, k)
    
    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < len(chunks):
            results.append({
                'chunk': chunks[idx],
                'score': float(score)
            })
    
    return results


def query_bnss(query: str, k: int = 5) -> List[Dict]:
    """
    Query Bharatiya Nagarik Suraksha Sanhita (BNSS)
    
    Args:
        query: Search query
        k: Number of results to return
        
    Returns:
        List of results with 'chunk' and 'score' keys
    """
    index, chunks = _load_index('bnss')
    
    # Generate query embedding
    query_vector = embedding_model.embed_query(query)
    query_vector = np.array([query_vector]).astype('float32')
    faiss.normalize_L2(query_vector)
    
    # Search
    scores, indices = index.search(query_vector, k)
    
    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < len(chunks):
            results.append({
                'chunk': chunks[idx],
                'score': float(score)
            })
    
    return results


def query_bsa(query: str, k: int = 5) -> List[Dict]:
    """
    Query Bharatiya Sakshya Adhiniyam (BSA)
    
    Args:
        query: Search query
        k: Number of results to return
        
    Returns:
        List of results with 'chunk' and 'score' keys
    """
    index, chunks = _load_index('bsa')
    
    # Generate query embedding
    query_vector = embedding_model.embed_query(query)
    query_vector = np.array([query_vector]).astype('float32')
    faiss.normalize_L2(query_vector)
    
    # Search
    scores, indices = index.search(query_vector, k)
    
    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < len(chunks):
            results.append({
                'chunk': chunks[idx],
                'score': float(score)
            })
    
    return results


def query_ndps(query: str, k: int = 5) -> List[Dict]:
    """
    Query Narcotic Drugs and Psychotropic Substances Act (NDPS)
    
    Args:
        query: Search query
        k: Number of results to return
        
    Returns:
        List of results with 'chunk' and 'score' keys
    """
    index, chunks = _load_index('ndps')
    
    # Generate query embedding
    query_vector = embedding_model.embed_query(query)
    query_vector = np.array([query_vector]).astype('float32')
    faiss.normalize_L2(query_vector)
    
    # Search
    scores, indices = index.search(query_vector, k)
    
    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < len(chunks):
            results.append({
                'chunk': chunks[idx],
                'score': float(score)
            })
    
    return results


def query_forensic(query: str, k: int = 5) -> List[Dict]:
    """
    Query Forensic Guide for Crime Investigators - NDPS Chapter
    
    Args:
        query: Search query
        k: Number of results to return
        
    Returns:
        List of results with 'chunk' and 'score' keys
    """
    index, chunks = _load_index('forensic')
    
    # Generate query embedding
    query_vector = embedding_model.embed_query(query)
    query_vector = np.array([query_vector]).astype('float32')
    faiss.normalize_L2(query_vector)
    
    # Search
    scores, indices = index.search(query_vector, k)
    
    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < len(chunks):
            results.append({
                'chunk': chunks[idx],
                'score': float(score)
            })
    
    return results


def query_ndps_judgements(query: str, k: int = 5) -> List[Dict]:
    """
    Query NDPS Historical Judgements
    
    Args:
        query: Search query
        k: Number of results to return
        
    Returns:
        List of results with 'chunk' and 'score' keys
    """
    index, chunks = _load_index('ndps_judgements')
    
    # Generate query embedding
    query_vector = embedding_model.embed_query(query)
    query_vector = np.array([query_vector]).astype('float32')
    faiss.normalize_L2(query_vector)
    
    # Search
    scores, indices = index.search(query_vector, k)
    
    results = []
    for idx, score in zip(indices[0], scores[0]):
        if idx < len(chunks):
            results.append({
                'chunk': chunks[idx],
                'score': float(score)
            })
    
    return results
