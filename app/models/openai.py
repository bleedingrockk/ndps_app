import os
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from dotenv import load_dotenv
from typing import Union, List
import numpy as np

load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")

llm_model = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0.1,
    api_key=openai_api_key,
    max_tokens=None,
    timeout=None,
    max_retries=2
)

embedding_model = OpenAIEmbeddings(
    model="text-embedding-3-large",
    api_key=openai_api_key,
)


def get_embedding(text: Union[str, List[str]], normalize: bool = False) -> np.ndarray:
    """
    Generate embeddings using OpenAI's text-embedding-3-large model.
    
    Args:
        text: A single string or list of strings to embed
        normalize: Whether to apply L2 normalization to embeddings
        
    Returns:
        numpy array of embeddings
    """
    is_single = isinstance(text, str)
    texts = [text] if is_single else text
    
    # Get embeddings from OpenAI
    embeddings = embedding_model.embed_documents(texts)
    embeddings_array = np.array(embeddings, dtype='float32')
    
    # Apply L2 normalization if requested
    if normalize:
        norms = np.linalg.norm(embeddings_array, axis=1, keepdims=True)
        embeddings_array = embeddings_array / norms
    
    return embeddings_array[0] if is_single else embeddings_array



