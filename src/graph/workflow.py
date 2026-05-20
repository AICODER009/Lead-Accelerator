import os
import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from agents.lead_researcher import lead_researcher_node
from agents.personalizer import personalizer_node
from agents.human_approval import human_approval_node
from agents.crm_coach import crm_coach_node
from agents.objection_simulator import objection_simulator_node
from graph.state import AgentState, session_is_complete


def route_after_approval(state: dict) -> str:
    if state.get("approved", False):
        return "personalizer"
    return "lead_researcher"


def route_after_coach(state: dict) -> str:
    if session_is_complete(state):
        return "end"
    return "personalizer"


def build_graph(
    db_path: str = "data/checkpoints.db",
    interrupt_before: list | None = None,
):
    Path("data").mkdir(exist_ok=True)
    if db_path == "data/checkpoints.db":
        db_path = os.getenv("CHECKPOINT_DB", db_path)

    builder = StateGraph(AgentState)

    # Register all five nodes
    builder.add_node("lead_researcher", lead_researcher_node)
    builder.add_node("human_approval", human_approval_node)
    builder.add_node("personalizer", personalizer_node)
    builder.add_node("objection_simulator", objection_simulator_node)
    builder.add_node("crm_coach", crm_coach_node)

    # Static edges
    builder.add_edge(START, "lead_researcher")
    builder.add_edge("lead_researcher", "human_approval")
    builder.add_edge("personalizer", "objection_simulator")
    builder.add_edge("objection_simulator", "crm_coach")

    # Conditional edges
    builder.add_conditional_edges(
        "human_approval",
        route_after_approval,
        {"personalizer": "personalizer", "lead_researcher": "lead_researcher"},
    )
    builder.add_conditional_edges(
        "crm_coach",
        route_after_coach,
        {"personalizer": "personalizer", "end": END},
    )

    # Checkpoint SqliteSaver setup
    conn = sqlite3.connect(db_path, check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=interrupt_before or [],
    )


graph = build_graph()
