# Technician Scheduling Agent

Week 1 field-service scheduling MVP with a business request form, agent handoffs, auditable recommendations, coordinator confirmation, technician schedules, and downloadable customer email drafts. SQLite is used for runtime state and CSV files are used only by evaluation.

The runtime uses two specialized agents: a Customer Intake Agent and a Scheduling Operations Agent. They communicate through validated handoffs and can call only explicitly allowed tools. The LLM coordinates interaction; deterministic Python remains authoritative for technician selection and scheduling.

See [MULTI_AGENT_ARCHITECTURE.md](MULTI_AGENT_ARCHITECTURE.md) for the architecture, tool contracts, state machine, AWS/Bedrock interaction, and human-in-the-loop boundary.

See [the implementation review](docs/IMPLEMENTATION_REVIEW.md) and [35-case validation matrix](docs/TEST_MATRIX.md) for the latest guardrails, implemented suggestions, test coverage and remaining live-evaluation work. The dashboard now records provider-reported model cost per request. Offline tests should use `LLM_BACKEND=mock` explicitly when `.env` points to a paid provider.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/init_db.py
python scripts/validate_seed_data.py
pytest
python evaluation/run_eval.py
streamlit run app.py
```

On macOS/Linux, activate the environment with `source .venv/bin/activate` instead of the Windows command. Initialize a fresh database once. `reset_db.py` deletes runtime records and should only be used intentionally to rebuild demo data.

## Business demo

1. Customer: enter a synthetic name, email, apartment, area, future date and time window. Try `The kitchen pipe is leaking` or `The aircon is leaking`.
2. The Intake Agent maps the service and saves validated fields. The Scheduling Operations Agent calls the deterministic engine, validates its result, and creates a recommendation.
3. Coordinator: select the request, inspect candidates, exclusions, tool inputs/results and handoffs, then confirm the recommendation.
4. Confirmation revalidates availability inside a SQLite write transaction, creates one work order, and adds it to the technician schedule.
5. Download the customer email draft. No message is sent.

The view switcher is a local demo, not authentication. Do not expose real customer records until login and server-side role checks are added. Disruption recovery, job completion/customer confirmation, and email sending are future milestones. Travel-time buffers are not implemented in this repository's slot search yet.

The architecture document includes a historical missing-feature list. The implemented code already contains the two agents, Converse tool loop, tool registry/executor, workflow state machine, session/handoff/tool audits, and recommendation validation.

The default `LLM_BACKEND=mock` requires no model server or AWS credentials.

To exercise real tool calling through the OpenAI-compatible development path, set `LLM_BACKEND=local`. This route can point either to a model server running on this computer (for example LM Studio, Ollama's OpenAI-compatible endpoint, or vLLM) or to a remote OpenAI-compatible API such as OpenRouter.

For a model server running on this computer:

```env
LLM_BACKEND=local
LOCAL_LLM_BASE_URL=http://127.0.0.1:1234/v1
LOCAL_LLM_API_KEY=local
LOCAL_LLM_MODEL=your-tool-capable-model
LOCAL_LLM_TIMEOUT_SEC=60
```

For OpenRouter-based local development/debugging:

```env
LLM_BACKEND=local
LOCAL_LLM_BASE_URL=https://openrouter.ai/api/v1
LOCAL_LLM_API_KEY=sk-or-v1-your-key-here
LOCAL_LLM_MODEL=your-openrouter-model-id
LOCAL_LLM_TIMEOUT_SEC=60
```

The selected model must support function/tool calling. The shared `LocalOpenAICompatibleClient` sends requests to `POST {LOCAL_LLM_BASE_URL}/chat/completions`, so the agent/orchestration/scheduling code does not change when switching between a local model server and OpenRouter.

OpenRouter credit/key metadata can be checked manually during development with:

```bash
python scripts/check_llm_credit.py
```

The credit check is developer-only: it is not called automatically by the Agent and does not modify SQLite runtime state.

To use Amazon Bedrock instead, set `LLM_BACKEND=bedrock`, `AWS_REGION`, and `BEDROCK_MODEL_ID`.
# Shared staff sign-in

The Customer form is public. Select Technician or Coordinator in **Sign in as** to open a password-protected staff workspace. Sign out ends staff access; switching roles requires signing in again.

Development demo passwords: Technician `DispatchTech2026!`; Coordinator `DispatchOps2026!`. Override them with `TECHNICIAN_PASSWORD` and `COORDINATOR_PASSWORD` in your ignored `.env`. Outside `APP_ENV=development`, staff sign-in stays disabled until these passwords are configured. Restart the app after changing them.

This is shared role access for the hackathon, not individual staff authentication. A signed-in technician can select any technician's demo schedule. Per-person accounts and access restrictions are a separate milestone. The short retry cooldown applies only to the current browser session.
