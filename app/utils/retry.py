"""
Utility module for retry decorators with exponential backoff.
"""
import time
import random
import logging
from functools import wraps

logger = logging.getLogger(__name__)


def exponential_backoff_retry(max_retries=5, max_wait=60):
    """
    Decorator for exponential backoff retry on LLM calls.
    
    Args:
        max_retries: Maximum number of retry attempts (5 means 1 initial + 5 retries = 6 total)
        max_wait: Maximum wait time in seconds (60 seconds = 1 minute)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempt = 0
            base_wait = 1  # Start with 1 second
            
            while attempt <= max_retries:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt >= max_retries:
                        logger.error(f"Failed after {max_retries + 1} attempts: {str(e)}")
                        raise
                    
                    # Calculate wait time: exponential backoff with jitter, capped at max_wait
                    wait_time = min(base_wait * (2 ** attempt), max_wait)
                    # Add jitter (random 0-10% to avoid thundering herd)
                    wait_time = wait_time * (1 + random.uniform(0, 0.1))
                    
                    attempt += 1
                    logger.warning(f"LLM call failed (attempt {attempt}/{max_retries + 1}), retrying in {wait_time:.1f}s...")
                    time.sleep(wait_time)
            
            # Should never reach here, but just in case
            raise Exception(f"Failed after {max_retries + 1} attempts")
        
        return wrapper
    return decorator
