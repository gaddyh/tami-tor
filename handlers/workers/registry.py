# handlers/work_registry.py
from handlers.workers.inbound import handle_process_inbound
from handlers.workers.tami_scheduled_message import handle_scheduled_message

WORK_HANDLERS = {
    "INBOUND": handle_process_inbound,
    "SCHEDULED_MESSAGE": handle_scheduled_message, #tami
    # "CALENDAR": handle_calendar_work,
}
