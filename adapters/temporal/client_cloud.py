import os
from temporalio.client import Client
from dotenv import load_dotenv

load_dotenv(".venv/.env")

async def temporal_client_from_env() -> Client:
    address = os.getenv("TEMPORAL_ADDRESS") 
    namespace = os.getenv("TEMPORAL_NAMESPACE")     
    api_key = os.getenv("TEMPORAL_API_KEY")

    return await Client.connect(
        address,
        namespace=namespace,
        api_key=api_key,
        tls=True,  # required for Temporal Cloud API-key auth
    )
