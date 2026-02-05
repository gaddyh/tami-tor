# handlers/work_registry.py
from handlers.workers.inbound import handle_process_inbound
from handlers.workers.scheduled_message_handler import handle_dynamic_list
from handlers.workers.tami_scheduled_message import handle_scheduled_message

WORK_HANDLERS = {
    "INBOUND": handle_process_inbound,
    # "CALENDAR": handle_calendar_work,
    "DYNAMIC_LIST": handle_dynamic_list,
    "SCHEDULED_MESSAGE": handle_scheduled_message,
}
