# Lab 2 Solution Guide

This guide presents **two complete workflow solutions** for Lab 2:

| | Solution | When Lab 1 tests run | When Lab 2 tests run |
|---|---|---|---|
| **1** | Sequential | First | After Lab 1 finishes |
| **2** | Parallel | At the same time as Lab 2 | At the same time as Lab 1 |

The full solution files are in `GH_Actions/solutions/`:
- `lab2-solution.yml` — the parallel solution (bonus features included)

---

## Solution 1 — Sequential Jobs

### How it works

Each job waits for the previous one to finish before starting. The `needs:` keyword creates a chain:

```
lint
 ↓
test-lab1
 ↓
test-lab2
 ↓
summary
```

The total runtime equals the **sum** of all job runtimes.

### The key line

```yaml
test-lab2:
  needs: test-lab1   # ← waits for test-lab1 to finish before starting
```

### Complete workflow

```yaml
name: Lab 2 - Sequential Solution

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:

  # ── STEP 1 ──────────────────────────────────────────────────────────────
  lint:
    name: Lint Code
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v5

      - name: Set up Python 3.11
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'

      - name: Install linting tools
        run: pip install flake8

      - name: Lint Lab 1
        run: flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
        working-directory: './GH_Actions/lab1'
        continue-on-error: true

      - name: Lint Lab 2
        run: flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
        working-directory: './GH_Actions/lab2'
        continue-on-error: true

  # ── STEP 2 ──────────────────────────────────────────────────────────────
  test-lab1:
    name: Test Lab 1 — Calculator
    runs-on: ubuntu-latest
    needs: lint          # waits for lint to succeed

    steps:
      - name: Checkout code
        uses: actions/checkout@v5

      - name: Set up Python 3.11
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pytest pytest-cov
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
        working-directory: './GH_Actions/lab1'

      - name: Run Lab 1 tests
        run: pytest test_calculator.py -v --cov=calculator --cov-report=term-missing
        working-directory: './GH_Actions/lab1'

  # ── STEP 3 ──────────────────────────────────────────────────────────────
  # NOTE: needs: test-lab1 means this job CANNOT start until Lab 1 tests
  # have fully completed. They never run at the same time.
  test-lab2:
    name: Test Lab 2 — String Utils
    runs-on: ubuntu-latest
    needs: test-lab1     # waits for test-lab1 to finish (SEQUENTIAL)

    steps:
      - name: Checkout code
        uses: actions/checkout@v5

      - name: Set up Python 3.11
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pytest pytest-cov
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
        working-directory: './GH_Actions/lab2'

      - name: Run Lab 2 tests
        run: pytest test_string_utils.py -v --cov=string_utils --cov-report=term-missing
        working-directory: './GH_Actions/lab2'

  # ── STEP 4 ──────────────────────────────────────────────────────────────
  summary:
    name: Test Summary
    runs-on: ubuntu-latest
    # List all jobs so their results are available via needs.<job>.result
    needs: [lint, test-lab1, test-lab2]
    if: always()         # run even if a previous job failed

    steps:
      - name: Print results
        run: |
          echo "=================================="
          echo "Sequential Workflow Results"
          echo "=================================="
          echo "Lint   : ${{ needs.lint.result }}"
          echo "Lab 1  : ${{ needs.test-lab1.result }}"
          echo "Lab 2  : ${{ needs.test-lab2.result }}"
          echo "=================================="
```

### Timeline

```
Time →  0s          30s         60s         90s
        ┌──────────┐
lint    │  ~10s    │
        └──────────┘
                   ┌──────────┐
test-lab1          │  ~30s    │
                   └──────────┘
                               ┌──────────┐
test-lab2                      │  ~30s    │
                               └──────────┘
                                           ┌──┐
summary                                    │  │
                                           └──┘
Total: ~70s
```

---

## Solution 2 — Parallel Jobs

### How it works

Both test jobs declare `needs: lint` (not `needs: test-lab1`). Because they share the same dependency, GitHub starts them on **separate runners at the same time** as soon as `lint` completes.

```
lint
 ↓         ↓
test-lab1  test-lab2   ← run simultaneously on two separate runners
     ↓         ↓
      summary (fan-in)
```

The total runtime equals the runtime of `lint` + the **slower** of the two test jobs — not the sum.

### The key difference from Solution 1

```yaml
# Solution 1 — sequential
test-lab2:
  needs: test-lab1     # waits for Lab 1 tests

# Solution 2 — parallel
test-lab2:
  needs: lint          # only waits for lint, starts alongside test-lab1
```

### Complete workflow

```yaml
name: Lab 2 - Parallel Solution

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:

  # ── STAGE 1 ─────────────────────────────────────────────────────────────
  lint:
    name: Lint Code
    runs-on: ubuntu-latest
    steps:
      - name: Checkout code
        uses: actions/checkout@v5

      - name: Set up Python 3.11
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'

      - name: Install linting tools
        run: pip install flake8

      - name: Lint Lab 1
        run: flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
        working-directory: './GH_Actions/lab1'
        continue-on-error: true

      - name: Lint Lab 2
        run: flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics
        working-directory: './GH_Actions/lab2'
        continue-on-error: true

  # ── STAGE 2 (both jobs start simultaneously) ─────────────────────────────
  test-lab1:
    name: Test Lab 1 — Calculator
    runs-on: ubuntu-latest
    needs: lint          # waits only for lint

    steps:
      - name: Checkout code
        uses: actions/checkout@v5

      - name: Set up Python 3.11
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pytest pytest-cov
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
        working-directory: './GH_Actions/lab1'

      - name: Run Lab 1 tests
        run: pytest test_calculator.py -v --cov=calculator --cov-report=term-missing
        working-directory: './GH_Actions/lab1'

      - name: Upload Lab 1 coverage report
        uses: actions/upload-artifact@v4
        with:
          name: lab1-coverage
          path: ./GH_Actions/lab1/coverage.xml

  # NOTE: needs: lint — NOT needs: test-lab1
  # This is the only change from Solution 1. Both test jobs now share
  # the same upstream dependency (lint), so GitHub runs them in parallel.
  test-lab2:
    name: Test Lab 2 — String Utils
    runs-on: ubuntu-latest
    needs: lint          # waits only for lint → runs alongside test-lab1

    steps:
      - name: Checkout code
        uses: actions/checkout@v5

      - name: Set up Python 3.11
        uses: actions/setup-python@v6
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pytest pytest-cov
          if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
        working-directory: './GH_Actions/lab2'

      - name: Run Lab 2 tests
        run: pytest test_string_utils.py -v --cov=string_utils --cov-report=term-missing
        working-directory: './GH_Actions/lab2'

      - name: Upload Lab 2 coverage report
        uses: actions/upload-artifact@v4
        with:
          name: lab2-coverage
          path: ./GH_Actions/lab2/coverage.xml

  # ── STAGE 3 (fan-in — waits for BOTH parallel jobs) ─────────────────────
  summary:
    name: Test Summary
    runs-on: ubuntu-latest
    needs: [test-lab1, test-lab2]   # waits for both to finish
    if: always()

    steps:
      - name: Print results
        run: |
          echo "=================================="
          echo "Parallel Workflow Results"
          echo "=================================="
          echo "Lab 1  : ${{ needs.test-lab1.result }}"
          echo "Lab 2  : ${{ needs.test-lab2.result }}"
          echo "=================================="
```

### Timeline

```
Time →  0s          30s         60s
        ┌──────────┐
lint    │  ~10s    │
        └──────────┘
                   ┌──────────┐
test-lab1          │  ~30s    │    ← both start at the same moment
test-lab2          │  ~30s    │    ← running on separate runners
                   └──────────┘
                               ┌──┐
summary                        │  │
                               └──┘
Total: ~40s  (compared to ~70s sequential — 43% faster)
```

---

## Side-by-Side Comparison

| | Sequential | Parallel |
|---|---|---|
| `test-lab2` depends on | `test-lab1` | `lint` |
| Jobs run at the same time | No | Yes (test-lab1 + test-lab2) |
| Total time | Sum of all job times | Lint + slowest test job |
| Runner cost | Same (jobs still run) | Same (same total compute) |
| When to use sequential | Job B needs output from Job A | Jobs are independent |
| Fan-in job (`summary`) `needs:` | `[lint, test-lab1, test-lab2]` | `[test-lab1, test-lab2]` |

---

## 🎓 Key Concepts Explained

### 1. `needs:` controls order, not just dependencies

`needs:` is the only mechanism for sequencing jobs. Without it, all jobs start at the same time. With it, a job waits until every job in its `needs:` list reaches a terminal state.

### 2. Fan-in pattern

When the `summary` job lists multiple jobs in `needs: [test-lab1, test-lab2]`, it waits for **all** of them. This is called a fan-in — multiple parallel branches converging into one job.

### 3. `if: always()`

By default, if a `needs` dependency fails, downstream jobs are **skipped** — not failed. `if: always()` overrides this so the summary job runs regardless of upstream outcomes.

```yaml
summary:
  needs: [test-lab1, test-lab2]
  if: always()   # run even if test-lab1 or test-lab2 failed
```

### 4. Reading job results

Inside a downstream job, you can read any listed dependency's result:

```yaml
echo "Lab 1: ${{ needs.test-lab1.result }}"
```

Possible values: `success` | `failure` | `cancelled` | `skipped`.

### 5. Matrix Strategy (Bonus)

```yaml
strategy:
  matrix:
    python-version: ['3.9', '3.10', '3.11']
```

This creates 3 runners per job automatically — one for each Python version. It's a second layer of parallelism, independent from job-level parallelism.

### 6. Working Directory

```yaml
working-directory: './GH_Actions/lab2'
```

All `run:` commands in that step execute from the lab2 folder.

---

## 🎯 Grading Rubric (Optional)

| Requirement | Points |
|---|---|
| Workflow runs on push | 10 |
| Uses Ubuntu | 5 |
| Sets up Python | 10 |
| Installs dependencies | 10 |
| Runs tests successfully | 15 |
| **Bonus: Sequential multi-job workflow** | +10 |
| **Bonus: Parallel multi-job workflow** | +15 |
| **Bonus: Summary/fan-in job** | +10 |
| **Bonus: Multiple Python versions (matrix)** | +10 |
| **Bonus: Code coverage** | +10 |
| **Bonus: Push + PR triggers** | +5 |
| **Bonus: Linting** | +10 |
| **Total** | 50 (+70 bonus) |

---

## 🔗 Additional Resources

- [GitHub Actions — Creating dependent jobs](https://docs.github.com/en/actions/using-workflows/advanced-workflow-features#creating-dependent-jobs)
- [GitHub Actions — Matrix builds](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs)
- [GitHub Actions — needs context](https://docs.github.com/en/actions/learn-github-actions/contexts#needs-context)
- [pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [Flake8 Documentation](https://flake8.pycqa.org/)
