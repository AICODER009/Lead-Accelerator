import os
import sys
import uuid
import sqlite3
from dotenv import load_dotenv

# Force UTF-8 encoding for stdout/stderr to prevent UnicodeEncodeErrors on Windows
os.environ["PYTHONIOENCODING"] = "utf-8"

# Load environment variables from .env
load_dotenv()

import streamlit as st

# Set Streamlit run flag before any agent/graph imports
os.environ["STREAMLIT_RUN"] = "true"

# Add path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))

from graph.workflow import graph
from graph.state import initial_state, LeadCampaign, SimulationResult
from langgraph.types import Command

# Page config with premium branding and styling
st.set_page_config(
    page_title="Lead Accelerator Studio",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for rich aesthetics: glassmorphism, harmony colors, Outfit font
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&family=Plus+Jakarta+Sans:wght@300;400;500;700&display=swap" rel="stylesheet">
<style>
    body {
        font-family: 'Plus Jakarta Sans', sans-serif;
    }
    h1, h2, h3, .title-text {
        font-family: 'Outfit', sans-serif;
        font-weight: 800;
        background: linear-gradient(135deg, #FF007F, #8A2BE2, #00D2FF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .main-header {
        font-size: 3rem !important;
        margin-bottom: 0.5rem !important;
    }
    .sub-header {
        font-size: 1.2rem !important;
        color: #8E8EA0;
        margin-bottom: 2rem !important;
    }
    /* Premium card containers */
    .premium-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        -webkit-backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 24px;
        margin-bottom: 20px;
        transition: transform 0.3s ease, border-color 0.3s ease;
    }
    .premium-card:hover {
        border-color: rgba(138, 43, 226, 0.4);
        transform: translateY(-2px);
    }
    .success-badge {
        background-color: rgba(46, 204, 113, 0.15);
        color: #2ecc71;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: bold;
        border: 1px solid rgba(46, 204, 113, 0.3);
    }
    .review-badge {
        background-color: rgba(241, 196, 15, 0.15);
        color: #f1c40f;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: bold;
        border: 1px solid rgba(241, 196, 15, 0.3);
    }
    .pending-badge {
        background-color: rgba(142, 142, 160, 0.15);
        color: #8E8EA0;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 0.85rem;
        font-weight: bold;
        border: 1px solid rgba(142, 142, 160, 0.3);
    }
</style>
""", unsafe_allow_html=True)


# Sidebar Brand & Session Manager
st.sidebar.markdown("<h2 class='title-text' style='font-size:1.8rem;'>⚡ Accelerator Studio</h2>", unsafe_allow_html=True)
st.sidebar.caption("Chapter 9: The Complete Production System")
st.sidebar.markdown("---")

# Discover existing sessions in the database
def get_existing_sessions():
    sessions = []
    db_path = "data/checkpoints.db"
    if os.path.exists(db_path):
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            # Select distinct thread_ids from checkpoints
            cursor.execute("SELECT DISTINCT thread_id FROM checkpoints")
            rows = cursor.fetchall()
            sessions = [r[0] for r in rows]
            conn.close()
        except Exception:
            pass
    return sessions

sessions = get_existing_sessions()
session_mode = st.sidebar.radio("Session Choice", ["Create New B2B Campaign", "Resume Past Session"], index=0)

# Initialize stable default session ID in Streamlit session state
if "default_session_id" not in st.session_state:
    st.session_state["default_session_id"] = str(uuid.uuid4())[:8]

active_session_id = None
if session_mode == "Resume Past Session" and sessions:
    active_session_id = st.sidebar.selectbox("Select Session ID", sorted(sessions, reverse=True))
    st.sidebar.success(f"Selected Session: {active_session_id}")
else:
    if session_mode == "Resume Past Session":
        st.sidebar.warning("No past sessions found in database.")
    active_session_id = st.sidebar.text_input("Custom Session ID (Optional)", st.session_state["default_session_id"])


# Main Header
st.markdown("<h1 class='main-header'>⚡ B2B Lead Accelerator Studio</h1>", unsafe_allow_html=True)
st.markdown("<p class='sub-header'>Autonomous Prospecting, Copywriting, A2A Objection Simulator & CRM Coach — Powered by gpt-5.2</p>", unsafe_allow_html=True)

# Main Campaign Dashboard tabs
tab_config, tab_monitor, tab_history = st.tabs(["🚀 Campaign Generator", "📊 Pipeline Monitor", "💾 Session Registry"])

# Session configuration or retrieval
config = {"configurable": {"thread_id": active_session_id}}

with tab_config:
    st.markdown("### 🎯 Targeting Criteria & ICP Setup")
    
    col_input, col_info = st.columns([2, 1])
    
    with col_input:
        default_goal = "SaaS Founders in NY who need outbound lead automation"
        goal_input = st.text_area("ICP Target Goal / Prospecting Criteria", default_goal, height=100)
        
        col_leads, col_mcp = st.columns(2)
        with col_leads:
            leads_count = st.slider("Target Leads Count", min_value=2, max_value=6, value=3)
        with col_mcp:
            # Displays settings for A2A
            st.markdown("<p style='font-size:0.9rem; margin-bottom:4px; font-weight:bold;'>Remote A2A Services</p>", unsafe_allow_html=True)
            use_quiz = st.toggle("Sales Objection A2A Service (Port 9001)", value=os.getenv("USE_A2A_QUIZ", "true").lower() == "true")
            use_buddy = st.toggle("CrewAI Sales Research Partner A2A Service (Port 9002)", value=os.getenv("USE_STUDY_BUDDY", "true").lower() == "true")
            
            # Persist choices in environment
            os.environ["USE_A2A_QUIZ"] = "true" if use_quiz else "false"
            os.environ["USE_STUDY_BUDDY"] = "true" if use_buddy else "false"
            
        run_btn = st.button("🚀 Initialize & Run Autonomous Campaign Pipeline", type="primary", use_container_width=True)

    with col_info:
        st.markdown("""
        <div class="premium-card">
            <h4>🔄 B2B Pipeline Architecture</h4>
            <ol style="font-size:0.85rem; padding-left:15px; color:#8E8EA0;">
                <li><b>Lead Researcher</b>: Uses LLM to compile relevant target leads.</li>
                <li><b>Human Quality Gate</b>: Interrupts the workflow for human approval.</li>
                <li><b>Personalizer SDR</b>: Calls local MCP servers to personalize the value hooks.</li>
                <li><b>Objection Simulator</b>: Triggers simulated B2B sales objection handling.</li>
                <li><b>CRM Coach</b>: Grades objections & logs progress into SQLite.</li>
            </ol>
        </div>
        """, unsafe_allow_html=True)

    if run_btn:
        with st.spinner("Initializing campaign state in LangGraph..."):
            inputs = initial_state(goal=goal_input, session_id=active_session_id)
            # Adjust campaign count directly
            inputs["campaign"] = None # Let research re-generate
            # Execute first leg of graph (runs lead_researcher and pauses on human_approval)
            result = graph.invoke(inputs, config)
            st.success(f"Pipeline initialized! Session ID: {active_session_id}. Proceed to Pipeline Monitor tab.")
            st.rerun()

with tab_monitor:
    st.markdown("### 📊 Active Pipeline Monitor")
    
    # Retrieve current state from SQL Checkpointer
    state = graph.get_state(config)
    
    if not state or not state.values:
        st.info("No active campaign campaign in this session. Create a new campaign or resume a session from the sidebar.")
    else:
        current_values = state.values
        session_id = current_values.get("session_id", "unknown")
        goal = current_values.get("goal", "unknown")
        campaign = current_values.get("campaign")
        approved = current_values.get("approved", False)
        current_lead_index = current_values.get("current_lead_index", 0)
        simulation_results = current_values.get("simulation_results", []) or []
        weak_areas = current_values.get("weak_areas", []) or []
        error = current_values.get("error")
        
        # Check if Campaign Plan exists
        if campaign:
            if isinstance(campaign, dict):
                campaign = LeadCampaign.from_dict(campaign)
            
            # Display Header Info
            col_g, col_s, col_l = st.columns([3, 1, 1])
            col_g.metric("Campaign Target ICP", goal)
            col_s.metric("Session ID", session_id)
            col_l.metric("Processed Leads", f"{current_lead_index} / {len(campaign.leads)}")
            
            # Check Human Interrupt Gate
            if state.next and state.next[0] == "human_approval":
                st.warning("⚠️ **Human Approval Interrupt Gate Triggered**: A B2B campaign plan has been compiled. Please review and approve it below.")
                
                # Render Campaign Plan Details
                st.markdown("#### 📋 Compiled Campaign Lead List")
                for i, lead in enumerate(campaign.leads, 1):
                    with st.expander(f"{i}. {lead.name} — {lead.role} at {lead.company}", expanded=True):
                        st.markdown(f"**Email**: {lead.email}")
                        st.markdown(f"**Business Description**: {lead.company_description}")
                        st.markdown(f"**Initial Personalization Angle**: {lead.personalized_hook}")
                
                # Approval action buttons
                col_app, col_rej = st.columns(2)
                
                if col_app.button("✅ Approve Campaign & Start SDR Personalizer Node", type="primary", use_container_width=True):
                    with st.spinner("Resuming graph execution..."):
                        graph.invoke(Command(resume="yes"), config)
                        st.success("Campaign approved! Personalizer SDR & A2A objection simulator started.")
                        st.rerun()
                        
                if col_rej.button("❌ Reject Plan (Re-run Lead Researcher Node)", type="secondary", use_container_width=True):
                    with st.spinner("Resuming with rejection..."):
                        graph.invoke(Command(resume="no"), config)
                        st.error("Campaign rejected! Running researcher node to compile a different plan.")
                        st.rerun()
            
            else:
                # Render Active Pipeline Progress
                st.markdown("#### 🚀 Prospecting Sessions Progress")
                
                col_leads_details, col_sim_log = st.columns([1, 1])
                
                with col_leads_details:
                    st.markdown("##### 👥 Lead Progression Tracker")
                    for i, lead in enumerate(campaign.leads):
                        status_badge = ""
                        if lead.status == "approved":
                            status_badge = "<span class='success-badge'>APPROVED</span>"
                        elif lead.status == "needs_review":
                            status_badge = "<span class='review-badge'>NEEDS REVIEW</span>"
                        else:
                            status_badge = "<span class='pending-badge'>PENDING</span>"
                            
                        # Highlight active lead
                        active_style = "border: 2px solid #8A2BE2;" if i == current_lead_index and lead.status == "pending" else ""
                        
                        st.markdown(f"""
                        <div class="premium-card" style="{active_style}">
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                                <strong>{lead.name}</strong>
                                {status_badge}
                            </div>
                            <p style="font-size:0.85rem; margin-bottom:4px; color:#8E8EA0;">{lead.role} at <b>{lead.company}</b></p>
                            <p style="font-size:0.85rem; margin:0; color:#8E8EA0;">{lead.company_description}</p>
                        </div>
                        """, unsafe_allow_html=True)
                
                with col_sim_log:
                    st.markdown("##### 🎭 A2A Objection Simulator & CRM Coach Log")
                    
                    if not simulation_results:
                        st.info("Personalizer agent is currently analyzing case studies and generating cold outreach copies. Refresh to view results.")
                        if st.button("🔄 Refresh Pipeline State", use_container_width=True):
                            st.rerun()
                    else:
                        for sim in reversed(simulation_results):
                            if isinstance(sim, dict):
                                sim = SimulationResult.from_dict(sim)
                            
                            with st.container(border=True):
                                st.markdown(f"🏆 **Lead**: {sim.lead_name} | **CRM Coach Score**: `{sim.score:.0%}`")
                                st.markdown("---")
                                
                                # Render simulated SDR interaction
                                for idx, q in enumerate(sim.questions, 1):
                                    st.markdown(f"❓ **Objection {idx}**: *{q.question}*")
                                    st.markdown(f"💬 **Simulated SDR Answer**: {q.user_answer}")
                                    st.markdown(f"🎯 **Best Practice**: *{q.expected_answer}*")
                                    
                                    badge_color = "green" if q.correct else "red"
                                    st.markdown(f"🧑‍🏫 **Feedback**: :{badge_color}[{q.feedback}]")
                                    st.markdown("---")
                                
                                if sim.weak_areas:
                                    st.warning(f"💡 **Improvement Needed in**: {', '.join(sim.weak_areas)}")
                        
                        if weak_areas:
                            st.markdown("##### ⚠️ Campaign Level Weak Areas")
                            st.error(f"CRM Coach suggested SDR training focused on: {', '.join(weak_areas)}")
                            
                        # If campaign is fully processed, show completion!
                        if current_lead_index >= len(campaign.leads):
                            st.balloons()
                            st.success("🎉 Autonomous Prospecting Session completed successfully!")
                        else:
                            # Let them trigger the next step
                            if st.button("🚀 Process Next Lead Session", type="primary", use_container_width=True):
                                with st.spinner("Processing next lead..."):
                                    graph.invoke(None, config)
                                    st.rerun()
        
        if error:
            st.error(f"System halt error: {error}")

with tab_history:
    st.markdown("### 💾 SQLite Checkpoint Registry")
    
    sessions = get_existing_sessions()
    if not sessions:
        st.info("No active campaign history found in SQLite checkpoints database.")
    else:
        st.markdown("Below are distinct active campaign sessions saved in `data/checkpoints.db`:")
        for s_id in sorted(sessions, reverse=True):
            s_config = {"configurable": {"thread_id": s_id}}
            s_state = graph.get_state(s_config)
            
            if s_state and s_state.values:
                val = s_state.values
                s_goal = val.get("goal", "No target goal specified")
                s_campaign = val.get("campaign")
                leads_len = len(s_campaign.get("leads", [])) if s_campaign and isinstance(s_campaign, dict) else len(s_campaign.leads) if s_campaign else 0
                s_idx = val.get("current_lead_index", 0)
                
                with st.expander(f"Session: {s_id} — {s_goal[:60]}...", expanded=False):
                    st.markdown(f"**Goal**: {s_goal}")
                    st.markdown(f"**Total Leads Generated**: {leads_len}")
                    st.markdown(f"**Leads Processed**: {s_idx} / {leads_len}")
                    st.markdown(f"**Weak Areas Identified**: {', '.join(val.get('weak_areas', []))}")
                    
                    if st.button(f"🔌 Resume Session {s_id}", key=f"res_{s_id}", use_container_width=True):
                        # Force update st session and sidebar selectbox
                        st.success(f"🔌 Connected to session {s_id}! Please switch to the Pipeline Monitor tab to view state.")
                        st.rerun()
