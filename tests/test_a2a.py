import os
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient

from a2a.types import Message
from a2a.client import create_text_message_object
from utils.a2a_client import call_a2a_agent, call_a2a_agent_async
from agents.objection_simulator import generate_objections, grade_response
from agents.personalizer import tool_ask_study_buddy
from a2a_services.objection_service import create_app as create_quiz_app
from a2a_services.sales_research_partner import create_app as create_buddy_app


class MockA2AClient:
    def __init__(self, response_text):
        self.response_text = response_text
        self.is_closed = False

    async def send_message(self, msg):
        yield create_text_message_object(role="agent", content=self.response_text)

    async def close(self):
        self.is_closed = True


@pytest.mark.asyncio
@patch("a2a.client.client_factory.ClientFactory.connect")
async def test_a2a_client_async_aggregation(mock_connect):
    """Test that call_a2a_agent_async correctly streams and aggregates responses."""
    mock_connect.return_value = MockA2AClient("Hello from A2A Service!")

    res = await call_a2a_agent_async("http://dummy-url", "ping")
    assert res == "Hello from A2A Service!"
    mock_connect.assert_called_once_with("http://dummy-url")


@patch("utils.a2a_client.call_a2a_agent")
def test_objection_simulator_delegation_true(mock_call):
    """Test that objection simulator delegates to A2A when USE_A2A_QUIZ is true."""
    mock_call.return_value = json.dumps({
        "questions": [
            {
                "question": "A2A objection?",
                "expected_answer": "A2A expected",
                "difficulty": "hard"
            }
        ]
    })

    with patch.dict(os.environ, {"USE_A2A_QUIZ": "true", "QUIZ_SERVICE_URL": "http://localhost:9001", "IS_QUIZ_SERVICE": "false"}):
        questions = generate_objections("Alice", "Tech Corp", "Draft email text", n=1)
        assert len(questions) == 1
        assert questions[0]["question"] == "A2A objection?"
        mock_call.assert_called_once()
        assert "Alice" in mock_call.call_args[0][1]


@patch("agents.objection_simulator.generate_objections_local")
def test_objection_simulator_delegation_false(mock_local):
    """Test that objection simulator bypasses A2A when USE_A2A_QUIZ is false."""
    mock_local.return_value = [{"question": "Local objection"}]

    with patch.dict(os.environ, {"USE_A2A_QUIZ": "false"}):
        questions = generate_objections("Alice", "Tech Corp", "Draft email text", n=1)
        assert len(questions) == 1
        assert questions[0]["question"] == "Local objection"
        mock_local.assert_called_once()


@patch("utils.a2a_client.call_a2a_agent")
def test_objection_simulator_grading_delegation_true(mock_call):
    """Test that grading delegates to A2A when USE_A2A_QUIZ is true."""
    mock_call.return_value = json.dumps({
        "correct": True,
        "score": 0.9,
        "feedback": "Perfect handling!",
        "missing_concept": ""
    })

    with patch.dict(os.environ, {"USE_A2A_QUIZ": "true", "QUIZ_SERVICE_URL": "http://localhost:9001", "IS_QUIZ_SERVICE": "false"}):
        res = grade_response("How to handle X?", "Try Y.", "I would try Y.")
        assert res["correct"] is True
        assert res["score"] == 0.9
        mock_call.assert_called_once()


@patch("utils.a2a_client.call_a2a_agent")
def test_personalizer_study_buddy_delegation(mock_call):
    """Test that tool_ask_study_buddy delegates to A2A when USE_STUDY_BUDDY is true."""
    mock_call.return_value = "Detailed competitor research report from CrewAI."

    with patch.dict(os.environ, {"USE_STUDY_BUDDY": "true", "STUDY_BUDDY_URL": "http://localhost:9002"}):
        report = tool_ask_study_buddy.invoke("Find competitors for AI CRM")
        assert "Detailed competitor research" in report
        mock_call.assert_called_once_with("http://localhost:9002", "Find competitors for AI CRM")


@patch("mcp_servers.filesystem_server.search_notes")
def test_personalizer_study_buddy_fallback(mock_search):
    """Test that tool_ask_study_buddy falls back to local file search when USE_STUDY_BUDDY is false."""
    mock_search.return_value = [{"file": "competitors.md", "line": 5, "content": "Competitor Acme"}]

    with patch.dict(os.environ, {"USE_STUDY_BUDDY": "false"}):
        report = tool_ask_study_buddy.invoke("Acme competitors")
        assert "Sales Research Partner is offline" in report
        assert "Competitor Acme" in report
        mock_search.assert_called_once_with("Acme competitors")


def test_quiz_service_fastapi_app():
    """Verify that Objection Service FastAPI application creates and exposes routes properly."""
    app = create_quiz_app()
    client = TestClient(app)
    # Check that metadata endpoint or a typical endpoint returns status or is registered
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "B2B Sales Objection Simulator Service"


def test_study_buddy_service_fastapi_app():
    """Verify that CrewAI Sales Research Partner Service FastAPI application creates and exposes routes properly."""
    app = create_buddy_app()
    client = TestClient(app)
    response = client.get("/.well-known/agent-card.json")
    assert response.status_code == 200
    card = response.json()
    assert card["name"] == "CrewAI Sales Research Partner"
