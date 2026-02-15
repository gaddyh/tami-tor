# repos/business_repo.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.business import Business
from db.models.service import Service


async def get_services_by_business_id(
    session: AsyncSession,
    business_id: str,
    *,
    active_only: bool = True,
) -> list[Service]:
    result = await session.execute(
        select(Business).where(Business.business_id == business_id)
    )
    business: Business | None = result.scalar_one_or_none()

    if business is None:
        raise ValueError(f"Business not found: {business_id}")

    raw = business.services_json or []

    if active_only:
        raw = [s for s in raw if s.get("is_active", True)]

    return [Service(**s) for s in raw]

async def get_service_by_id(
    session: AsyncSession,
    business_id: str,
    service_id: str,
) -> Service:
    services = await get_services_by_business_id(session, business_id, active_only=False)
    for s in services:
        if s.id == service_id:
            return s
    raise ValueError(f"Service '{service_id}' not found for business {business_id}")
