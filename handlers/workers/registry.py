# handlers/work_registry.py
from handlers.workers.registry import handle_process_inbound
from handlers.workers.registry import handle_scheduled
from handlers.workers.registry import handle_scheduled_message

WORK_HANDLERS = {
    "INBOUND": handle_process_inbound,
    # "CALENDAR": handle_calendar_work,
    "SCHEDULED": handle_scheduled,
    "SCHEDULED_MESSAGE": handle_scheduled_message,
}
