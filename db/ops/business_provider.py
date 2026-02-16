# repos/business_repo.py
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from db.models.business import Business

from db.models.business_provider import BusinessProvider
from db.session_async import get_async_db

async def get_business_provider_id(
    session: AsyncSession,
    user_id: str | None = None,
    business_id: str | None = None,
    *,
    active_only: bool = True,
) -> str | None:
    if user_id:
        result = await session.execute(
            select(BusinessProvider).where(BusinessProvider.user_id == user_id and BusinessProvider.business_id == business_id and BusinessProvider.is_active == active_only) 
        )
    elif business_id:
        result = await session.execute(
            select(BusinessProvider).where(BusinessProvider.business_id == business_id and BusinessProvider.is_active == active_only)
        )

    if result is None:
        raise ValueError(f"Business provider not found: {user_id}")

    business_provider: BusinessProvider | None = result.scalar_one_or_none()
    
    return business_provider.id



DEMO_USER_ID = "972546610653"
DEMO_DISPLAY_NAME = "Demo Provider"

async def ensure_demo_provider(session: AsyncSession, business_id: str) -> BusinessProvider:
    q = select(BusinessProvider).where(
        BusinessProvider.business_id == business_id,
        BusinessProvider.user_id == DEMO_USER_ID,
    )
    existing = (await session.execute(q)).scalar_one_or_none()
    if existing:
        return existing

    p = BusinessProvider(
        business_id=business_id,
        user_id=DEMO_USER_ID,
        display_name=DEMO_DISPLAY_NAME,
        email=None,
        timezone="Asia/Jerusalem",
        google_calendar_id="primary",
        is_active=True,
        config_json={"demo": True},
    )
    session.add(p)
    await session.commit()
    await session.refresh(p)
    return p


if __name__ == "__main__":
    async def main():
         async with get_async_db() as db:
            provider = await ensure_demo_provider(db, "demo-salon")
            print(f"Demo provider ensured: {provider.user_id}")
    
    import asyncio
    asyncio.run(main())
