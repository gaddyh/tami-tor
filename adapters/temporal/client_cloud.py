import os
from temporalio.client import Client
from dotenv import load_dotenv

load_dotenv(".venv/.env")

async def temporal_client_from_env() -> Client:
    address = os.environ["TEMPORAL_ADDRESS"]          # e.g. xxx.tmprl.cloud:7233
    namespace = os.environ["TEMPORAL_NAMESPACE"]      # e.g. tami-prod.a1b2c
    api_key = os.environ["TEMPORAL_API_KEY"]

    return await Client.connect(
        address,
        namespace=namespace,
        api_key=api_key,
        tls=True,  # required for Temporal Cloud API-key auth
    )
