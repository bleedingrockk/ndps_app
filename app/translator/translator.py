import os
import requests
import uuid
import json
from app.langgraph.state import WorkflowState

def translate_to_english(state: WorkflowState) -> dict:
    """
    Translate PDF content to English using Azure Translator.
    Works as a LangGraph node that accepts state and returns updated state.
    
    Args:
        state: WorkflowState containing pdf_content
        
    Returns:
        Dictionary with translated content in pdf_content_in_english
    """
    if not state.get("pdf_content"):
        raise ValueError("pdf_content is required for translation")
    
    pdf_content = state["pdf_content"]
    print("Translation started")
    try:
        # Retrieve configuration from environment variables
        key = os.environ.get("AZURE_TRANSLATOR_KEY")
        location = os.environ.get("AZURE_TRANSLATOR_LOCATION")
        endpoint = os.environ.get("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com")
        
        if not key or not location:
            raise ValueError("AZURE_TRANSLATOR_KEY and AZURE_TRANSLATOR_LOCATION must be set in .env")

        path = '/translate'
        constructed_url = endpoint + path

        params = {
            'api-version': '3.0',
            'to': ['en']  # Translating TO English
        }

        headers = {
            'Ocp-Apim-Subscription-Key': key,
            # location required if you're using a multi-service or regional (not global) resource.
            'Ocp-Apim-Subscription-Region': location,
            'Content-type': 'application/json',
            'X-ClientTraceId': str(uuid.uuid4())
        }

        # You can pass more than one object in body.
        body = [{
            'text': pdf_content
        }]

        print(f"📡 [translate_to_english] Sending request to {endpoint} (timeout=10s)...")
        request = requests.post(constructed_url, params=params, headers=headers, json=body, timeout=10)
        print("✅ [translate_to_english] Received response from Azure.")
        
        response = request.json()

        # Check for error in response
        if isinstance(response, dict) and "error" in response:
             raise Exception(f"Azure API Error: {response['error']}")

        # Extract translated text
        # Response structure is valid for multiple inputs: [{'translations': [{'text': '...', 'to': 'en'}]}]
        translated_text = response[0]['translations'][0]['text']
        
        print(f"✅ [translate_to_english] Translation completed, output length: {len(translated_text)} characters")
        print("=" * 80)
        
        return {"pdf_content_in_english": translated_text}

    except Exception as e:
        raise Exception(f"Error translating content: {str(e)}")

if __name__ == "__main__":
    # For local testing - Direct API Call (No project imports needed)
    from dotenv import load_dotenv
    import os
    import requests
    import uuid
    import json
    
    # Load env from .env in current or parent directory
    load_dotenv(".env")
    
    print("🚀 Starting Translator Direct Test...")

    key = os.environ.get("AZURE_TRANSLATOR_KEY")
    location = os.environ.get("AZURE_TRANSLATOR_LOCATION")
    endpoint = os.environ.get("AZURE_TRANSLATOR_ENDPOINT", "https://api.cognitive.microsofttranslator.com")
    
    if not key or not location:
         print("❌ Error: AZURE_TRANSLATOR_KEY and AZURE_TRANSLATOR_LOCATION not found in .env")
    else:
        path = '/translate'
        constructed_url = endpoint + path

        params = {
            'api-version': '3.0',
            'to': ['en']  # Translate to English
        }

        headers = {
            'Ocp-Apim-Subscription-Key': key,
            'Ocp-Apim-Subscription-Region': location,
            'Content-type': 'application/json',
            'X-ClientTraceId': str(uuid.uuid4())
        }

        body = [{
             'text': 'કેમ છો દુનિયા! હું ખરેખર તમારી કારને બ્લોકની આસપાસ થોડી વાર ચલાવવા માંગુ છું!'
        }]
        
        try:
            print(f"📡 Sending request to {endpoint}...")
            request = requests.post(constructed_url, params=params, headers=headers, json=body)
            response = request.json()
            
            print(json.dumps(response, sort_keys=True, ensure_ascii=False, indent=4, separators=(',', ': ')))
            
            if isinstance(response, list) and 'translations' in response[0]:
                 print(f"\n✅ Translated: {response[0]['translations'][0]['text']}")
            else:
                 print("\n⚠️ Unexpected response format.")

        except Exception as e:
            print(f"\n❌ Error during test: {e}")

