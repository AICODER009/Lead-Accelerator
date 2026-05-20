import json
import pytest
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage
from graph.state import Lead, LeadCampaign, SimulationResult
from agents.objection_simulator import objection_simulator_node
from agents.crm_coach import crm_coach_node


@pytest.fixture
def sample_state():
    """Create a sample AgentState for testing node progressions."""
    lead1 = Lead(
        name="John Doe",
        company="Acme Corp",
        role="CEO",
        email="john@acme.com",
        company_description="B2B engineering services.",
        personalized_hook="Help Acme scale outsourcing.",
        status="pending"
    )
    lead2 = Lead(
        name="Jane Smith",
        company="Beta Inc",
        role="Founder",
        email="jane@beta.com",
        company_description="AI marketing tools.",
        personalized_hook="Boost Beta's marketing automation.",
        status="pending"
    )
    campaign = LeadCampaign(
        goal="Find B2B Tech Leads",
        total_leads_target=2,
        leads=[lead1, lead2],
        outreach_channel="email"
    )
    return {
        "messages": [
            AIMessage(content="Subject: Scale Acme outsourcing\n\nHi John, I noticed Acme spending hours on SDR prep...")
        ],
        "session_id": "test_session_999",
        "goal": "Find B2B Tech Leads",
        "campaign": campaign,
        "approved": True,
        "current_lead_index": 0,
        "simulation_results": [],
        "weak_areas": ["initial objection"],
        "lead_materials_path": "lead_materials/sample_profiles",
        "error": None
    }


@patch("agents.objection_simulator.run_simulation")
def test_objection_simulator_node(mock_run, sample_state):
    """Test that the objection simulator node extracts the explanation and runs the simulator."""
    mock_result = SimulationResult(
        lead_name="John Doe",
        questions=[],
        score=0.8,
        weak_areas=["budget objection"],
        timestamp="2026-05-20T00:00:00"
    )
    mock_run.return_value = mock_result

    # Run node
    output = objection_simulator_node(sample_state)

    # Assertions
    assert output["error"] is None
    assert len(output["simulation_results"]) == 1
    assert output["simulation_results"][0].score == 0.8
    assert "budget objection" in output["weak_areas"]
    assert "initial objection" in output["weak_areas"]
    mock_run.assert_called_once()
    assert mock_run.call_args[0][0] == "John Doe"
    assert "Subject: Scale Acme outsourcing" in mock_run.call_args[0][2]


@patch("agents.crm_coach.get_coaching_message")
@patch("agents.crm_coach.memory_set")
def test_crm_coach_node_passed(mock_memory, mock_coaching, sample_state):
    """Test CRM Coach updates lead status to 'approved' when simulator score >= 0.5."""
    mock_coaching.return_value = {
        "summary": "Great objection handling, John was convinced.",
        "encouragement": "Onwards to Jane Smith!"
    }
    mock_memory.return_value = "Stored"

    # Setup state with a passing simulation result
    sim_result = SimulationResult(
        lead_name="John Doe",
        questions=[],
        score=0.85,
        weak_areas=[]
    )
    sample_state["simulation_results"] = [sim_result]

    # Run node
    output = crm_coach_node(sample_state)

    # Assertions
    assert output["error"] is None
    assert output["current_lead_index"] == 1
    assert output["campaign"].leads[0].status == "approved"
    assert len(output["messages"]) == 1
    assert "John was convinced" in output["messages"][0].content
    mock_memory.assert_called_once()
    assert "progress_lead_0" in mock_memory.call_args[0][1]


@patch("agents.crm_coach.get_coaching_message")
@patch("agents.crm_coach.memory_set")
def test_crm_coach_node_failed(mock_memory, mock_coaching, sample_state):
    """Test CRM Coach updates lead status to 'needs_review' when simulator score < 0.5."""
    mock_coaching.return_value = {
        "summary": "Struggled with competitor objections.",
        "encouragement": "Let's review before reaching out."
    }
    mock_memory.return_value = "Stored"

    # Setup state with a failing simulation result
    sim_result = SimulationResult(
        lead_name="John Doe",
        questions=[],
        score=0.30,
        weak_areas=["competitor objection"]
    )
    sample_state["simulation_results"] = [sim_result]

    # Run node
    output = crm_coach_node(sample_state)

    # Assertions
    assert output["error"] is None
    assert output["current_lead_index"] == 1
    assert output["campaign"].leads[0].status == "needs_review"
    assert "Struggled with competitor objections" in output["messages"][0].content
