# Questbond / Mendigo — System Benchmark

A separate, repeatable quantitative evaluation framework for the whole system. It
is independent of the product runtime and of the existing `evaluation/run_eval.py`
regression, and independent of the multimodal visual-quality track.

## What it answers

1. Correct understanding/structuring of customer requests.
2. Feasible and reproducible deterministic scheduling.
3. Disruption recovery: right affected jobs, minimum unnecessary change.
4. HITL/governance prevents unauthorized or premature schedule mutation.
5. Correct Agent orchestration and handoffs.
6. Safe failure under adversarial/edge conditions.

## Layout

```
evaluation/system_benchmark/
├─ run.py            # CLI entry: --mode validate|offline|live
├─ config.py         # paths, results dir, fixed calendar, suite targets
├─ loaders.py        # load fixtures/cases/GT into an isolated in-memory DB
├─ metrics.py        # (B2) pure metric functions
├─ reporters.py      # (B2) result CSV / summary JSON / report writers
├─ fixtures/base/    # versioned synthetic operational world
├─ cases.csv         # unified case registry (120 offline cases)
├─ ground_truth/     # modular per-suite GT (robustness inlined in cases.csv)
├─ suites/           # (B2/B4) per-suite runners
└─ live_subset.csv   # (B3) 40–50 representative cases for the live run
```

Result artifacts are written to `results/system_benchmark/` and never overwrite
other evaluation outputs.

## Case distribution (120 offline)

| Suite | Cases |
|---|---:|
| request | 20 |
| scheduling | 25 |
| disruption | 30 (UNAVAILABLE 15 + DELAYED 15) |
| governance | 15 |
| agent | 15 |
| robustness | 15 |

## Commands

```powershell
conda activate hackathon

# Checkpoint B1 — validate registry / GT / fixtures (no scoring):
python -m evaluation.system_benchmark.run --mode validate

# Checkpoint B2 — deterministic offline benchmark (mock backend):
$env:LLM_BACKEND="mock"
python -m evaluation.system_benchmark.run --mode offline

# Checkpoint B4 — live Agent subset (paid; explicit approval required):
python -m evaluation.system_benchmark.run --mode live
```

## Non-negotiable principles

- Ground truth is loaded only for comparison; it is never read by runtime decision logic.
- No random ground truth; all fixtures and GT are versioned files.
- Offline/mock results are never reported as live Agent quality.
- Deterministic scheduling metrics are not credited to the LLM.
- Live cost uses provider-reported values; missing cost stays missing (not zero).
- Every metric is reproducible from saved per-case result files and traceable to case IDs.
- Multimodal visual accuracy is a separate evaluation track (`evaluation/evaluate_photo_quality.py`).
