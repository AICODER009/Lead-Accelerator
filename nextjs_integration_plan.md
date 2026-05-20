# ⚡ Next.js Production Frontend Integration Plan
### Migrating B2B Lead Accelerator from Streamlit to a Decoupled Next.js + FastAPI Microservice Architecture

---

## 📌 Executive Summary

To support high-concurrency enterprise outbound campaigns, we propose migrating the **B2B Lead Accelerator Studio** from its local single-user Streamlit dashboard to a decoupled, production-grade **Next.js (App Router)** React frontend communicating with a unified **FastAPI Agent Gateway**. 

This plan details:
1.  **System Decoupling**: Transitioning from a Python-monolith script (Streamlit) to a modern full-stack web application structure (Next.js client + FastAPI backend).
2.  **Real-Time State Synchronization**: Leveraging **Server-Sent Events (SSE)** or **WebSockets** to stream LangGraph's dynamic state updates directly to React components.
3.  **Production Next.js Dashboard Structure**: Implementing interactive approval tables, rich charts for objection response analysis, and full session caching using Next.js route handlers.

---

## 🗺️ Production Next.js Architecture Overview

```
 ┌────────────────────────────────────────────────────────┐
 │                   Next.js Frontend                     │
 │  (App Router, TypeScript, React, Tailwind, Framer)     │
 └───────────┬────────────────────────────────┬───────────┘
             │                                │
             │ REST API (JSON)                │ WebSockets / SSE (Real-Time Streams)
             ▼                                ▼
 ┌────────────────────────────────────────────────────────┐
 │                 FastAPI Agent Gateway                  │
 │      (Exposes LangGraph state machines via ASGI)       │
 └───────┬──────────────┬──────────────┬──────────────┬───┘
         │              │              │              │
         ▼              ▼              ▼              ▼
 ┌──────────────┐┌──────────────┐┌──────────────┐┌──────────────┐
 │A2A Port 9001 ││A2A Port 9002 ││  MCP Server  ││  Cloud SQL   │
 │ Objection    ││ Research     ││ Memory       ││ Persistent   │
 │ Simulator    ││ Partner      ││ (Context)    ││ state DB    │
 └──────────────┘└──────────────┘└──────────────┘└──────────────┘
```

---

## 🛠️ Proposed Changes

Grouped by layer, here are the exact steps and code structures required to implement this Next.js-driven production model.

### 1. Backend Layer: FastAPI Agent API Gateway
We will expose the LangGraph workflows as a decoupled HTTP service using **FastAPI** and **langgraph-sdk** or raw FastAPI WebSocket routers.

#### [NEW] `src/api_gateway.py`
*   **Purpose**: Bootstraps the LangGraph loop as a high-concurrency ASGI server, replacing the local synchronous CLI execution blocks.

```python
import os
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from graph.workflow import graph
from graph.state import initial_state
from langgraph.types import Command

app = FastAPI(title="⚡ B2B Lead Accelerator Production Gateway")

# Enable secure communication with Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class CampaignRequest(BaseModel):
    goal: str
    session_id: str

@app.post("/api/campaigns/start")
async def start_campaign(req: CampaignRequest):
    """Initializes a new state graph session and runs up to the Human Approval Gate."""
    try:
        inputs = initial_state(goal=req.goal, session_id=req.session_id)
        config = {"configurable": {"thread_id": req.session_id}}
        
        # Run graph in an executor to prevent blocking the event loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: graph.invoke(inputs, config))
        
        # Determine the next node to execute (e.g. human_approval)
        state = graph.get_state(config)
        return {
            "session_id": req.session_id,
            "next_step": state.next[0] if state.next else "complete",
            "values": state.values
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/campaigns/approve")
async def approve_campaign(session_id: str, approved: bool):
    """Resumes the LangGraph campaign sequence after the human gate."""
    config = {"configurable": {"thread_id": session_id}}
    state = graph.get_state(config)
    
    if not state or not state.next or state.next[0] != "human_approval":
        raise HTTPException(status_code=400, detail="No campaign awaiting approval in this session.")
        
    loop = asyncio.get_event_loop()
    resume_command = "yes" if approved else "no"
    
    # Send resume signal to LangGraph interrupt gate
    await loop.run_in_executor(
        None, 
        lambda: graph.invoke(Command(resume=resume_command), config)
    )
    
    updated_state = graph.get_state(config)
    return {
        "session_id": session_id,
        "next_step": updated_state.next[0] if updated_state.next else "complete",
        "values": updated_state.values
    }
```

---

### 2. Frontend Layer: Next.js (TypeScript) Project Structure
A new sub-directory `frontend/` will be initialized in the workspace containing the Next.js setup:

```text
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx         # Root layout with premium dark mode theme
│   │   ├── page.tsx           # Landing page / ICP Setup
│   │   ├── dashboard/
│   │   │   └── page.tsx       # Live Campaign Monitor
│   │   └── api/
│   │       └── proxy/route.ts # Secure API proxy for FastAPI
│   ├── components/
│   │   ├── ui/
│   │   │   ├── GlassCard.tsx  # Sleek Glassmorphism container
│   │   │   └── ProgressBar.tsx# Modern campaign progression bar
│   │   ├── ApprovalTable.tsx  # HIP Approval gate interface
│   │   └── SimulationLog.tsx  # Chat interface showing SDR vs Objection
│   └── hooks/
│       └── useCampaign.ts     # Dynamic react hook managing state polls/SSE
├── tailwind.config.js
├── package.json
└── tsconfig.json
```

---

### 3. Key Next.js Component Implementations

#### [NEW] `frontend/src/hooks/useCampaign.ts`
*   **Purpose**: Orchestrates state polling and websocket callbacks. Encapsulates all SDR Campaign transitions inside a clean, reactive hook.

```typescript
import { useState, useEffect } from 'react';

export function useCampaign(sessionId: string) {
  const [state, setState] = useState<any>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchState = async () => {
    try {
      const response = await fetch(`/api/campaigns/status?session_id=${sessionId}`);
      if (!response.ok) throw new Error("Failed to load campaign state");
      const data = await response.json();
      setState(data);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const startCampaign = async (goal: string) => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/campaigns/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ goal, session_id: sessionId })
      });
      const data = await res.json();
      setState(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const submitApproval = async (approved: boolean) => {
    setLoading(true);
    try {
      const res = await fetch(`/api/campaigns/approve?session_id=${sessionId}&approved=${approved}`, {
        method: 'POST'
      });
      const data = await res.json();
      setState(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Poll state every 4 seconds when processed and waiting
  useEffect(() => {
    if (!sessionId) return;
    fetchState();
    const interval = setInterval(fetchState, 4000);
    return () => clearInterval(interval);
  }, [sessionId]);

  return { state, loading, error, startCampaign, submitApproval, refresh: fetchState };
}
```

#### [NEW] `frontend/src/app/dashboard/page.tsx`
*   **Purpose**: Premium, rich, glassmorphic monitoring console displaying the campaign flow.

```tsx
'use client';

import React, { useState } from 'react';
import { useCampaign } from '@/hooks/useCampaign';
import GlassCard from '@/components/ui/GlassCard';
import ApprovalTable from '@/components/ApprovalTable';
import SimulationLog from '@/components/SimulationLog';

export default function Dashboard() {
  const [sessionId, setSessionId] = useState<string>('prod-session-1');
  const [goal, setGoal] = useState<string>('SaaS Founders in NY who need outbound lead automation');
  const { state, loading, startCampaign, submitApproval } = useCampaign(sessionId);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 p-8 font-sans">
      <header className="mb-10">
        <h1 className="text-4xl font-extrabold tracking-tight bg-gradient-to-r from-pink-500 via-purple-600 to-cyan-400 bg-clip-text text-transparent">
          ⚡ B2B Lead Accelerator Studio
        </h1>
        <p className="text-slate-400 mt-2">Enterprise Production Console — React Full-Stack</p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Left Column: Configuration Controls */}
        <div className="space-y-6">
          <GlassCard title="🎯 Targeting & Goal Setup">
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-semibold text-slate-400 mb-2">Campaign Goal</label>
                <textarea 
                  className="w-full bg-slate-900 border border-slate-800 rounded-lg p-3 text-slate-100 focus:outline-none focus:border-purple-500" 
                  value={goal}
                  onChange={(e) => setGoal(e.target.value)}
                  rows={4}
                />
              </div>
              <button 
                onClick={() => startCampaign(goal)}
                className="w-full py-3 bg-gradient-to-r from-purple-600 to-indigo-600 rounded-lg font-bold hover:from-purple-500 hover:to-indigo-500 transition-all shadow-lg shadow-purple-500/20"
                disabled={loading}
              >
                {loading ? 'Initializing Pipeline...' : '🚀 Start Outbound Campaign'}
              </button>
            </div>
          </GlassCard>
        </div>

        {/* Center/Right Columns: State Monitor & Human Approval */}
        <div className="lg:col-span-2 space-y-6">
          {state?.next_step === 'human_approval' && (
            <GlassCard title="⚠️ Human Approval Interrupt Gate" borderClass="border-amber-500/40 bg-amber-950/10">
              <p className="text-amber-400 text-sm mb-4">
                A B2B outbound campaign list has been compiled. Please review the hooks before approving.
              </p>
              <ApprovalTable campaign={state?.values?.campaign} />
              
              <div className="flex gap-4 mt-6">
                <button 
                  onClick={() => submitApproval(true)}
                  className="flex-1 py-3 bg-emerald-600 hover:bg-emerald-500 rounded-lg font-bold transition-all text-white"
                >
                  ✅ Approve Plan & Trigger SDR Copywriting
                </button>
                <button 
                  onClick={() => submitApproval(false)}
                  className="flex-1 py-3 bg-rose-600 hover:bg-rose-500 rounded-lg font-bold transition-all text-white"
                >
                  ❌ Reject (Re-run Lead Researcher)
                </button>
              </div>
            </GlassCard>
          )}

          {/* Adversarial Simulation Logs */}
          <GlassCard title="🎭 A2A Adversarial objection simulator">
            <SimulationLog results={state?.values?.simulation_results} />
          </GlassCard>
        </div>
      </div>
    </div>
  );
}
```

---

## ☁️ Production Deployment Configuration (Multi-Container)

In Next.js production deployments, we containerize both the backend (FastAPI gateway) and frontend (Next.js server) separately, coordinating secure service communication.

### [NEW] `frontend/Dockerfile.frontend`
*   **Purpose**: Production optimized build stages for Next.js.

```dockerfile
# Stage 1: Dependency builder
FROM node:18-alpine AS deps
WORKDIR /app
COPY package*.json ./
RUN npm ci

# Stage 2: NextJS builder
FROM node:18-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# Stage 3: Runner
FROM node:18-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
ENV PORT=3000
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

EXPOSE 3000
CMD ["npm", "start"]
```

---

## 🧪 Verification Plan

### 1. API Verification
We will run custom script integration tests checking that the FastAPI HTTP backend is responsive and coordinates with LangGraph state registers correctly:
```bash
pytest tests/test_production_api.py
```

### 2. Next.js Dev Mode Verification
To spin up and test the frontend prototype locally:
```powershell
cd frontend
npm run dev
```
Navigate to `http://localhost:3000` to verify:
- Streamlit styled glassmorphic panels render correctly in React.
- Clicking the "Start Outbound Campaign" button fires a POST request to FastAPI on port `8000`.
- Triggering approval sends a valid LangGraph Command and resumes graph processing.
