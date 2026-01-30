# observability/langfuse_client.py
from langfuse import get_client
from dotenv import load_dotenv

load_dotenv(".venv/.env")
# 1 global instance for whole system
langfuse = get_client()
