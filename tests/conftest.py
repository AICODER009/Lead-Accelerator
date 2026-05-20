import os
import sys
from pathlib import Path
import pytest

# Ensure the src directory is in the path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def pytest_configure(config):
    """Register custom markers so pytest doesn't warn about unknown marks."""
    config.addinivalue_line(
        "markers",
        "eval: marks slow evaluation tests requiring LLM-as-judge (deselect with -m 'not eval')"
    )
    config.addinivalue_line(
        "markers",
        "unit: marks fast unit tests with no external API dependencies"
    )


@pytest.fixture
def sample_campaign():
    """A minimal LeadCampaign for use in B2B unit and eval tests."""
    from graph.state import LeadCampaign, Lead
    return LeadCampaign(
        goal="Prospect SaaS founders needing outbound agentic AI",
        total_leads_target=2,
        leads=[
            Lead(
                name="Alice Vance",
                company="Vance Solutions",
                role="CEO",
                email="alice@vance.io",
                company_description="Outsourced customer success provider.",
                personalized_hook="Automate outbound prep for Vance client outreach.",
                status="pending"
            ),
            Lead(
                name="Bob Miller",
                company="Miller Cloud",
                role="Founder",
                email="bob@miller.cloud",
                company_description="Managed AWS infrastructure provider.",
                personalized_hook="Overcome cloud cost concerns with objection simulation.",
                status="pending"
            ),
        ]
    )


@pytest.fixture
def sample_state(sample_campaign):
    """A minimal AgentState dict for B2B unit tests."""
    from graph.state import initial_state
    state = initial_state("Prospect SaaS founders needing outbound agentic AI", "test-eval-sess-99")
    state["campaign"] = sample_campaign
    state["current_lead_index"] = 0
    return state


@pytest.fixture
def case_study_note_content():
    """The B2B copywriter case studies content used as retrieval context in faithfulness tests."""
    case_study_path = (
        Path(__file__).parent.parent
        / "lead_materials/sample_profiles/case_studies.md"
    )
    if case_study_path.exists():
        return case_study_path.read_text(encoding="utf-8")
    return (
        "# Success Case Studies\n\n"
        "Acme Outsourcing Group reduced preparing prep time per lead from 25 minutes to 15 seconds "
        "and increased cold booking rates from 2.1% to 8.4%."
    )
