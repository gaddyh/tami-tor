from handlers.hello import handle_hello
from handlers.inbound import handle_process_inbound
from handlers.text_hanlder import handle_text
from handlers.interactive_handler import handle_interactive
from handlers.media_handler import handle_media
from handlers.unknown_handler import handle_unknown

HANDLERS = {
    "HELLO": handle_hello,
    "PROCESS_INBOUND": handle_process_inbound,
}

INBOUND_HANDLERS = {
    "text": handle_text,
    "interactive": handle_interactive,
    "image": handle_media,
    "*": handle_unknown,
}
