from typing import NamedTuple, Literal, Optional

from models.session_state import SessionFlow, SessionStep

class RouteKey(NamedTuple):
    flow: SessionFlow
    step: SessionStep

from typing import Callable, Dict

Handler = Callable[[dict], dict]

INBOUND_REGISTRY: Dict[RouteKey, Handler] = {}
