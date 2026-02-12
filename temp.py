import os
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv


load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")
llm_model = ChatOpenAI(
    model="gpt-4.1",
    temperature=0.1,
    api_key=openai_api_key,
    max_tokens=None,
    timeout=None,
    max_retries=2
)
print(llm_model.invoke("Hi").content)
