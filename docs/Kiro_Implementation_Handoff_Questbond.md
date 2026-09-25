# Questbond / Mendigo — Kiro Implementation Handoff

## 0. Purpose and frozen boundaries

This handoff is for **incremental implementation** on the current GitHub `main` codebase. Do not redesign the project.

**Product:** Technician Scheduling Agent.

**Keep the existing two-Agent architecture:**
- `customer_intake_agent`
- `scheduling_operations_agent`

Do **not** create a third Rescheduling Agent.

**Responsibility split**
- LLM Agent: understand events, retrieve context, choose tools, orchestrate, explain, escalate.
- Deterministic Python: eligibility, feasibility, ranking, conflict detection, recovery proposal, governance policy.
- Human Coordinator: final authority for changes to already confirmed operational commitments.

**Booking boundary**
- New, unconfirmed booking: a deterministically validated slot may be self-confirmed by the customer.
- Existing confirmed booking: any change to technician, start, end, or cancellation requires deterministic policy evaluation and Coordinator approval before schedule mutation.

**Disruption scope for this implementation**
- `UNAVAILABLE`
- `DELAYED`

Keep the MVP to **one active disruption recovery case at a time**. Do not add multi-event optimization.

**Current multimodal policy**
- text only → normal text intake
- photo only → visual assessment runs
- text + photo → written description is authoritative; visual model is skipped; photo metadata/checksum is stored

Do not add image-text fusion/conflict reasoning unless explicitly approved later.

---

# 1. Current-repo compatibility facts

Inspect these first; do not scan/rewrite unrelated modules:

```text
src/agents/scheduling_operations_agent.py
src/orchestration/orchestrator.py
src/orchestration/state_machine.py
src/tools/registry.py
src/tools/executor.py
src/tools/scheduling_tools.py
src/services/disruption_service.py
src/services/booking_service.py
src/services/request_service.py
src/services/photo_service.py
src/ui/technician_view.py
src/ui/coordinator_view.py
src/ui/customer_view.py
src/database.py
tests/test_disruption_recovery.py
tests/test_orchestration.py
tests/test_tools.py
docs/TEST_MATRIX.md
```

Important current facts:
1. `disruption_service.py` is sick-leave-specific and currently uses `SICK_LEAVE`.
2. The current recovery service is deterministic and already supports affected-job discovery, replacement search, proposal creation, stale revalidation, approval, schedule mutation and notification drafts.
3. Recovery is currently called directly from the Coordinator prototype, not through the Agent tool registry.
4. The current Agent tool registry contains intake/initial-assignment tools only.
5. `agent_sessions` is request-centric (`request_id` is required), while one technician disruption may affect jobs from multiple requests.
6. `ToolExecutor` enforces request/session ownership. Do not weaken these checks.
7. Current `approve_plan(...)` can apply resolvable actions even if another action is `UNRESOLVED`; the target policy forbids partial auto-apply.
8. Coordinator UI already has a sick-leave recovery prototype with Before/Proposed, metrics, approval and notification drafts. Upgrade it in place.
9. Customer self-confirm is already implemented for a verified alternative slot after no-feasible scheduling; normal initial recommendation may still use Coordinator confirmation.
10. Photo-only visual assessment exists; text+photo currently skips visual inference.

---

# 2. Target disruption model

## 2.1 UNAVAILABLE

Generalize the existing sick-leave flow:

```text
event
→ affected confirmed jobs
→ deterministic replacement search
→ preserve original appointment time if feasible
→ otherwise earliest feasible slot inside customer window
→ UNRESOLVED if no valid recovery exists
```

Use:
- `event_type = UNAVAILABLE`
- keep sick leave / emergency leave / other absence as `reason`

Avoid a database redesign merely to rename fields.

## 2.2 DELAYED

Technician-facing input:

```text
effective_from
delay_minutes
reason
```

Prefer compatibility with the current interval schema:

```text
unavailable_from = effective_from
unavailable_until = effective_from + delay_minutes
event_type = DELAYED
```

Recovery principle:

> Only jobs whose feasibility is actually broken should be reconsidered.

Do not regenerate the technician's whole day unnecessarily.

Existing hard constraints still apply:
- skill
- certification
- technician status
- shift
- company hours
- customer window
- no overlap
- workload capacity
- 30-minute granularity
- deterministic ranking/tie-break

---

# 3. Scheduling Operations Agent integration

The existing Scheduling Operations Agent should support two logical task modes:

```text
INITIAL_ASSIGNMENT
DISRUPTION_RECOVERY
```

Prefer separate internal paths such as:

```python
run_initial_assignment(...)
run_disruption_recovery(...)
```

Do not create a third Agent.

## Tool capabilities

The Scheduling Operations Agent needs the following **logical capabilities**:

```text
read disruption context
identify affected jobs
create deterministic recovery proposal
validate proposal
read decision evidence / trace
```

Do **not** force five separate tools if the same auditable behavior can be exposed with fewer wrappers. Use the smallest clear tool surface.

Never expose these as LLM tools:

```text
approve
reject
apply schedule mutation
```

## Request-centric session issue

Before implementation, Kiro must propose how event-scoped Agent sessions work without weakening current request security.

Preferred minimal-change direction:
- keep existing `agent_sessions` / `agent_tool_calls`;
- keep `reschedule_plans` / `reschedule_actions` as recovery business truth;
- if necessary, add a small additive mapping such as:

```text
disruption_sessions(session_id, event_id)
```

- scope disruption tools to the mapped event;
- do not make current request ownership checks globally weaker.

If a disruption has zero affected jobs, it may be recorded/closed deterministically without creating an unnecessary LLM session.

---

# 4. Governance and reschedule proposal contract

For every affected job expose:

```text
job_id
before_technician
before_start
before_end
after_technician
after_start
after_end
action_type
reason
technician_changed
time_changed
customer_appointment_changed
requires_human_approval
approval_reasons
```

Suggested actions:

```text
UNCHANGED
REASSIGN_SAME_TIME
REASSIGN_AND_RESCHEDULE
SHIFT_SAME_TECHNICIAN
UNRESOLVED
```

Deterministic approval rule:

```python
requires_human_approval = (
    booking_status == "CONFIRMED"
    and (
        technician_changed
        or start_changed
        or end_changed
        or booking_cancelled
    )
)
```

Return explicit reasons, e.g.:

```json
{
  "requires_human_approval": true,
  "approval_reasons": ["CONFIRMED_TECHNICIAN_CHANGED"]
}
```

**Frozen unresolved policy**

> If any affected job is `UNRESOLVED`, do not partially auto-apply the recovery plan. Route the whole plan to Human Review.

Proposal generation must not mutate `schedules`.

---

# 5. Technician UI — minimum change

Preserve the existing technician schedule view.

Add one `Report disruption` area with exactly two types.

## UNAVAILABLE

Fields:

```text
unavailable_from
unavailable_until
reason
```

Validate:
- start < end
- selected technician owns the event
- idempotent/rerender-safe submission

## DELAYED

Fields:

```text
effective_from
delay_minutes
reason
```

Demo values may be limited to:

```text
30 / 60 / 90 / 120
```

Technician must **not**:
- choose replacements
- approve/reject
- mutate confirmed schedules

Flow:

```text
Technician report
→ operational event
→ DISRUPTION_RECOVERY
→ Scheduling Operations Agent
→ deterministic recovery
→ saved proposal
→ Coordinator review
```

---

# 6. Coordinator UI — upgrade the existing prototype, do not rebuild

Reuse `src/ui/coordinator_view.py` and the current sick-leave recovery prototype.

Preserve:
- request queue/detail
- candidate evaluation
- tool-call trace / handoffs / usage
- recovery summary metrics
- current Before/Proposed table
- current `approve_plan(...)`
- notification drafts

Rename/generalize the business-facing section to:

```text
Recovery Plans
```

Support:
- `UNAVAILABLE`
- `DELAYED`

Keep the current seed button only as an explicitly labelled **Demo / Developer Tool**.

## Extend the existing recovery table

Add only the governance fields needed:

```text
Job
Service
Priority
Before
Proposed After
Action
Reason
Technician changed?
Time changed?
Customer appointment changed?
Approval required?
Approval reasons
```

## Actions

Add:

```text
Approve
Reject
Recalculate
```

### Approve
- revalidate against current DB state;
- fail safely if stale;
- apply only after valid approval;
- record approval;
- generate draft customer notice when needed.

### Reject
- record `REJECTED`;
- optional short reason;
- modify **zero** schedule rows.

### Recalculate
Use when the proposal is stale or operational state changed.

The UI displays approval policy output; it does not decide policy itself.

If there are no changes to confirmed bookings, show an audit result such as:

```text
Resolved automatically
No Coordinator approval required
```

Reuse existing Agent/tool trace presentation for disruption recovery.

---

# 7. Multimodal intake tests

The current product is **photo-assisted intake**, not full image-text fusion.

## Functional quality

Test:
1. photo only
2. text only regression
3. text + photo current-policy regression
4. image validation/safety boundaries
5. privacy/storage invariant
6. mock-vs-live separation

### Photo-only quality metrics
Use a labelled held-out image set only for service rules that are visually defensible.

Report:
- exact service-rule accuracy where justified
- category accuracy
- review/abstention rate
- unsupported-to-supported false-routing count

Do not require exact photo-only classification for intent classes that cannot be visually distinguished reliably.

### Text + photo regression
Verify:
- text drives intake;
- visual inference is skipped;
- photo metadata/checksum is stored;
- raw image bytes are not persisted;
- scheduling follows the written request.

### Boundary cases
Test:
- JPEG / PNG / WebP
- unsupported type
- empty file
- corrupt image
- >5 MB
- uncertain photo
- hazard-like photo where supported by policy

Mock tests are **not** visual-model accuracy.

Before any live visual evaluation, stop and report:
- image count
- backend/model
- estimated number of calls
- output path

Run only after explicit approval.

---

# 8. Test architecture

## A. Deterministic domain

UNAVAILABLE:
- no affected jobs
- same-time replacement
- shifted replacement
- no feasible replacement
- skill/cert/status/conflict/workload exclusions
- deterministic ranking
- stale proposal

DELAYED:
- small delay affects no job
- near downstream job affected
- later feasible job unchanged
- same-tech shift when feasible
- replacement when necessary
- no feasible recovery
- customer-window violation
- workload enforced
- repeatability

## B. Tool/security
Verify:
- Intake Agent cannot call disruption tools
- Scheduling Agent can call allowed disruption tools
- no Agent can approve/reject/apply
- invalid event IDs fail safely
- extra args rejected
- scope escape rejected
- errors audited

## C. Multi-Agent orchestration
Verify:
- normal request: Intake → Scheduling
- incomplete request remains with Intake
- UNAVAILABLE/DELAYED route to Scheduling Operations Agent
- confirmed-booking change routes to human approval
- unresolved recovery routes to human review
- disruption does not unnecessarily call Intake

## D. Human authority
Verify:
- proposal creation does not mutate schedules
- approve changes only intended rows
- reject changes zero rows
- stale approval fails
- repeated approval is idempotent
- unresolved plan cannot partially auto-apply

## E. Live-model evaluation
Separate from offline pytest.

Measure:
- tool sequence
- handoff correctness
- unauthorized attempts
- grounded explanation
- completion/failure
- latency
- tokens
- provider-reported cost when available

---

# 9. Judge-facing repeatable demos

Prepare stable fixtures for:

1. **Normal booking**
   - Intake → Scheduling → validated recommendation → confirmation → Technician schedule

2. **Clarification**
   - missing field → no guessing → same session → schedule only when ready

3. **Photo-only intake**
   - blank text + clear image → visual assessment → canonical service rule → normal scheduling

4. **UNAVAILABLE**
   - confirmed jobs → disruption → Before/After → Human Review/approval

5. **DELAYED**
   - near downstream job becomes infeasible, later job remains feasible
   - prove minimum-change recovery

6. **UNRESOLVED**
   - no valid recovery
   - no partial auto-apply

All demos must be synthetic/repeatable and must not require manually editing SQLite.

---

# 10. Mandatory Kiro stop-gates

Use this instruction at the start of every Kiro task:

```text
Work only on the current checkpoint.
Do not start later checkpoints.

When the current checkpoint is complete:
1. run the requested tests;
2. summarize changed files and behavior;
3. give me the exact verification commands;
4. STOP and wait for my explicit approval.

Do not interpret test success as permission to continue automatically.
```

## Checkpoint 0 — baseline only

Kiro: inspect; no feature edits.

User runs:

```powershell
cd C:\Users\DELL\Desktop\hackathon_questbond
git status
git branch --show-current
$env:LLM_BACKEND="mock"
python -m pytest tests -q
```

Check:
- correct branch
- no unexpected local changes
- baseline failures recorded before edits

**STOP.**

## Checkpoint 1 — deterministic disruption backend

Kiro implements only:
- generic UNAVAILABLE
- DELAYED normalization/recovery
- one-disruption-at-a-time rule
- no-partial-apply guard
- reject service path
- stale/recalculate service behavior as needed
- deterministic approval-policy output
- unit tests

No UI or Agent integration yet.

User runs:

```powershell
cd C:\Users\DELL\Desktop\hackathon_questbond
$env:LLM_BACKEND="mock"
python -m pytest tests/test_disruption_recovery.py -q
python -m pytest tests -k "disruption or unavailable or delayed or reschedule" -q
git diff --stat
git diff -- src/services/disruption_service.py src/database.py
```

Check:
- old sick-leave case still works as UNAVAILABLE
- DELAYED changes only truly affected downstream work
- proposal creation does not mutate schedule
- UNRESOLVED blocks partial apply
- reject = zero schedule mutation
- stale approval fails before mutation
- no unnecessary DB redesign

**STOP.**

## Checkpoint 2A — Agent integration design review only

Kiro inspects:
- `agent_sessions`
- `agent_tool_calls`
- `ToolExecutor`
- `AgentOrchestrator`
- `SchedulingOperationsAgent`
- `operational_events`
- `reschedule_plans`

No coding.

Kiro must report:
1. how disruption gets an Agent session despite request-centric sessions;
2. how event scope is enforced without weakening request security;
3. whether a small event-session mapping is needed;
4. exact new tools and why;
5. exact schema changes;
6. how multi-job/multi-customer recovery remains represented.

Approve only if the design:
- avoids broad rewrite of `agent_sessions`;
- preserves ToolExecutor protections;
- keeps recovery state in existing disruption tables;
- uses minimal new tools/tables.

**STOP.**

## Checkpoint 2 — Agent integration

Kiro implements the approved 2A design only.

User runs:

```powershell
cd C:\Users\DELL\Desktop\hackathon_questbond
$env:LLM_BACKEND="mock"
python -m pytest tests/test_orchestration.py tests/test_tools.py -q
python -m pytest tests -k "disruption and (agent or orchestration or tool)" -q
python -c "from src.tools import build_registry; print('\n'.join(sorted(build_registry().keys())))"
```

Check:
- disruption routes to `scheduling_operations_agent`
- no unnecessary Intake invocation
- disruption tool trace exists
- registry contains no human approval/apply tool
- normal Week 1 flow still passes

**STOP.**

## Checkpoint 3 — Technician UI

Kiro changes only Technician reporting UI.

User runs:

```powershell
cd C:\Users\DELL\Desktop\hackathon_questbond
$env:LLM_BACKEND="mock"
python -m streamlit run app.py
```

Browser checks:
- existing schedule still visible
- UNAVAILABLE submits once
- DELAYED submits once
- no replacement chooser
- no approval controls
- saved proposal is created

Then:

```powershell
$env:LLM_BACKEND="mock"
python -m pytest tests -k "technician or disruption" -q
```

**STOP.**

## Checkpoint 4 — Coordinator Recovery Plans UI

Kiro upgrades the existing prototype only.

Browser checks:
- correct event summary
- Before + Proposed After
- impact flags visible
- backend policy drives approval requirement
- Reject preserves schedule
- Approve revalidates
- stale proposal cannot be approved
- unresolved plan cannot partially apply
- customer notice remains draft

Terminal:

```powershell
$env:LLM_BACKEND="mock"
python -m pytest tests -k "coordinator or disruption or approval or reschedule" -q
python -m pytest tests -q
```

**STOP.**

## Checkpoint 5 — multimodal evaluation harness

Kiro adds tests/evaluation only; no modality redesign.

User runs:

```powershell
$env:LLM_BACKEND="mock"
python -m pytest tests -k "photo or multimodal or intake" -q
```

Check:
- photo-only
- text-only regression
- text+photo current policy
- validation boundaries
- raw bytes not persisted
- no mock-as-accuracy claim

Live evaluation requires separate explicit approval.

**STOP.**

## Checkpoint 6 — full regression + demos

User runs:

```powershell
$env:LLM_BACKEND="mock"
python -m pytest tests -q
python evaluation/run_eval.py
```

Then manually run:
- normal booking
- clarification
- photo-only intake
- UNAVAILABLE
- DELAYED
- UNRESOLVED

Check:
- repeatable reset
- displayed explanation matches stored evidence
- no manual SQLite editing
- no mock result presented as live-model accuracy

**STOP.**

## Checkpoint 7 — remaining original scope

Only after 0–6 pass, ask which to implement next:

```text
A. fixed travel-time buffer
B. Technician COMPLETED + Customer Yes/No CLOSED/REOPENED
C. basic event-history view
D. AWS deployed smoke test + local fallback
E. final diagrams / measured eval summary / fallback media
```

Do not start these automatically.

---

# 11. Kiro working rule

For every checkpoint:

```text
Do not redesign the project.
Inspect and reuse current implementation.
Make the minimum changes needed.
Do not modify unrelated Week 1 behavior.
Do not create a third Agent.
Keep scheduling/recovery truth deterministic.
Keep approve/reject/apply outside LLM tools.
Run relevant tests before and after.
Report changed files, tests run, and unresolved assumptions.
STOP after this checkpoint.
```
