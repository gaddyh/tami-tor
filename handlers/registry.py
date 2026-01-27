from handlers.hello import handle_hello
from handlers.inbound import handle_process_inbound

HANDLERS = {
    "HELLO": handle_hello,
    "PROCESS_INBOUND": handle_process_inbound,
}
