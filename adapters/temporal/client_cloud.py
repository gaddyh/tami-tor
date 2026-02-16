import os
from temporalio.client import Client
from dotenv import load_dotenv

load_dotenv(".venv/.env")

async def temporal_client_from_env() -> Client:
    address = os.getenv("TEMPORAL_ADDRESS") 
    namespace = os.getenv("TEMPORAL_NAMESPACE")     
    api_key = os.getenv("TEMPORAL_API_KEY")

    print("address:", address)
    print("namespace:", namespace)
    print("api_key:", api_key)

    print("TEMPORAL_ADDRESS present:", "TEMPORAL_ADDRESS" in os.environ, flush=True)
    print("TEMPORAL_NAMESPACE present:", "TEMPORAL_NAMESPACE" in os.environ, flush=True)
    print("TEMPORAL_API_KEY present:", "TEMPORAL_API_KEY" in os.environ, flush=True)
    print("ENV sample keys:", sorted(list(os.environ.keys()))[:30], flush=True)

    return await Client.connect(
        address,
        namespace=namespace,
        api_key=api_key,
        tls=True,  # required for Temporal Cloud API-key auth
    )
