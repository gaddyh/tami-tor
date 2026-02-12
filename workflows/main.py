from models.business import Business
from workflows.booking_with_signal import BookingWorkflow, BookingParams, InboundEvent
from workflows.client_session import ClientSessionWorkflow
from workflows.provider_session import ProviderWorkflow
from temporalio.client import Client

TASK_QUEUE = "booking"

from temporalio.client import WithStartWorkflowOperation
from temporalio import common
from temporalio.client import Client

from workflows.main import TASK_QUEUE


async def update_client_workflow_with_start(
    *,
    temporal_client: Client,
    business_id: str,
    client_id: str,
    ev: InboundEvent,
) -> None:
    wf_id = f"client:{business_id}:{client_id}"

    start_op = WithStartWorkflowOperation(
        ClientSessionWorkflow.run,
        id=wf_id,
        task_queue=TASK_QUEUE,
        id_conflict_policy=common.WorkflowIDConflictPolicy.USE_EXISTING,
    )

    await temporal_client.execute_update_with_start_workflow(
        ClientSessionWorkflow.ingest,
        ev,
        start_workflow_operation=start_op,
    )

async def update_provider_workflow_with_start(
    *,
    temporal_client: Client,
    business_id: str,
    client_id: str,
    ev: InboundEvent,
) -> None:
    wf_id = f"provider:{business_id}:{client_id}"

    start_op = WithStartWorkflowOperation(
        ProviderWorkflow.run,
        id=wf_id,
        task_queue=TASK_QUEUE,
        id_conflict_policy=common.WorkflowIDConflictPolicy.USE_EXISTING,
    )

    await temporal_client.execute_update_with_start_workflow(
        ProviderWorkflow.ingest,
        ev,
        start_workflow_operation=start_op,
    )

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.user_route import UserRoute


@dataclass(frozen=True)
class RouteResult:
    business_id: str
    is_provider: bool


async def resolve_user_route_async(db: AsyncSession, user_id: str) -> Optional[RouteResult]:
    if not user_id:
        return None

    stmt = select(UserRoute.business_id, UserRoute.is_provider).where(UserRoute.user_id == user_id).limit(1)
    res = await db.execute(stmt)
    row = res.first()
    if not row:
        return None

    business_id, is_provider = row
    return RouteResult(business_id=business_id, is_provider=bool(is_provider))
