from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


@dataclass
class Lead:
    """A single lead identified for the outreach campaign."""
    name: str
    company: str
    role: str
    email: str
    company_description: str
    personalized_hook: str = ""
    # pending → in_progress → approved | needs_review
    status: str = "pending"
    email_verified: bool = False
    procurement_vetted: bool = False
    verification_reason: str = "Unverified"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Lead":
        return cls(
            name=data["name"],
            company=data["company"],
            role=data["role"],
            email=data["email"],
            company_description=data["company_description"],
            personalized_hook=data.get("personalized_hook", ""),
            status=data.get("status", "pending"),
            email_verified=bool(data.get("email_verified", False)),
            procurement_vetted=bool(data.get("procurement_vetted", False)),
            verification_reason=data.get("verification_reason", "Unverified"),
        )


@dataclass
class LeadCampaign:
    """The full outreach campaign plan produced by the Lead Researcher."""
    goal: str
    total_leads_target: int
    leads: list[Lead]
    outreach_channel: str = "email"

    def is_complete(self) -> bool:
        return all(l.status in ("completed", "needs_review", "approved") for l in self.leads)

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "total_leads_target": self.total_leads_target,
            "leads": [l.to_dict() if hasattr(l, "to_dict") else l for l in self.leads],
            "outreach_channel": self.outreach_channel,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LeadCampaign":
        raw_leads = data.get("leads", [])
        leads = []
        for l in raw_leads:
            if isinstance(l, dict):
                leads.append(Lead.from_dict(l))
            else:
                leads.append(l)
        return cls(
            goal=data["goal"],
            total_leads_target=int(data["total_leads_target"]),
            leads=leads,
            outreach_channel=data.get("outreach_channel", "email"),
        )


@dataclass
class SimulationQuestion:
    """An individual objection scenario question in the simulation."""
    question: str
    expected_answer: str
    user_answer: str
    correct: bool
    feedback: str
    score: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationQuestion":
        return cls(
            question=data["question"],
            expected_answer=data["expected_answer"],
            user_answer=data.get("user_answer", ""),
            correct=bool(data.get("correct", False)),
            feedback=data.get("feedback", ""),
            score=float(data.get("score", 0.0)),
        )


@dataclass
class SimulationResult:
    """The complete result of a pitch simulation/objection handling session for a lead."""
    lead_name: str
    questions: list[SimulationQuestion]
    score: float       # 0.0 to 1.0 (strength of pitch/response)
    weak_areas: list[str]
    timestamp: str = ""

    def passed(self) -> bool:
        return self.score >= 0.5

    def to_dict(self) -> dict:
        return {
            "lead_name": self.lead_name,
            "questions": [q.to_dict() if hasattr(q, "to_dict") else q for q in self.questions],
            "score": self.score,
            "weak_areas": self.weak_areas,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SimulationResult":
        raw_questions = data.get("questions", [])
        questions = []
        for q in raw_questions:
            if isinstance(q, dict):
                questions.append(SimulationQuestion.from_dict(q))
            else:
                questions.append(q)
        return cls(
            lead_name=data["lead_name"],
            questions=questions,
            score=float(data["score"]),
            weak_areas=data.get("weak_areas", []),
            timestamp=data.get("timestamp", ""),
        )



class AgentState(TypedDict):
    """
    The shared state for the Lead Accelerator graph.

    Partial updates: when a node returns {"approved": True}, LangGraph
    merges that into the existing state. It does NOT replace the whole dict.
    Nodes only return the keys they changed.

    The one exception is `messages`: it uses the add_messages reducer,
    which appends to the list instead of replacing it.
    """
    messages: Annotated[list[BaseMessage], add_messages]
    session_id: str
    goal: str
    total_leads_target: int
    campaign: LeadCampaign | None
    approved: bool
    current_lead_index: int
    simulation_results: list[SimulationResult]
    weak_areas: list[str]
    lead_materials_path: str
    error: str | None


def initial_state(
    goal: str,
    session_id: str,
    lead_materials_path: str = "lead_materials/sample_profiles",
    total_leads_target: int = 3,
) -> dict:
    """Create the initial state for a new lead campaign session."""
    return {
        "messages": [],
        "session_id": session_id,
        "goal": goal,
        "total_leads_target": total_leads_target,
        "campaign": None,
        "approved": False,
        "current_lead_index": 0,
        "simulation_results": [],
        "weak_areas": [],
        "lead_materials_path": lead_materials_path,
        "error": None,
    }


def get_current_lead(state: dict) -> Lead | None:
    """Get the lead currently being analyzed, or None if done."""
    campaign = state.get("campaign")
    if campaign is None:
        return None
    if isinstance(campaign, dict):
        campaign = LeadCampaign.from_dict(campaign)
    idx = state.get("current_lead_index", 0)
    if idx >= len(campaign.leads):
        return None
    lead = campaign.leads[idx]
    if isinstance(lead, dict):
        return Lead.from_dict(lead)
    return lead


def session_is_complete(state: dict) -> bool:
    """True when all leads in the campaign have been processed."""
    campaign = state.get("campaign")
    if campaign is None:
        return True
    if isinstance(campaign, dict):
        campaign = LeadCampaign.from_dict(campaign)
    idx = state.get("current_lead_index", 0)
    return idx >= len(campaign.leads)


def get_latest_simulation_result(state: dict) -> SimulationResult | None:
    """Get the most recent pitch simulation result from the state."""
    results = state.get("simulation_results", [])
    if not results:
        return None
    res = results[-1]
    if isinstance(res, dict):
        return SimulationResult.from_dict(res)
    return res

