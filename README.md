# NORWEMA Agent Portal

Welcome to the **North West Marathi Association (NORWEMA)** digital portal. This platform is a refactored, modern SPA (Single Page Application) integrating Google Cloud Firestore, Stripe payment processing, and an advanced multi-agent system powered by the new `google-genai` SDK and Firestore Model Context Protocol (MCP) concepts.

Live Demo URL: [https://norwema-app-692906504234.europe-west2.run.app](https://norwema-app-692906504234.europe-west2.run.app)

---

## 📚 Curriculum Mapping: 5 Days of Learnings

This repository is structured to cleanly showcase the implementation of the 5-day agentic engineering curriculum:

### 📅 Day 1: Agent Personas & System Instructions
*   **Concepts:** Crafting specialized LLM system instructions, parsing parameters, and setting agent bounds.
*   **Key Files:** 
    *   [`skills/EventPlannerSkill.md`](file:///c:/Users/RUSHI/.gemini/antigravity-ide/scratch/norwema_agent_portal/skills/EventPlannerSkill.md): System prompt guidelines and operational constraints for the Event Architect Agent.
    *   [`skills/MarathiCultureSkill.md`](file:///c:/Users/RUSHI/.gemini/antigravity-ide/scratch/norwema_agent_portal/skills/MarathiCultureSkill.md): Storyteller guidelines and tone of voice configuration for the Cultural Blogger Agent.

### 🛠️ Day 2: Function Calling & Tool Registration
*   **Concepts:** Defining structured python tool functions and mapping them for LLM execution.
*   **Key Files:**
    *   [`app.py`](file:///c:/Users/RUSHI/.gemini/antigravity-ide/scratch/norwema_agent_portal/app.py#L945-L1002): The `_build_tool_registry()` function registers native python tools like `mcp_commit_event_to_db`, `mcp_create_registration_form`, and `mcp_draft_cultural_blog` for agent invocation.

### 🤖 Day 3: Multi-Agent Orchestration & Loops
*   **Concepts:** Managing multi-agent taxonomies, forcing tool actions via configuration (forcing `mode="ANY"` or `mode="AUTO"`), and agent-to-agent division of labor.
*   **Key Files:**
    *   [`app.py`](file:///c:/Users/RUSHI/.gemini/antigravity-ide/scratch/norwema_agent_portal/app.py#L1004-L1145): The `run_live_agent()` function executes a live agentic loop (up to 5 rounds) using the new `google-genai` SDK, dynamically forcing function calls on the first round and disabling them afterwards to extract a clean text summary.

### 💾 Day 4: State Management & Persistent Memory
*   **Concepts:** Database persistence, state recovery, and mock-payment gateway integration.
*   **Key Files:**
    *   [`mcp_server_db.py`](file:///c:/Users/RUSHI/.gemini/antigravity-ide/scratch/norwema_agent_portal/mcp_server_db.py): Emulates a Model Context Protocol database server that connects directly to Google Cloud Firestore collections (`events`, `blogs`, `registrations`, `form_schemas`) or falls back to local JSON databases when offline.
    *   [`db_manager.py`](file:///c:/Users/RUSHI/.gemini/antigravity-ide/scratch/norwema_agent_portal/db_manager.py): Orchestrates CRUD operations and manages ContextVar logging middleware for real-time console tracing.
    *   [`app.py`](file:///c:/Users/RUSHI/.gemini/antigravity-ide/scratch/norwema_agent_portal/app.py#L318-L437): Stripe payments integration callback and Stripe Sandbox simulation page ensuring paid status is correctly written to memory.

### 🚀 Day 5: Secure Cloud Deployment & Secrets
*   **Concepts:** Containerization, serverless scaling, API key management, and cloud secret retrieval.
*   **Key Files:**
    *   [`app.py`](file:///c:/Users/RUSHI/.gemini/antigravity-ide/scratch/norwema_agent_portal/app.py#L34-L59): `_load_gemini_api_key_from_secrets()` retrieves the Gemini API key securely from GCP Secret Manager, falling back to environment variables.
    *   [`Dockerfile`](file:///c:/Users/RUSHI/.gemini/antigravity-ide/scratch/norwema_agent_portal/Dockerfile): Container builds for Google Cloud Run deployment.
    *   [`deployment_guide.md`](file:///c:/Users/RUSHI/.gemini/antigravity-ide/scratch/norwema_agent_portal/deployment_guide.md): Comprehensive instructions on setting up GitHub, creating Native Firestore, pushing Docker images to Artifact Registry, and scaling Google Cloud Run.

---

## 🛠️ Local Setup & Execution

### Prerequisites
*   Python 3.10+
*   Pip

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Create a `.env` file in the root:
```env
GEMINI_API_KEY=your_gemini_api_key_here
NORWEMA_ADMIN_PASSWORD=your_admin_password
STRIPE_SECRET_KEY=optional_stripe_secret_key
```

### 3. Run the Server
```bash
uvicorn app:app --port 8080 --reload
```
Open `http://localhost:8080` in your browser.
