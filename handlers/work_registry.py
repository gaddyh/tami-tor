# handlers/work_registry.py
from handlers.inbound_work import handle_inbound_work

WORK_HANDLERS = {
    "INBOUND": handle_inbound_work,
    # "CALENDAR": handle_calendar_work,
    # "SCHEDULED": handle_scheduled_work,
}
