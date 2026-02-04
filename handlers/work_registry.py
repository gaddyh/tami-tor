# handlers/work_registry.py
from handlers.inbound import handle_process_inbound
from handlers.scheduled_message_handler import handle_scheduled
from handlers.tami_scheduled_message import handle_scheduled_message

WORK_HANDLERS = {
    "INBOUND": handle_process_inbound,
    # "CALENDAR": handle_calendar_work,
    "SCHEDULED": handle_scheduled,
    "SCHEDULED_MESSAGE": handle_scheduled_message,
}
