# Lab 3 Solution Guide — Parallel Jobs

This document walks through the complete solution, explains every design decision, and provides a grading rubric.

The complete workflow is in: `GH_Actions/solutions/lab3-solution.yml`

Copy it to `.github/workflows/lab3-parallel.yml` to activate it.

---

## 🎯 What the Solution Includes

### Core Requirements

- ✅ Three parallel test jobs (`test-validator`, `test-transformer`, `test-reporter`)
- ✅ No `needs:` between the three test jobs (they start simultaneously)
- ✅ Fan-in `pipeline-summary` job using `needs: [test-validator, test-transformer, test-reporter]`
- ✅ `if: always()` on the summary job so it always runs
- ✅ Trigger on `push` and `pull_request` to `main`

### Bonus Features

1. ✅ **Cross-platform matrix** — each test job runs on ubuntu, macos, and windows in parallel
2. ✅ **`fail-fast: false`** — all matrix legs run to completion even if one fails
3. ✅ **Code coverage per module** — `--cov=<module>` + XML upload as artifact
4. ✅ **Concurrent security scan** — `pip-audit` runs alongside the test jobs

---

## 🔍 Solution Breakdown

### Stage 1: Parallel Jobs

```
Trigger (push/PR)
       │
       ├──► test-validator    (runner A)
       ├──► test-transformer  (runner B)   ← all start at the same moment
       ├──► test-reporter     (runner C)
       └──► security-scan     (runner D)
```

The key insight: **GitHub starts every job that has no unmet `needs:` dependency at the same time.** Since none of the four stage-1 jobs declare a `needs:`, all four are queued simultaneously.

```yaml
# No 'needs:' here → starts in parallel with every other no-needs job
test-validator:
  name: Test Validator
  runs-on: ubuntu-latest
  steps: ...
```

### Stage 2: Fan-In

```yaml
pipeline-summary:
  needs: [test-validator, test-transformer, test-reporter, security-scan]
  if: always()    # run even when a parallel job failed
```

`needs` accepts a list — the summary job waits until **every** listed job reaches a terminal state (`success`, `failure`, `cancelled`, or `skipped`).

### Reading job results

```yaml
- run: echo "Validator: ${{ needs.test-validator.result }}"
```

`needs.<job-id>.result` is one of: `success` | `failure` | `cancelled` | `skipped`.

### Failing the summary job when a test job failed

```yaml
- name: Fail if any test job failed
  if: |
    needs.test-validator.result   != 'success' ||
    needs.test-transformer.result != 'success' ||
    needs.test-reporter.result    != 'success'
  run: exit 1
```

Without this step, the summary job would show green even when a parallel job failed.

---

## 📊 Execution Graph

```
push / pull_request
        │
┌───────┴──────────────────────────────────────────────────┐
│  STAGE 1 — all jobs start simultaneously                 │
│                                                          │
│  [test-validator]  [test-transformer]  [test-reporter]   │
│        (3 OS)           (3 OS)              (3 OS)       │
│                                                          │
│                  [security-scan]                         │
└───────────────────────┬──────────────────────────────────┘
          needs: [...] ─┘  (waits for all 4 jobs above)
┌───────────────────────▼──────────────────────────────────┐
│  STAGE 2                                                 │
│                [pipeline-summary]                        │
└──────────────────────────────────────────────────────────┘

Without matrix: 2 stages, 5 jobs total
With matrix   : 2 stages, 10 jobs total (3×3 test + 1 scan + 1 summary)
```

---

## 🚀 Minimal Passing Solution

If a student only completes the core requirements (no matrix, no security scan):

```yaml
name: Lab 3 - Parallel Jobs

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test-validator:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
        working-directory: './GH_Actions/lab3'
      - name: Run validator tests
        run: pytest test_validator.py -v
        working-directory: './GH_Actions/lab3'

  test-transformer:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
        working-directory: './GH_Actions/lab3'
      - name: Run transformer tests
        run: pytest test_transformer.py -v
        working-directory: './GH_Actions/lab3'

  test-reporter:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v5
      - uses: actions/setup-python@v6
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
        working-directory: './GH_Actions/lab3'
      - name: Run reporter tests
        run: pytest test_reporter.py -v
        working-directory: './GH_Actions/lab3'

  pipeline-summary:
    runs-on: ubuntu-latest
    needs: [test-validator, test-transformer, test-reporter]
    if: always()
    steps:
      - name: Report status
        run: |
          echo "Validator  : ${{ needs.test-validator.result }}"
          echo "Transformer: ${{ needs.test-transformer.result }}"
          echo "Reporter   : ${{ needs.test-reporter.result }}"
```

---

## 🎓 Key Concepts Taught

### 1. Default Parallel Execution

Jobs with no `needs:` run in parallel automatically. Students often assume jobs always run sequentially; this lab corrects that misconception.

### 2. `needs:` Controls Order, Not Just Dependencies

`needs` is not just about data sharing — it's the primary mechanism for sequencing jobs. No `needs` = parallel. `needs` = sequential (relative to the listed jobs).

### 3. Fan-Out / Fan-In Pattern

- **Fan-out**: one trigger → multiple parallel jobs
- **Fan-in**: multiple parallel jobs → one aggregating job

This pattern is fundamental to efficient CI pipelines.

### 4. `if: always()` vs Default Behavior

By default, if a `needs` dependency fails, downstream jobs are **skipped** (not failed). `if: always()` overrides this so the summary job runs regardless.

### 5. Matrix as Parallelism Within a Job

The bonus cross-platform matrix creates 3 runners per job (ubuntu, macos, windows), all running in parallel. This is a different level of parallelism from having separate jobs — both can be combined.

### 6. `fail-fast: false`

Without `fail-fast: false`, a failure on `ubuntu-latest` would cancel `macos-latest` and `windows-latest` before they finish. Setting it to `false` lets you see results from all platforms, which is often more useful for debugging cross-platform issues.

---

## 🧪 Common Student Mistakes

| Mistake | Symptom | Fix |
|---|---|---|
| Adding `needs: [test-validator]` to `test-transformer` | Jobs run sequentially, not in parallel | Remove the unnecessary `needs` |
| Forgetting `if: always()` on the summary job | Summary is skipped when a test fails | Add `if: always()` |
| Wrong `working-directory` | `ModuleNotFoundError` or "file not found" | Use `'./GH_Actions/lab3'` |
| Missing `--cov=<module>` (just `--cov`) | Coverage includes all modules in one report | Specify the correct module name |
| Exiting on security scan failure | Workflow fails even when tests pass | Add `continue-on-error: true` to the scan step |

---

## 🎯 Grading Rubric

| Requirement | Points |
|---|---|
| Workflow triggers on push and PR | 5 |
| Three separate test jobs defined | 15 |
| All three jobs run in parallel (no ordering between them) | 20 |
| All tests pass | 10 |
| `pipeline-summary` job uses `needs: [...]` correctly | 15 |
| `pipeline-summary` runs even on failure (`if: always()`) | 10 |
| Summary prints status of each parallel job | 5 |
| **Bonus: Cross-platform matrix (3 OSes)** | +10 |
| **Bonus: `fail-fast: false`** | +5 |
| **Bonus: Code coverage upload per module** | +10 |
| **Bonus: Concurrent security scan job** | +10 |
| **Bonus: Sequential comparison workflow** | +5 |
| **Total** | 80 (+40 bonus) |

---

## 🔗 Additional Resources

- [GitHub Docs — Creating dependent jobs](https://docs.github.com/en/actions/using-workflows/advanced-workflow-features#creating-dependent-jobs)
- [GitHub Docs — Using a matrix for your jobs](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs)
- [GitHub Docs — Context: needs](https://docs.github.com/en/actions/learn-github-actions/contexts#needs-context)
- [pip-audit](https://pypi.org/project/pip-audit/)
- [pytest-cov](https://pytest-cov.readthedocs.io/)
