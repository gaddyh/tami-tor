from sqlalchemy import select
from sqlalchemy.orm import Session

from models.business import Business

DEMO_BUSINESS = {
    "business_id": "demo-tami",
    "wa_id": "723503380842690",          # WhatsApp phone_number_id
    "agent_id": "default-agent",
    "business_name": "Demo Tami",
    "timezone": "Asia/Jerusalem",
    "booking_policy_mode": "owner_confirm",
    "enable_digest": True,

    "booking_policy_json": {
        "mode": "owner_confirm"
    },

    "reminder_policy_json": {
        "enabled": True,
        "offset_minutes": [1440, 120],
    },

    "working_hours_json": {
        "start": "09:00",
        "end": "17:00",
        "weekend_days": [4, 5],
    },

    "services_json": [
        {
            "id": "haircut",
            "name": "תספורת",
            "duration_min": 30,
            "buffer_min": 5,
            "price": 100,
            "description": "תספורת קלאסית",
            "is_active": True,
        },
    ],

    "providers_json": [
        {
            "provider_id": "972501234567",
            "display_name": "בעלת העסק",
            "email": "owner@example.com",
            "phone": "+972501234567",
            "timezone": "Asia/Jerusalem",
            "google_calendar_id": "primary",
            "is_active": True,
            "specialties": ["haircut"],
        }
    ],
}


def upsert_business(db: Session, payload: dict) -> Business:
    """
    Idempotent upsert of a Business row by business_id.
    Safe to run multiple times.
    """

    business = db.execute(
        select(Business)
        .where(Business.business_id == payload["business_id"])
        .limit(1)
    ).scalar_one_or_none()

    if business:
        # Update existing
        business.wa_id = payload["wa_id"]
        business.agent_id = payload["agent_id"]
        business.business_name = payload["business_name"]
        business.timezone = payload.get("timezone", business.timezone)
        business.booking_policy_mode = payload.get("booking_policy_mode", business.booking_policy_mode)
        business.enable_digest = payload.get("enable_digest", business.enable_digest)

        business.booking_policy_json = payload.get("booking_policy_json", {})
        business.reminder_policy_json = payload.get("reminder_policy_json", {})
        business.working_hours_json = payload.get("working_hours_json", {})
        business.services_json = payload.get("services_json", [])
        business.providers_json = payload.get("providers_json", [])

    else:
        # Insert new
        business = Business(
            business_id=payload["business_id"],
            wa_id=payload["wa_id"],
            agent_id=payload["agent_id"],
            business_name=payload["business_name"],
            timezone=payload.get("timezone", "Asia/Jerusalem"),
            booking_policy_mode=payload.get("booking_policy_mode", "owner_confirm"),
            enable_digest=payload.get("enable_digest", True),

            booking_policy_json=payload.get("booking_policy_json", {}),
            reminder_policy_json=payload.get("reminder_policy_json", {}),
            working_hours_json=payload.get("working_hours_json", {}),
            services_json=payload.get("services_json", []),
            providers_json=payload.get("providers_json", []),
        )
        db.add(business)

    db.commit()
    db.refresh(business)
    return business


if __name__ == "__main__":
    from db.session import SessionLocal

    with SessionLocal() as db:
        biz = upsert_business(db, DEMO_BUSINESS)
        print("Upserted business:", biz.business_id)

