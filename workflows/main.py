from workflows.client_session.workflow import ClientSessionWorkflow
from workflows.provider_session import ProviderWorkflow
from temporalio.client import Client

TASK_QUEUE = "booking"

from temporalio.client import WithStartWorkflowOperation
from temporalio import common
from temporalio.client import Client

from workflows.main import TASK_QUEUE
from models.input import InboundEvent

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

if __name__ == "__main__":
    import asyncio
    from sqlalchemy import select

    from db.session_async import get_async_db
    from models.user_route import UserRoute

    async def upsert_user_route(
        *,
        db,
        user_id: str,
        business_id: str,
        is_provider: bool,
    ) -> UserRoute:
        stmt = select(UserRoute).where(UserRoute.user_id == user_id).limit(1)
        existing = (await db.execute(stmt)).scalar_one_or_none()

        if existing:
            existing.business_id = business_id
            existing.is_provider = is_provider
            await db.commit()
            await db.refresh(existing)
            return existing

        row = UserRoute(
            user_id=user_id,
            business_id=business_id,
            is_provider=is_provider,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row

    async def main():
        user_id = "972546610653"
        business_id = "demo-salon"   
        is_provider = False

        async with get_async_db() as db:
            r = await upsert_user_route(
                db=db,
                user_id=user_id,
                business_id=business_id,
                is_provider=is_provider,
            )
            print("Created/updated route:", r.user_id, r.business_id, r.is_provider)

            # verify your resolver
            route = await resolve_user_route_async(db, user_id)
            print("Route result:", route)

    asyncio.run(main())
