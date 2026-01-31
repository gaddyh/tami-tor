# apps/langgraph_flow_stub.py
from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict

import psycopg
from psycopg.rows import dict_row

from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver

from IPython.display import display, Image

# ----------------------------
# Types / State
# ----------------------------

Flow = Literal["client", "provider"]
Expected = Optional[Literal["btn_id", "list_id", "text"]]
InputType = Literal["text", "audio", "btn", "list"]


class Event(TypedDict, total=False):
    type: InputType
    text: str
    transcript: str
    btn_id: str
    list_id: str
    raw: Any


class Effect(TypedDict, total=False):
    effect_id: str
    kind: str
    payload: dict
    business_id: str
    client_id: str


class AppState(TypedDict, total=False):
    thread_id: str
    business_id: str
    client_id: str

    flow: Flow
    step: str
    expected: Expected

    chunked: list[list[dict]]
    chunked_index: int
    slot: Optional[dict]

    last_input: Event
    effects: list[Effect]


# ----------------------------
# Node stubs (common)
# ----------------------------
def schedule_effects(state: AppState) -> AppState:
    """Insert effects into outbox/work_items (stub). Sink-only."""
    return {}


# ----------------------------
# Routers (ONLY for conditional edges)
# ----------------------------

_EXPECTED_ACCEPTS: dict[Expected, set[InputType]] = {
    None: {"text", "audio", "btn", "list"},
    "text": {"text", "audio"},
    "btn_id": {"btn"},
    "list_id": {"list"},
}


def route_input_type(state: AppState) -> InputType:
    return (state.get("last_input") or {}).get("type", "text")  # type: ignore[return-value]


def route_expected(state: AppState) -> Literal["ok", "reprompt"]:
    expected = state.get("expected")
    inp_type = (state.get("last_input") or {}).get("type")
    accepted = _EXPECTED_ACCEPTS.get(expected, _EXPECTED_ACCEPTS[None])
    return ("ok" if inp_type in accepted else "reprompt")


# ----------------------------
# Client nodes (entries + handlers)
# ----------------------------

def client_text_entry(state: AppState) -> AppState: return {}
def client_audio_entry(state: AppState) -> AppState: return {}
def client_btn_entry(state: AppState) -> AppState: return {}
def client_list_entry(state: AppState) -> AppState: return {}

def client_start(state: AppState) -> AppState: return {}
def client_show_slots(state: AppState) -> AppState: return {}
def client_paginate_next(state: AppState) -> AppState: return {}
def client_paginate_prev(state: AppState) -> AppState: return {}
def client_select_slot(state: AppState) -> AppState: return {}
def client_confirm_slot(state: AppState) -> AppState: return {}
def client_cancel(state: AppState) -> AppState: return {}
def client_done(state: AppState) -> AppState: return {}

_CLIENT_STEP_TO_NODE: dict[str, str] = {
    "start": "client_start",
    "show_slots": "client_show_slots",
    "paginate_next": "client_paginate_next",
    "paginate_prev": "client_paginate_prev",
    "select_slot": "client_select_slot",
    "confirm_slot": "client_confirm_slot",
    "cancel": "client_cancel",
    "done": "client_done",
}

def route_client_step(state: AppState) -> str:
    return _CLIENT_STEP_TO_NODE.get(state.get("step", "start"), "client_start")


# ----------------------------
# Provider nodes (entries + handlers)
# ----------------------------

def provider_text_entry(state: AppState) -> AppState: return {}
def provider_audio_entry(state: AppState) -> AppState: return {}
def provider_btn_entry(state: AppState) -> AppState: return {}
def provider_list_entry(state: AppState) -> AppState: return {}

def provider_start(state: AppState) -> AppState: return {}
def provider_create_slots(state: AppState) -> AppState: return {}
def provider_review_slots(state: AppState) -> AppState: return {}
def provider_publish_slots(state: AppState) -> AppState: return {}
def provider_done(state: AppState) -> AppState: return {}

_PROVIDER_STEP_TO_NODE: dict[str, str] = {
    "start": "provider_start",
    "create_slots": "provider_create_slots",
    "review_slots": "provider_review_slots",
    "publish_slots": "provider_publish_slots",
    "done": "provider_done",
}

def route_provider_step(state: AppState) -> str:
    return _PROVIDER_STEP_TO_NODE.get(state.get("step", "start"), "provider_start")


# ----------------------------
# Checkpointer helper
# ----------------------------

def _make_checkpointer(db_uri: str) -> tuple[PostgresSaver, psycopg.Connection]:
    conn = psycopg.connect(db_uri, autocommit=True, row_factory=dict_row)
    checkpointer = PostgresSaver(conn)
    checkpointer.setup()
    return checkpointer, conn


# ----------------------------
# Client graph
# Starts with: (known client) + message type → expected gate → step routing
# ----------------------------

def build_client_graph(db_uri: str):
    sg = StateGraph(AppState)

    # common nodes
    sg.add_node("schedule_effects", schedule_effects)

    # routers (as explicit nodes for nicer diagram)
    sg.add_node("route_client_type", lambda s: {})
    sg.add_node("route_client_step", lambda s: {})

    # entries
    sg.add_node("client_text_entry", client_text_entry)
    sg.add_node("client_audio_entry", client_audio_entry)
    sg.add_node("client_btn_entry", client_btn_entry)
    sg.add_node("client_list_entry", client_list_entry)

    # handlers
    for name, fn in [
        ("client_start", client_start),
        ("client_show_slots", client_show_slots),
        ("client_paginate_next", client_paginate_next),
        ("client_paginate_prev", client_paginate_prev),
        ("client_select_slot", client_select_slot),
        ("client_confirm_slot", client_confirm_slot),
        ("client_cancel", client_cancel),
        ("client_done", client_done),
    ]:
        sg.add_node(name, fn)

    # START → type
    sg.add_edge(START, "route_client_type")

    # type fanout (client)
    sg.add_conditional_edges(
        "route_client_type",
        route_input_type,
        {
            "text": "client_text_entry",
            "audio": "client_audio_entry",
            "btn": "client_btn_entry",
            "list": "client_list_entry",
        },
    )

    # expected gate AFTER type
    for entry in ["client_text_entry", "client_audio_entry", "client_btn_entry", "client_list_entry"]:
        sg.add_conditional_edges(
            entry,
            route_expected,
            {"ok": "route_client_step", "reprompt": "schedule_effects"},
        )

    # step routing
    sg.add_conditional_edges(
        "route_client_step",
        route_client_step,
        {name: name for name in _CLIENT_STEP_TO_NODE.values()},
    )

    # handlers → effects → END
    for node_name in _CLIENT_STEP_TO_NODE.values():
        sg.add_edge(node_name, "schedule_effects")
    sg.add_edge("schedule_effects", END)

    checkpointer, conn = _make_checkpointer(db_uri)
    graph = sg.compile(checkpointer=checkpointer)
    return graph, conn


# ----------------------------
# Provider graph
# Starts with: (known provider) + message type → expected gate → step routing
# ----------------------------

def build_provider_graph(db_uri: str):
    sg = StateGraph(AppState)

    # common nodes
    sg.add_node("schedule_effects", schedule_effects)

    # routers (as explicit nodes for nicer diagram)
    sg.add_node("route_provider_type", lambda s: {})
    sg.add_node("route_provider_step", lambda s: {})

    # entries
    sg.add_node("provider_text_entry", provider_text_entry)
    sg.add_node("provider_audio_entry", provider_audio_entry)
    sg.add_node("provider_btn_entry", provider_btn_entry)
    sg.add_node("provider_list_entry", provider_list_entry)

    # handlers
    for name, fn in [
        ("provider_start", provider_start),
        ("provider_create_slots", provider_create_slots),
        ("provider_review_slots", provider_review_slots),
        ("provider_publish_slots", provider_publish_slots),
        ("provider_done", provider_done),
    ]:
        sg.add_node(name, fn)

    # START → type
    sg.add_edge(START, "route_provider_type")

    # type fanout (provider)
    sg.add_conditional_edges(
        "route_provider_type",
        route_input_type,
        {
            "text": "provider_text_entry",
            "audio": "provider_audio_entry",
            "btn": "provider_btn_entry",
            "list": "provider_list_entry",
        },
    )

    # expected gate AFTER type
    for entry in ["provider_text_entry", "provider_audio_entry", "provider_btn_entry", "provider_list_entry"]:
        sg.add_conditional_edges(
            entry,
            route_expected,
            {"ok": "route_provider_step", "reprompt": "schedule_effects"},
        )

    # step routing
    sg.add_conditional_edges(
        "route_provider_step",
        route_provider_step,
        {name: name for name in _PROVIDER_STEP_TO_NODE.values()},
    )

    # handlers → effects → END
    for node_name in _PROVIDER_STEP_TO_NODE.values():
        sg.add_edge(node_name, "schedule_effects")
    sg.add_edge("schedule_effects", END)

    checkpointer, conn = _make_checkpointer(db_uri)
    graph = sg.compile(checkpointer=checkpointer)
    return graph, conn


def build_graph(db_uri: str):
    client_graph, client_conn = build_client_graph(db_uri)
    provider_graph, provider_conn = build_provider_graph(db_uri)
    return client_graph, provider_graph, client_conn, provider_conn

if __name__ == "__main__":
    from dotenv import load_dotenv
    import os
    load_dotenv(".venv/.env")
    DATABASE_URL='postgresql://tami_postgre_user:zcHW1V9DwfeXkbx7NCv5NdWQa1K9ygLO@dpg-d5sbatbuibrs739oofk0-a.frankfurt-postgres.render.com/tami_postgre_db_ynu7'
    client_graph, provider_graph, client_conn, provider_conn = build_graph(DATABASE_URL)
    png_bytes_client = client_graph.get_graph().draw_mermaid_png()
    png_bytes_provider = provider_graph.get_graph().draw_mermaid_png()

    with open("client_graph.png", "wb") as f:
        f.write(png_bytes_client)

    with open("provider_graph.png", "wb") as f:
        f.write(png_bytes_provider)

    print("Graph written to client_graph.png and provider_graph.png")

    display(Image(client_graph.get_graph().draw_mermaid_png()))
    display(Image(provider_graph.get_graph().draw_mermaid_png()))
