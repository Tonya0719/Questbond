# Technician Scheduling Agent — Codex README / Implementation Spec

## 1. Project Overview

Build a Python-based **Technician Scheduling Agent** for SME field-service operations.

Week 1 MVP flow:

```
Customer natural-language request
        ↓
AI / Intake Agent
        ↓
Structured service request
        ↓
Request readiness check
        ↓
Service rule lookup
        ↓
Technician eligibility filtering
        ↓
Feasible time-slot search
        ↓
Deterministic candidate ranking
        ↓
Assignment recommendation
        ↓
SQLite runtime database
        ↓
Coordinator / Streamlit UI
```

Core design principle:

> **The LLM understands and structures requests. Deterministic Python logic performs scheduling and technician assignment.**
> 

The LLM must **not directly choose a technician based on free-form reasoning**.

## 2. Week 1 Scope

The Week 1 MVP should support:

- Customer request intake
- Natural-language information extraction
- Missing-information detection
- Structured request creation
- Service-rule lookup
- Technician skill filtering
- Certification filtering
- Technician availability filtering
- Shift validation
- Existing schedule conflict detection
- Customer appointment-window checking
- Workload-capacity checking
- Feasible time-slot search
- Deterministic technician ranking
- Assignment recommendation
- Assignment explanation
- Runtime persistence in SQLite
- Separate CSV-based evaluation

Week 1 should **not** implement:

- real-time traffic
- live GPS
- route optimization
- material shortage
- weather
- multi-day optimization
- global multi-job optimization
- disruption cascade
- automatic rescheduling
- real WhatsApp integration

## 3. Recommended Tech Stack

Use:

```
Python 3.11+
Streamlit
SQLite
sqlite3
pandas
Pydantic
pytest
python-dotenv
```

LLM layer:

```
Amazon Bedrock
```

The model should be configurable rather than hard-coded.

Example:

```
BEDROCK_MODEL_ID=<configured-in-env>
AWS_REGION=ap-southeast-1
```

If Bedrock credentials are unavailable during local development, implement a **mock intake backend** so the rest of the system can still run.

## 4. Architecture

```
Customer / Technician / Coordinator
                │
                ▼
        Streamlit Application
                │
       ┌────────┼─────────┐
       │        │         │
       ▼        ▼         ▼
 Intake Agent  Runtime   Scheduling Engine
       │       Services       │
       ▼        │             │
 Amazon        │             │
 Bedrock       │             │
       │        │             │
       └───────►SQLite◄────────┘
                │
                ▼
       Operational Runtime Data
```

Evaluation must remain isolated:

```
Runtime Application
      │
      └── SQLite
          ├── customers
          ├── service_rules
          ├── technicians
          ├── jobs
          ├── schedules
          ├── customer_requests
          ├── structured_requests
          └── assignment_results

Evaluation Harness
      │
      └── CSV files
          ├── cases.csv
          ├── request_ground_truth.csv
          └── assignment_ground_truth.csv
```

**Critical rule:** Runtime code must never load evaluation ground-truth CSV files.

## 5. Project Structure

```
technician-scheduling-agent/
│
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── app.py
│
├── data/
│   ├── runtime/
│   │   ├── seed/
│   │   │   ├── company_profile.json
│   │   │   ├── service_rules.csv
│   │   │   ├── technicians.csv
│   │   │   ├── customers.csv
│   │   │   ├── jobs_current.csv
│   │   │   ├── schedule_current.csv
│   │   │   └── customer_requests.csv
│   │   └── technician_scheduling.db
│   └── evaluation/
│       ├── cases.csv
│       ├── request_ground_truth.csv
│       └── assignment_ground_truth.csv
│
├── src/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── seed_database.py
│   ├── validators.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── request.py
│   │   ├── technician.py
│   │   └── assignment.py
│   ├── intake/
│   │   ├── __init__.py
│   │   ├── intake_agent.py
│   │   ├── bedrock_client.py
│   │   ├── mock_intake.py
│   │   └── parser.py
│   ├── scheduling/
│   │   ├── __init__.py
│   │   ├── eligibility.py
│   │   ├── conflicts.py
│   │   ├── workload.py
│   │   ├── slots.py
│   │   ├── ranking.py
│   │   └── assignment_engine.py
│   ├── services/
│   │   ├── request_service.py
│   │   ├── technician_service.py
│   │   ├── schedule_service.py
│   │   └── assignment_service.py
│   └── ui/
│       ├── customer_view.py
│       ├── coordinator_view.py
│       └── technician_view.py
│
├── evaluation/
│   ├── run_eval.py
│   ├── evaluate_requests.py
│   └── evaluate_assignments.py
│
├── scripts/
│   ├── init_db.py
│   ├── reset_db.py
│   └── validate_seed_data.py
│
└── tests/
    ├── test_request_readiness.py
    ├── test_eligibility.py
    ├── test_conflicts.py
    ├── test_slots.py
    ├── test_workload.py
    ├── test_ranking.py
    └── test_assignment_engine.py
```

## 6. Runtime Data Design

Runtime data must be stored in:

```
data/runtime/technician_scheduling.db
```

SQLite should be accessed through Python's built-in `sqlite3`.

Do not introduce PostgreSQL, MySQL, or RDS for Week 1.

## 7. SQLite Tables

### `company_profile`

Fields:

```
company_id
business_type
operating_start
operating_end
dispatch_policy
```

Purpose: company operating hours and scheduling-policy configuration.

### `service_rules`

Fields:

```
service_rule_id
category
subtype
required_skills
required_certifications
default_duration_min
default_priority
required_customer_information
```

`service_rule_id` is the **canonical service key**. `category` and `subtype` must be derived consistently from the corresponding rule.

### `technicians`

Fields:

```
technician_id
name_alias
skills
certifications
shift_start
shift_end
status
current_zone
max_workload_min
```

Do **not** store `assigned_workload_min` as the source of truth. Current workload must be dynamically calculated from active assignments.

`max_workload_min` means the company-defined maximum schedulable job workload for that technician per day. It is not necessarily equal to shift length.

### `customers`

Fields:

```
customer_id
name_alias
customer_type
contact_channel
postal_sector
zone
preferred_time
```

Known customer context may be combined with the current customer message. Current request information overrides historical preferences when explicitly provided.

### `jobs`

Fields:

```
job_id
customer_id
service_rule_id
priority
estimated_duration_min
window_start
window_end
zone
status
```

Only active relevant jobs should count toward schedule-conflict checking and current workload calculation.

### `schedules`

Fields:

```
job_id
technician_id
scheduled_start
scheduled_end
assignment_status
customer_confirmed
```

Requirements:

- `scheduled_start < scheduled_end`
- no overlapping active schedules for the same technician

### `customer_requests`

Fields:

```
request_id
customer_id_or_new
received_at
channel
raw_message
language
```

This table stores **raw immutable customer input**.

Do not store evaluation labels such as `case_type`, `normal`, `constrained`, or `incomplete` inside runtime tables.

### `structured_requests`

Fields:

```
request_id
customer_id
service_rule_id
category
subtype
zone
urgency
window_start
window_end
estimated_duration_min
missing_fields
ready_for_scheduling
```

This is the formal interface between the Intake Agent and Technician Assignment Engine.

`service_rule_id` is canonical. `category` and `subtype` may be retained for readability but must be obtained from the corresponding service rule rather than independently maintained.

### `assignment_results`

Fields:

```
assignment_id
request_id
technician_id
scheduled_start
scheduled_end
decision_status
workload_before
workload_after
recommendation_reason
created_at
```

Supported statuses:

```
ASSIGNED
NEEDS_CLARIFICATION
NO_FEASIBLE_TECHNICIAN
```

Generating a recommendation must not directly overwrite the current schedule.

## 8. Request Intake Agent

The intake component receives natural-language requests such as:

```
My aircon is leaking. I live in Tampines and I'm free tomorrow afternoon.
```

The LLM should extract scheduling-relevant information and return structured JSON.

The application must then map the request to `service_rule_id` and obtain required skills, required certifications, and default duration from `service_rules`.

The LLM must not invent these values independently.

## 9. Request Readiness Gate

Before assignment, `ready_for_scheduling` must be checked.

Scheduling-critical fields include at minimum:

```
service_rule_id
zone
window_start
window_end
estimated_duration_min
```

If information is missing:

```
ready_for_scheduling = false
```

Return `NEEDS_CLARIFICATION` and do not execute technician assignment.

## 10. Assignment Algorithm

```
Structured Request
       ↓
Readiness Gate
       ↓
Load Service Rule
       ↓
Filter Technicians
       ↓
Find Feasible Slot
       ↓
Check Workload Capacity
       ↓
Rank Candidates
       ↓
Select Winner
       ↓
Return Assignment Result
```

## 11. Hard Constraints

A technician must satisfy **all** hard constraints.

### Skill

Technician must contain all required skills. Otherwise: `SKILL_MISMATCH`.

### Certification

If certification is required, technician must possess it. Otherwise: `CERTIFICATION_MISMATCH`.

### Status

Week 1 eligible status: `AVAILABLE`.

### Customer Time Window

The entire job must fit within `window_start` and `window_end`.

### Technician Shift

The entire job must fit within `shift_start` and `shift_end`.

### Existing Schedule Conflict

Use:

```python
new_start < existing_end and new_end > existing_start
```

If true: `SCHEDULE_CONFLICT`.

### Workload Capacity

Current workload must be dynamically calculated from active jobs and schedules.

```
projected_workload = current_assigned_workload + new_job_duration
```

Must satisfy:

```
projected_workload <= max_workload_min
```

Otherwise: `WORKLOAD_LIMIT`.

## 12. Feasible Time Slot Search

Use a Week 1 fixed granularity of **30 minutes**.

For each candidate start:

1. calculate `scheduled_end`
2. check customer window
3. check technician shift
4. check schedule conflict
5. check company operating hours

The first valid time is the technician's `earliest_feasible_start`.

## 13. Candidate Ranking

Do not use arbitrary weighted scoring in Week 1.

Use deterministic lexicographic ranking:

1. Lowest projected workload ratio
2. Earliest feasible start
3. Lowest technician ID

```python
projected_workload_ratio = (
    current_workload + new_job_duration
) / max_workload_min
```

Example:

```python
candidates.sort(
    key=lambda x: (
        x["projected_workload_ratio"],
        x["scheduled_start"],
        x["technician_id"],
    )
)
```

## 14. Assignment Engine

Main interface:

```python
assign_technician(request_id: str) -> AssignmentResult
```

Recommended internal functions:

```
check_request_ready()
load_service_rule()
has_required_skills()
has_required_certifications()
get_assigned_workload()
has_schedule_conflict()
find_earliest_feasible_slot()
build_eligible_candidates()
rank_candidates()
build_assignment_reason()
assign_technician()
```

Keep these functions modular because they should later be reusable by the rescheduling engine.

## 15. Assignment Explanation

Every assignment recommendation must include an explanation containing verifiable factors such as:

- skill match
- certification match
- technician status
- schedule conflict result
- workload before
- workload after
- projected workload ratio
- ranking reason

`recommendation_reason` may be stored in SQLite as JSON text.

## 16. Evaluation Architecture

Evaluation data must remain outside SQLite runtime data.

Directory:

```
data/evaluation/
```

Files:

```
cases.csv
request_ground_truth.csv
assignment_ground_truth.csv
```

### `cases.csv`

Unified test-case registry. Suggested fields:

```
case_id
request_id
scenario_type
starting_state
ground_truth_module
pass_criteria
demo_priority
```

Do not copy expected outputs into this registry.

### `request_ground_truth.csv`

Suggested fields:

```
request_id
expected_category
expected_subtype
expected_location
expected_urgency
expected_time_window
missing_fields
expected_clarification
ready_for_scheduling
```

Used only for evaluating intake / extraction.

### `assignment_ground_truth.csv`

Suggested fields:

```
request_id
eligible_technicians
excluded_technicians_and_reasons
expected_technician
expected_start
expected_end
decision_status
recommendation_reason
```

Used only for deterministic assignment evaluation.

## 17. Evaluation Boundary

This is mandatory:

- `src/` must never import from `data/evaluation/`
- only `evaluation/` scripts may load evaluation files
- runtime code must never read ground truth

Allowed pattern:

```
evaluation/run_eval.py
→ load assignment_ground_truth.csv
→ call runtime assignment engine
→ compare actual vs expected
```

## 18. Evaluation Scenarios

Create at least 10 cases covering:

1. Exact skill match
2. Skill mismatch
3. Certification mismatch
4. Technician unavailable
5. Existing schedule conflict
6. Job outside technician shift
7. Workload capacity exceeded
8. Multiple eligible technicians
9. Same workload requiring deterministic tie-break
10. Missing service information
11. Missing appointment window
12. No feasible technician

Ten cases may cover multiple conditions.

## 19. Seed Data

Create synthetic seed data for:

```
1 company
3 service categories
9 service rules
8 technicians
12 customers
16 existing jobs
16 current schedule records
10 new customer requests
```

Service categories:

```
Air-conditioning
Plumbing
Electrical
```

Suggested subtypes:

```
Air-conditioning
- Routine servicing
- Not cooling / diagnosis
- Water leakage / repair

Plumbing
- Pipe / tap leakage
- Drain / toilet blockage
- Fixture replacement

Electrical
- Light / switch / socket repair
- Power trip diagnosis
- Minor installation / replacement
```

Data must deliberately trigger different rules. Do not create trivial data where only one technician can ever perform each service.

## 20. Seed Database Workflow

Seed JSON / CSV files live in:

```
data/runtime/seed/
```

Create `scripts/init_db.py` to:

1. create SQLite tables
2. validate seed data
3. import runtime seed files
4. produce `data/runtime/technician_scheduling.db`

Create `scripts/reset_db.py` to delete and rebuild the database.

## 21. Data Validation

Create `scripts/validate_seed_data.py`.

Validate at minimum:

- all IDs are unique
- every `service_rule_id` exists
- every scheduled `job_id` exists
- every scheduled `technician_id` exists
- no technician double booking
- `scheduled_start < scheduled_end`
- schedule lies inside technician shift
- scheduled duration matches job duration
- technician possesses required skill
- technician possesses required certification
- active workload does not exceed `max_workload_min`
- structured `category/subtype` agree with `service_rule_id`

Validation failure should print useful errors and return a non-zero exit code.

## 22. Streamlit UI

Keep the UI simple.

### Customer View

Support:

- enter service request
- submit request
- view clarification question if needed

### Coordinator View

Show:

- incoming requests
- structured request
- recommended technician
- recommended appointment time
- recommendation reason
- current technician workload

### Technician View

Week 1 can simply show:

- technician
- today's assigned jobs
- start / end time
- service type
- customer zone

Do not implement full technician workflows yet.

## 23. Bedrock Integration

Implement `src/intake/bedrock_client.py`.

The rest of the codebase must not directly call Bedrock.

Expected interface:

```python
class BedrockClient:
    def extract_request(self, raw_message: str) -> dict:
        ...
```

Use structured JSON output and validate with Pydantic.

If the model returns invalid JSON:

- retry once if appropriate
- otherwise return a controlled parsing failure

Do not silently guess missing values.

## 24. Mock Intake Backend

Implement `src/intake/mock_intake.py`.

Configuration:

```
INTAKE_BACKEND=mock
```

or:

```
INTAKE_BACKEND=bedrock
```

This keeps the scheduling engine independent from LLM availability.

## 25. Configuration

Create `src/config.py` and read from `.env`.

Example:

```
APP_ENV=development
DB_PATH=data/runtime/technician_scheduling.db
INTAKE_BACKEND=mock
AWS_REGION=ap-southeast-1
BEDROCK_MODEL_ID=
SLOT_GRANULARITY_MIN=30
```

Never commit credentials.

## 26. `.gitignore`

Include at least:

```
.env
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
.DS_Store
data/runtime/technician_scheduling.db
```

The generated database does not need to be version controlled if it can be rebuilt from seed files.

## 27. Requirements

Suggested `requirements.txt`:

```
streamlit
pandas
pydantic
python-dotenv
boto3
pytest
```

Do not add large frameworks unless necessary. Do not introduce LangChain only for simple Bedrock calls.

## 28. Testing

Use `pytest`.

Important unit tests:

```
test_request_readiness.py
test_skill_matching.py
test_certification_matching.py
test_schedule_conflict.py
test_shift_constraint.py
test_workload_capacity.py
test_feasible_slots.py
test_ranking.py
test_no_feasible_technician.py
test_deterministic_tie_break.py
```

Tests must not depend on Bedrock. Use deterministic fixtures.

## 29. Development Commands

```bash
python -m venv .venv
```

Windows activation:

```bash
.venv\Scripts\activate
```

Then:

```bash
pip install -r requirements.txt
python scripts/init_db.py
python scripts/validate_seed_data.py
pytest
python evaluation/run_eval.py
streamlit run app.py
```

## 30. Week 1 Success Criteria

- [ ]  SQLite runtime database can be initialized from seed data
- [ ]  8 technicians exist with meaningful skill/certification differences
- [ ]  16 existing jobs and schedules exist
- [ ]  Customer raw messages can be submitted
- [ ]  Intake layer produces a validated structured request
- [ ]  Missing scheduling-critical information produces clarification
- [ ]  `service_rule_id` correctly determines service requirements
- [ ]  Skill mismatch technicians are excluded
- [ ]  Certification mismatch technicians are excluded
- [ ]  Unavailable technicians are excluded
- [ ]  Shift violations are excluded
- [ ]  Schedule conflicts are detected
- [ ]  Current workload is calculated dynamically
- [ ]  Projected workload does not exceed `max_workload_min`
- [ ]  Feasible slots are found using 30-minute increments
- [ ]  Candidate ranking is deterministic
- [ ]  Assignment result is written to SQLite
- [ ]  Recommendation reason is returned
- [ ]  No feasible candidate returns `NO_FEASIBLE_TECHNICIAN`
- [ ]  Evaluation CSV files are isolated from runtime
- [ ]  Evaluation script compares runtime result against ground truth
- [ ]  Unit tests pass
- [ ]  Streamlit demo runs end-to-end

## 31. Implementation Priority

### Phase 1 — Data Layer

```
SQLite schema
Seed CSV / JSON
Database initialization
Validation script
```

### Phase 2 — Scheduling Core

```
service rule lookup
skill matching
certification matching
conflict checking
shift checking
workload calculation
slot search
ranking
assignment
```

### Phase 3 — Request Intake

```
structured request schema
mock intake
Bedrock adapter
readiness gate
```

### Phase 4 — Evaluation

```
cases.csv
request ground truth
assignment ground truth
evaluation scripts
```

### Phase 5 — UI

```
customer request page
coordinator page
technician task page
```

### Phase 6 — Polish

```
error handling
logging
README
tests
demo cases
```

## 32. Important Engineering Rules

1. **Do not use the LLM as the scheduling optimizer.**
2. **Do not allow runtime code to read evaluation ground truth.**
3. **Do not store `assigned_workload_min` as authoritative technician state.**
4. Calculate workload dynamically from active schedules/jobs.
5. Treat `service_rule_id` as the canonical service identifier.
6. Keep the scheduling engine deterministic.
7. Avoid arbitrary weighted scores in Week 1.
8. Use `workload ratio → earliest slot → technician ID` as the ranking sequence.
9. Keep modules loosely coupled and reusable for Week 2 rescheduling.
10. Do not over-engineer the architecture.
11. Avoid unnecessary frameworks.
12. Keep AWS / Bedrock behind an adapter.
13. Ensure local development can work without AWS using mock mode.
14. Preserve clean separation between intake, scheduling, persistence, evaluation, and UI.

## 33. Expected Final Deliverable

After implementation, the repository should support:

```bash
python scripts/reset_db.py
python scripts/validate_seed_data.py
pytest
python evaluation/run_eval.py
streamlit run app.py
```

And demonstrate:

```
Customer message
→ structured request
→ deterministic technician assignment
→ explanation
→ persisted assignment result
→ coordinator display
```

with evaluation completely separated from runtime.

## Codex Instruction

> **Build this project from scratch according to this README. First create the full repository structure, SQLite schema, seed data, deterministic scheduling engine and tests. Keep the implementation simple and production-readable. Do not add features outside the specified Week 1 scope. After implementation, run the validation script and pytest, fix failures, and provide a short summary of the files created and remaining issues.**
>