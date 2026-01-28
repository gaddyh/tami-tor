# handlers/work_registry.py
from handlers.inbound import handle_process_inbound
from handlers.scheduled_message_handler import handle_scheduled

WORK_HANDLERS = {
    "INBOUND": handle_process_inbound,
    # "CALENDAR": handle_calendar_work,
    "SCHEDULED": handle_scheduled,
}
