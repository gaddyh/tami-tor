# handlers/work_registry.py
from handlers.inbound import handle_process_inbound

WORK_HANDLERS = {
    "INBOUND": handle_process_inbound,
    # "CALENDAR": handle_calendar_work,
    # "SCHEDULED": handle_scheduled_work,
}
