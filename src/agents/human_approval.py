from langgraph.types import interrupt


def human_approval_node(state: dict) -> dict:
    """
    LangGraph node: Human Approval

    Pauses the graph to allow the user to review the compiled B2B prospecting campaign.
    
    Reads:  state["campaign"]
    Writes: state["approved"] and all other state keys explicitly to survive state propagation issues.
    """
    campaign = state.get("campaign")
    
    print("\n[Human Approval] Pausing for campaign review...")
    
    # interrupt() pauses execution here.
    decision = interrupt({
        "type": "campaign_approval",
        "campaign": campaign,
        "prompt": (
            "Does this campaign plan look good?\n"
            "  Type 'yes' to start SDR sessions\n"
            "  Type 'no' to generate a different plan"
        )
    })
    
    approved = str(decision).lower().strip() in ("yes", "y", "ok", "approve")
    
    if approved:
        print("[Human Approval] Campaign approved! Starting prospecting sessions.")
    else:
        print("[Human Approval] Campaign rejected or needs refinement.")
        
    return {
        "approved": approved,
        "campaign": campaign,
        "goal": state.get("goal", ""),
        "session_id": state.get("session_id", ""),
        "current_lead_index": state.get("current_lead_index", 0),
        "simulation_results": state.get("simulation_results", []),
        "weak_areas": state.get("weak_areas", []),
        "lead_materials_path": state.get("lead_materials_path", "lead_materials/sample_profiles"),
        "error": None,
        "messages": state.get("messages", []),
    }
