# Technician Scheduling Agent — Project Introduction & Handoff Guide

> Keep the team sync to **10–15 minutes**. Do not start with the code directory. Present it in this order: **why we split the system this way → how the flow works → what teammates need to do next**.

## 1. One-Sentence Introduction

> We currently use a two-Agent architecture: the Customer Intake Agent understands customer needs and collects missing information, while the Scheduling Operations Agent invokes a deterministic scheduling engine to generate and validate assignment recommendations. The LLM does not directly select technicians, and critical operational changes remain under Human Coordinator control.

The purpose of this split is not to build a complicated Multi-Agent framework. It is to separate three types of responsibility clearly:

1. **Natural-language understanding and interaction** — handled by Agents / the LLM.
2. **Business constraints and scheduling calculations** — handled by deterministic Python engines.
3. **Critical operational decisions and approval** — retained by the Human Coordinator.

---

## 2. Why We Split the System This Way

The core challenge in Technician Scheduling is not asking an LLM to guess a technician. It is generating a **feasible, explainable, and auditable** schedule under real business constraints.

Therefore, we enforce the following boundaries:

- The LLM understands customer language, asks for missing information, selects tools, and explains results.
- The Python scheduling engine handles skills, certifications, shifts, conflicts, workload, slot search, and ranking.
- Agents do not execute arbitrary Python functions or direct SQL.
- Agents may only call tools registered in the Tool Registry and allowed for that Agent.
- Critical inputs are validated with Pydantic.
- Assignment recommendations can be persisted, but Week 1 does not directly overwrite current `schedules`.
- Evaluation Ground Truth is completely isolated from Runtime SQLite.

In one line:

> **The Agent coordinates, the Engine calculates, and the Human retains critical control.**

---

## 3. Current Business Flow

```text
Customer message
→ Customer Intake Agent
→ Structured Request
→ Agent Handoff
→ Scheduling Operations Agent
→ Deterministic Scheduling Engine
→ Assignment Recommendation
→ Coordinator Dashboard
```

Three points to emphasise:

1. This is a **Multi-Agent workflow**, not a one-shot LLM extraction call.
2. Agents communicate through structured Handoffs instead of relying on implicit free-text transfer.
3. Technician selection is performed by deterministic Python, not directly by the LLM.

---

## 4. Customer Intake Agent

### 4.1 Main Responsibilities

The Customer Intake Agent converts natural-language requests into a schedulable `StructuredRequest`:

- Understand customer messages
- Retrieve existing customer context
- Look up the standard Service Rule
- Extract service type, zone/location, urgency, and appointment window
- Detect missing or ambiguous fields
- Ask clarification questions proactively
- Save the Structured Request
- Send a `REQUEST_READY` Handoff once information is complete

### 4.2 Allowed Tools

```text
get_customer_context
lookup_service_rules
save_structured_request
get_request_status
```

### 4.3 Out of Scope

The Customer Intake Agent does **not**:

- Select technicians
- Check technician conflicts
- Calculate workload
- Search feasible slots
- Rank technician candidates
- Modify schedules

---

## 5. Scheduling Operations Agent

### 5.1 Week 1 Responsibilities

The Scheduling Operations Agent receives a ready request and coordinates deterministic scheduling:

- Receive `REQUEST_READY`
- Recheck request readiness
- Invoke the deterministic Assignment Engine
- Retrieve technician candidates and exclusion reasons
- Validate the assignment recommendation
- Retrieve the Decision Trace
- Generate an explanation for the Coordinator
- Escalate when no feasible result exists

### 5.2 Allowed Tools

```text
get_request_status
recommend_assignment
validate_assignment_recommendation
get_assignment_decision_trace
```

### 5.3 Week 2 Evolution

Week 2 does not introduce a separate Rescheduling Agent. Instead, the existing Scheduling Operations Agent gains a second mode:

```text
DISRUPTION_RECOVERY
```

Initial assignment and rescheduling share most of the same domain information and constraints:

- Service rules
- Skills / certifications
- Technician status
- Shift
- Existing schedules
- Customer time window
- Workload capacity
- Feasible slot search

Keeping both in one Operations Agent avoids duplicated prompts, tools, context, and error handling.

---

## 6. Human Coordinator Positioning

The Coordinator currently remains:

> **Human + Dashboard, not an independent Agent.**

### Week 1

The Coordinator mainly:

- Reviews the raw customer request
- Reviews AI-extracted fields
- Reviews Agent Handoffs / Tool Calls
- Reviews the recommended technician and appointment time
- Reviews candidate exclusion reasons
- Handles `NO_FEASIBLE_ASSIGNMENT`

Week 1 only displays and reviews recommendations; it does not directly modify `schedules`.

### Week 2

Once confirmed-appointment rescheduling is introduced, add:

- Approve
- Reject
- Approval state
- Before / After comparison
- Apply approved proposal

Core permission boundary:

```text
Agent can propose
Human can approve or reject
System can apply only an approved proposal
```

---

## 7. Relationship Between Agent, Tool, and Deterministic Engine

The key technical relationship is:

```text
Agent
→ Tool Registry
→ Tool Executor
→ Deterministic Engine / Application Service
→ SQLite
```

### Tool Registry

Defines:

- Which tools exist
- Which Agent may call each tool
- Input Schema
- Tool handler
- Read / Write permissions

### Tool Executor

Handles:

- Tool existence checks
- Agent permission checks
- Pydantic input validation
- Handler execution
- Normalised error handling
- Logging of input / output / status / duration

### Deterministic Scheduling Engine

Performs the actual calculation:

```text
Readiness Gate
→ Service Rule Lookup
→ Skill Filtering
→ Certification Filtering
→ Technician Status Filtering
→ Shift Validation
→ Customer Window Validation
→ Existing Schedule Conflict Check
→ Dynamic Workload Calculation
→ Workload Capacity Check
→ 30-minute Slot Search
→ Deterministic Ranking
```

Ranking is fixed as:

```text
projected workload ratio
→ earliest feasible start
→ technician ID
```

As a result, changing the LLM does not change the core business rules used to generate the assignment result.

---

## 8. Current LLM Backends

Local development supports three main modes:

| Backend | Purpose |
|---|---|
| `mock` | No real-model dependency; stable testing of Agents, Tools, and scheduling flow |
| `local` | Connects to an OpenAI-compatible API, including LM Studio, OpenRouter, or similar development endpoints |
| `bedrock` | Final AWS / Amazon Bedrock path |

With `local`, the project is using an OpenAI-compatible API; the model does not have to be physically hosted on the same computer. OpenRouter can also be used through this path.

---

## 9. Runtime Data vs Evaluation Boundary

Runtime business data is stored in SQLite, for example:

```text
company_profile
service_rules
technicians
customers
jobs
schedules
customer_requests
structured_requests
assignment_results
agent_sessions
agent_handoffs
agent_tool_calls
```

Evaluation data remains separate CSV data, for example:

```text
cases.csv
request_ground_truth.csv
assignment_ground_truth.csv
```

The required boundary is:

> **Runtime Agents must never read Ground Truth.**

Ground Truth exists only for offline evaluation and must not influence runtime decisions.

---

## 10. Three Recommended Demo Cases

Do not only show the code directory. Run three business cases directly.

### Case 1: Complete Request

Example:

```text
My aircon is leaking in East.
I am available from 2026-09-15T14:00 to 2026-09-15T17:00.
```

Show:

```text
Intake Agent
→ REQUEST_READY
→ Scheduling Operations Agent
→ Technician recommendation
→ Decision Trace
→ Coordinator Dashboard
```

This demonstrates:

- Agent Handoff
- Tool Calling
- Deterministic Assignment
- Explainability

### Case 2: Missing Information

Example:

```text
My toilet is blocked.
```

Show:

- Intake Agent detects a missing appointment window / location or other required fields
- Agent asks a clarification question
- Customer provides the missing information
- The same Agent Session continues
- Request becomes ready
- Handoff to the Scheduling Agent

This demonstrates:

- Multi-turn interaction
- Readiness Gate
- Structured Handoff

### Case 3: No Feasible Technician

Use a very late, very narrow, or conflicting appointment window.

Show:

- All candidates are excluded by the deterministic engine
- Exclusion reason for each technician
- `NO_FEASIBLE_ASSIGNMENT` / `HUMAN_REVIEW_REQUIRED`
- No automatic modification of the current schedule

This demonstrates:

- Constraint enforcement
- Decision Trace
- Human-in-the-loop
- Safe failure

Together, the three cases demonstrate:

- Multi-Agent design
- Tool Calling
- Multi-turn dialogue
- Deterministic Scheduling
- Explainability
- Human-in-the-loop

---

## 11. Files to Show the Team

Do not explain every file. Show the main path only:

| File | Purpose |
|---|---|
| `MULTI_AGENT_ARCHITECTURE.md` | Overall architecture and boundaries |
| `src/orchestration/orchestrator.py` | Controls Agent workflow, state, and handoff |
| `src/agents/intake_agent.py` | Customer Intake Agent |
| `src/agents/scheduling_operations_agent.py` | Scheduling Operations Agent |
| `src/tools/registry.py` | Agent Tool allowlist and schemas |
| `src/tools/executor.py` | Tool validation and execution safety boundary |
| `src/scheduling/assignment_engine.py` | Deterministic assignment core |
| `src/database.py` | SQLite schema and database interface |

The main concept teammates need to understand is:

```text
Agent → Tool Executor → Deterministic Engine → SQLite
```

not every directory in the repository.

---

## 12. Decisions to Align With the Team

Confirm the following during the meeting:

1. Do we agree on two Runtime Agents for Week 1?
2. Do we agree to keep Assignment and Rescheduling inside one Scheduling Operations Agent for now?
3. Do we agree that the Coordinator remains Human + Dashboard in Week 1?
4. Do we accept that the LLM does not directly select technicians?
5. Do we accept that Week 1 recommendations do not directly modify `schedules`?
6. Is the StructuredRequest Schema frozen?
7. Is the Handoff Schema frozen?
8. Which backend should the Demo primarily use: Mock, Local LLM, or Bedrock?
9. Who owns each module and interface?
10. What are the Week 2 rescheduling and approval boundaries?

---

## 13. Recommended Team Split

| Module | Main Responsibilities |
|---|---|
| Data & Setup | Seed data, SQLite, Service Rules, consistency checks, validation |
| Customer Intake | Intake Prompt, Tool Calling, clarification, multi-turn interaction |
| Technician Assignment | Deterministic Scheduling Engine, constraints, Decision Trace |
| Coordinator UI | Agent Timeline, recommendation details, human handling and later approval |
| AWS / Deployment | Bedrock, Guardrails, deployment, fallback |
| Evaluation | Extraction accuracy, assignment validity, demo cases, regression tests |

Freeze interfaces first, then develop in parallel to minimise multiple people changing the same core files.

---

## 14. Team Sync Message You Can Send Directly

```text
Hi team, I have built the initial Technician Scheduling architecture and want to align on the current design and boundaries.

We are using a two-Agent architecture:

1. Customer Intake Agent
- Understands customer natural language
- Retrieves customer context and standard Service Rules
- Extracts service type, location, and appointment window
- Proactively asks for missing information
- Produces a StructuredRequest

2. Scheduling Operations Agent
- Receives the Intake Agent's REQUEST_READY handoff
- Calls the deterministic Scheduling Engine
- Validates the assignment recommendation
- Retrieves candidate technicians, exclusion reasons, and the decision trace
- Generates an explanation or escalates to human handling

Important boundaries:
- The LLM does not directly select technicians
- Skill, certification, shift, conflict, workload, slot search, and ranking are handled by deterministic Python
- Agents may only call allowlisted Tools
- Tool inputs are validated with Pydantic
- Recommendations are written to assignment_results but do not directly overwrite schedules
- The Coordinator is currently Human + Dashboard
- Evaluation CSV is fully isolated from Runtime SQLite

Local development supports three modes:
- mock: no model dependency; stable testing
- local: OpenAI-compatible API, including local servers or OpenRouter
- bedrock: final AWS path

Week 1 focuses on the two-Agent intake → handoff → assignment flow.
Week 2 will add unavailable/delayed events and rescheduling proposals inside the Scheduling Operations Agent, followed by Human Approve/Reject.

Architecture document:
MULTI_AGENT_ARCHITECTURE.md

Current tests: please use the latest pytest result before the meeting.
```

---

## 15. Suggested 10–15 Minute Sync Structure

### 0–2 min: Why the system is split this way

Explain:

- The LLM is not the scheduling optimiser
- Two Agents separate Intake from Scheduling responsibilities
- Human control remains for critical changes

### 2–5 min: How the flow works

Show:

```text
Customer
→ Intake Agent
→ Structured Request
→ Handoff
→ Scheduling Agent
→ Deterministic Engine
→ Recommendation
→ Coordinator
```

### 5–8 min: Agent / Tool / Engine boundaries

Show the two Tool Allowlists and:

```text
Agent → Tool Executor → Engine
```

### 8–12 min: Demo

Run:

1. Complete request
2. Clarification case
3. No feasible technician

### 12–15 min: Handoff and ownership

Confirm:

- Schemas
- Module owners
- Week 2 scope
- Demo backend
- AWS / Evaluation owners

---

## 16. Most Important Communication Principle

Do not say:

> I built a very complicated Multi-Agent framework.

A better framing is:

> I built a runnable skeleton that separates the Agent layer, deterministic business logic, and human approval boundary. Each teammate can now continue development behind clear interfaces without changing other people's core modules.

The purpose of the architecture is not to add complexity. It is to:

- Reduce collaboration conflicts
- Clarify responsibility boundaries
- Keep scheduling results verifiable
- Preserve Human-in-the-loop control
- Make Week 2 extensions possible without redesigning the entire system
