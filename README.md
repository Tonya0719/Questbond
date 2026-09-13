# Technician Scheduling Agent

Week 1 deterministic field-service scheduling MVP. Natural-language intake is isolated from the scheduling engine; SQLite is used for runtime state and CSV files are used only by evaluation.

The runtime uses two specialized agents: a Customer Intake Agent and a Scheduling Operations Agent. They communicate through validated handoffs and can call only explicitly allowed tools. The LLM coordinates interaction; deterministic Python remains authoritative for technician selection and scheduling.

See [MULTI_AGENT_ARCHITECTURE.md](MULTI_AGENT_ARCHITECTURE.md) for the architecture, tool contracts, state machine, AWS/Bedrock interaction, and human-in-the-loop boundary.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python scripts/reset_db.py
python scripts/validate_seed_data.py
pytest
python evaluation/run_eval.py
streamlit run app.py
```

The default `LLM_BACKEND=mock` requires no model server or AWS credentials.

To exercise real tool calling against a local OpenAI-compatible server (for example LM Studio, Ollama's OpenAI-compatible endpoint, or vLLM), configure:

```env
LLM_BACKEND=local
LOCAL_LLM_BASE_URL=http://127.0.0.1:1234/v1
LOCAL_LLM_API_KEY=local
LOCAL_LLM_MODEL=your-tool-capable-model
LOCAL_LLM_TIMEOUT_SEC=60
```

The selected local model must support function/tool calling. The application sends requests to `POST /v1/chat/completions`; no OpenAI cloud account is required. Start the local server before running `streamlit run app.py`.

To use Amazon Bedrock instead, set `LLM_BACKEND=bedrock`, `AWS_REGION`, and `BEDROCK_MODEL_ID`.
