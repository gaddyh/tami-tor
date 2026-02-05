from typing import Dict, Any

from models.session_state import InputType, SessionFlow, SessionStep, SessionState, Actor
from adapters.primitivies import RawMessage
from handlers.models import HandlerResult, INBOUND_REGISTRY 
from runtime.session_state import init_state, SessionState, SessionStep, SessionFlow, InputType, get_type
from models.business import Business
from adapters.cloud_api import CloudAPIAdapter
from handlers.inbound.registry import dispatch
from observability.obs import instrument_io

@instrument_io(
    name="tami_tor_dev_handler",
    meta={"operation": "tami_tor_dev_handler"},
    input_fn=lambda business, is_provider, state_json, rawMessage, adapter: {
        "business_id": business.business_id,
        "is_provider": is_provider,
        "state_json": state_json,
        "rawMessage": rawMessage,
        "adapter": adapter
    },
    output_fn=lambda result: result,
    redact=True
)
def tami_tor_dev_handler(business: Business, is_provider: bool, state_json: dict[str, Any], rawMessage: RawMessage, adapter: CloudAPIAdapter) -> HandlerResult:
    if not state_json:
        state = init_state(rawMessage, actor=Actor.CLIENT) #TODO
    else:
        state = SessionState.model_validate(state_json)

    ctx = {
        "is_provider": is_provider,
        "services": business.services(),
        "timezone": business.timezone,
        "booking_policy_mode": business.booking_policy_mode,
        "default_provider_id": business.get_default_provider_id(),
    }

    state.input_type = get_type(rawMessage)

    result = dispatch(state=state, msg=rawMessage, ctx=ctx)

    return result
