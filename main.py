import argparse
import sys
import uuid
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

from graph.workflow import graph
from graph.state import initial_state, LeadCampaign
from langgraph.types import Command


def format_banner(title: str, session_id: str, goal: str):
    width = 60
    border = "=" * width
    print("\033[95m" + border)
    print(f" {title}".center(width))
    print(f" Session ID: {session_id}".center(width))
    print(f" Target Goal: {goal[:45]}...".center(width) if len(goal) > 45 else f" Target Goal: {goal}".center(width))
    print(border + "\033[0m")


def print_campaign(campaign):
    if not campaign:
        return
    if isinstance(campaign, dict):
        campaign = LeadCampaign.from_dict(campaign)
    print("\n\033[92m" + "Proposed Outreach Campaign Plan" + "\033[0m")
    print("=" * 60)
    print(f"\033[93mGoal:\033[0m {campaign.goal}")
    print(f"\033[93mTarget Leads Count:\033[0m {campaign.total_leads_target}")
    print(f"\033[93mOutreach Channel:\033[0m {campaign.outreach_channel}")
    print("-" * 60)
    
    for i, lead in enumerate(campaign.leads, 1):
        status_color = "\033[92m" if lead.status == "approved" else "\033[93m" if lead.status == "needs_review" else "\033[90m"
        print(f"\n  {i}. \033[1m{lead.name}\033[0m - {lead.role} at \033[94m{lead.company}\033[0m")
        print(f"     \033[90mEmail:\033[0m {lead.email}")
        print(f"     \033[90mCompany Bio:\033[0m {lead.company_description}")
        print(f"     \033[90mStatus:\033[0m {status_color}{lead.status}\033[0m")
        if lead.personalized_hook:
            print(f"     \033[36mPersonalization Hook:\033[0m {lead.personalized_hook}")
    print("=" * 60)


def execute_workflow(inputs: dict | None, config: dict):
    """Execute the LangGraph workflow, handling human-in-the-loop interrupts in the CLI."""
    result = graph.invoke(inputs, config)
    
    while True:
        state = graph.get_state(config)
        if state.next and state.next[0] == "human_approval":
            campaign = state.values.get("campaign")
            if campaign:
                print_campaign(campaign)
            
            # Interactive prompt for approval
            user_input = input("\n[Human Approval] Approve the proposed campaign plan? (yes/no): ").strip()
            
            # Resume the graph execution
            result = graph.invoke(Command(resume=user_input), config)
        else:
            break
            
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Lead Accelerator: Autonomous B2B Lead Generation & Nurturing Pipeline"
    )
    parser.add_argument(
        "goal",
        nargs="?",
        type=str,
        help="Target B2B lead generation criteria / ICP (e.g. 'SaaS founders in NY')"
    )
    parser.add_argument(
        "--resume",
        type=str,
        help="Session ID to resume execution from SQLite checkpoint"
    )
    parser.add_argument(
        "--db",
        type=str,
        default="data/checkpoints.db",
        help="Path to SQLite checkpoint database"
    )

    args = parser.parse_args()

    if not args.goal and not args.resume:
        parser.print_help()
        sys.exit(0)

    session_id = args.resume or str(uuid.uuid4())[:8]
    config = {"configurable": {"thread_id": session_id}}

    if args.resume:
        state = graph.get_state(config)
        if not state or not state.values:
            print(f"\033[91mError: No checkpoint found for Session ID: {session_id}\033[0m")
            sys.exit(1)
        
        goal = state.values.get("goal", "Resumed Session")
        format_banner("Lead Accelerator (Resuming)", session_id, goal)
        
        print(f"\n[System] Resuming from checkpoint...")
        result = execute_workflow(None, config)
    else:
        format_banner("Lead Accelerator", session_id, args.goal)
        
        # Initialize campaign state
        inputs = initial_state(goal=args.goal, session_id=session_id)
        result = execute_workflow(inputs, config)

    # Output final campaign state details
    campaign = result.get("campaign")
    if campaign:
        print_campaign(campaign)
    
    if result.get("error"):
        print(f"\n\033[91m[Error] Session halted due to error:\033[0m {result['error']}")
    else:
        print(f"\n\033[92m[Success] Session {session_id} completed successfully!\033[0m")


if __name__ == "__main__":
    main()
