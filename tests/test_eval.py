import pytest
from unittest.mock import MagicMock
import os
from deepeval.models import GPTModel

deepeval_judge = GPTModel(model=os.getenv("OPENAI_MODEL", "gpt-5.2"))

# Helper to run personalizer
def run_personalizer(lead_name: str, company: str, role: str, company_description: str, personalized_hook: str, session_id: str) -> str:
    """Run the Personalizer agent and return its final outreach email text."""
    from graph.state import LeadCampaign, Lead, initial_state
    from agents.personalizer import personalizer_node
    from langchain_core.messages import AIMessage

    state = initial_state(f"Find B2B Tech Leads", session_id)
    lead = Lead(
        name=lead_name,
        company=company,
        role=role,
        email="test@company.com",
        company_description=company_description,
        personalized_hook=personalized_hook,
        status="pending"
    )
    state["campaign"] = LeadCampaign(
        goal="Find B2B Tech Leads",
        total_leads_target=1,
        leads=[lead],
    )
    state["current_lead_index"] = 0

    result = personalizer_node(state)

    # Extract the final response: last AIMessage with no tool_calls
    for msg in reversed(result.get("messages", [])):
        if (isinstance(msg, AIMessage) and msg.content
                and not getattr(msg, "tool_calls", None)):
            return msg.content
    return ""


@pytest.mark.eval
class TestPersonalizerQuality:
    FAITHFULNESS_THRESHOLD = 0.6
    RELEVANCY_THRESHOLD = 0.6

    @pytest.fixture(autouse=True)
    def setup(self, case_study_note_content):
        """Run the Personalizer once, reuse the output across all tests in this class."""
        import uuid
        self.retrieval_context = [case_study_note_content]
        self.explanation = run_personalizer(
            lead_name="Alice Vance",
            company="Vance Solutions",
            role="CEO",
            company_description="Outsourced customer success provider struggling with SDR research efficiency.",
            personalized_hook="Help Acme scale outsourcing by reducing lead prep time.",
            session_id=f"eval-test-{uuid.uuid4().hex[:8]}",
        )
        if not self.explanation:
            pytest.skip("Personalizer returned empty output.")

    def test_personalizer_outreach_is_faithful_to_case_studies(self):
        """Verify the outreach does not hallucinate B2B metrics or case studies."""
        from deepeval.test_case import LLMTestCase
        from deepeval.metrics import FaithfulnessMetric

        test_case = LLMTestCase(
            input="Write a personalized B2B outreach email for Alice Vance at Vance Solutions.",
            actual_output=self.explanation,
            retrieval_context=self.retrieval_context,
        )
        metric = FaithfulnessMetric(
            threshold=self.FAITHFULNESS_THRESHOLD,
            model=deepeval_judge,
            include_reason=True,
        )
        metric.measure(test_case)

        print(f"\n[Faithfulness] Score: {metric.score:.3f}")
        if hasattr(metric, "reason"):
            print(f"[Faithfulness] Reason: {metric.reason}")

        assert metric.score >= self.FAITHFULNESS_THRESHOLD, (
            f"Faithfulness {metric.score:.3f} below threshold.\n"
            f"Reason: {getattr(metric, 'reason', 'N/A')}"
        )

    def test_personalizer_outreach_is_relevant_to_prospect(self):
        """Verify the outreach email is relevant to the B2B target lead."""
        from deepeval.test_case import LLMTestCase
        from deepeval.metrics import AnswerRelevancyMetric

        test_case = LLMTestCase(
            input="Write a personalized B2B outreach email for Alice Vance at Vance Solutions.",
            actual_output=self.explanation,
        )
        metric = AnswerRelevancyMetric(
            threshold=self.RELEVANCY_THRESHOLD,
            model=deepeval_judge,
            include_reason=True,
        )
        metric.measure(test_case)

        print(f"\n[Relevancy] Score: {metric.score:.3f}")
        if hasattr(metric, "reason"):
            print(f"[Relevancy] Reason: {metric.reason}")

        assert metric.score >= self.RELEVANCY_THRESHOLD, (
            f"Relevancy {metric.score:.3f} below threshold.\n"
            f"Reason: {getattr(metric, 'reason', 'N/A')}"
        )


@pytest.mark.eval
class TestGradingQuality:
    def test_correct_response_scores_high(self):
        """Test that a high-quality B2B response to an objection scores >= 0.65."""
        from agents.objection_simulator import grade_response

        result = grade_response(
            question="We already have an in-house outsourcing team and are happy with them.",
            expected="Validate their current team, then show how Lead Accelerator helps by reducing the prep time per lead from 25 min to 15 seconds to empower their in-house team.",
            sdr_response="That's great! Having an in-house team is a huge asset. Our tool actually doesn't replace them; it acts as a force multiplier by cutting down their lead prep research time from 25 minutes to just 15 seconds so they can book 4x more calls.",
        )
        score = float(result.get("score", 0.0))
        print(f"\n[GradingQuality] Correct response score: {score:.2f}")
        assert score >= 0.65, (
            f"Correct response scored too low: {score:.2f}\n"
            f"Feedback: {result.get('feedback', '')}"
        )

    def test_wrong_response_scores_low(self):
        """Test that a defiant/defensive or wrong objection-handling response scores <= 0.35."""
        from agents.objection_simulator import grade_response

        result = grade_response(
            question="We don't have budget for new sales software.",
            expected="Acknowledge budget limits, but highlight Acme's 4x booking rate increase (2.1% to 8.4%) to frame it as self-funding ROI.",
            sdr_response="Then you are missing out on serious revenue. Our software is cheap, you should just buy it if you care about growing your company.",
        )
        score = float(result.get("score", 0.0))
        print(f"\n[GradingQuality] Wrong response score: {score:.2f}")
        assert score <= 0.35, (
            f"Wrong response scored too high: {score:.2f}\n"
            f"Feedback: {result.get('feedback', '')}"
        )

    def test_partial_response_scores_middle(self):
        """Test that a partial response scores in the middle range (0.3 to 0.75)."""
        from agents.objection_simulator import grade_response

        result = grade_response(
            question="We already have a tool that searches LinkedIn.",
            expected="Acknowledge LinkedIn tools, but specify how our agentic workflow synthesizes custom copy grounded in real-time case studies to book 4x more meetings.",
            sdr_response="We do more than just search LinkedIn, we also draft the copy.",
        )
        score = float(result.get("score", 0.0))
        print(f"\n[GradingQuality] Partial response score: {score:.2f}")
        assert 0.3 <= score <= 0.75, (
            f"Partial response should score between 0.3 and 0.75, got {score:.2f}"
        )


@pytest.mark.eval
class TestProgressCoachQuality:
    COACHING_QUALITY_THRESHOLD = 0.6

    def test_coaching_message_is_encouraging_and_specific(self):
        """Evaluate if the coaching feedback is concise, specific, warm, and actionable."""
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams
        from deepeval.metrics import GEval
        from agents.crm_coach import get_coaching_message

        coaching = get_coaching_message(
            lead_name="Alice Vance",
            company="Vance Solutions",
            score=0.67,
            weak_areas=["competitor objection", "value proposition connection"],
        )
        coaching_text = (
            f"Summary: {coaching.get('summary', '')}\n"
            f"Encouragement: {coaching.get('encouragement', '')}"
        )

        test_case = LLMTestCase(
            input=(
                "Generate coaching feedback for an SDR who scored 67% on B2B objection handling "
                "for Alice Vance at Vance Solutions, struggling with competitor objections."
            ),
            actual_output=coaching_text,
        )
        metric = GEval(
            name="CRMCoachingQuality",
            criteria=(
                "Evaluate whether this B2B sales coaching message is: "
                "1) Concise and professional (2-3 sentences max total). "
                "2) Warm and encouraging without being dishonest about the 67% score. "
                "3) Specific to Vance Solutions and the SDR's weak areas (competitors). "
                "4) Actionable. Gives a clear and practical next step."
            ),
            evaluation_params=[LLMTestCaseParams.ACTUAL_OUTPUT],
            model=deepeval_judge,
            threshold=self.COACHING_QUALITY_THRESHOLD,
        )
        metric.measure(test_case)

        print(f"\n[CoachingQuality] Score: {metric.score:.3f}")
        if hasattr(metric, "reason"):
            print(f"[CoachingQuality] Reason: {metric.reason}")

        assert metric.score >= self.COACHING_QUALITY_THRESHOLD, (
            f"Coaching quality {metric.score:.3f} below threshold.\n"
            f"Reason: {getattr(metric, 'reason', 'N/A')}"
        )
