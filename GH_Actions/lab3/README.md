# Lab 3: Parallel Jobs — Data Pipeline CI

A three-module data pipeline with independent test suites. Your task is to make all three test suites run **at the same time** using parallel GitHub Actions jobs.

---

## 📦 Project Overview

The pipeline processes user records through three independent modules:

| Module | File | What it does |
|---|---|---|
| Validator | `validator.py` | Checks that emails, ages, and usernames are well-formed |
| Transformer | `transformer.py` | Normalizes emails, formats names, assigns age groups |
| Reporter | `reporter.py` | Counts records by age group and generates summary stats |

Each module has its own dedicated test file:

```
lab3/
├── validator.py          # Module 1
├── test_validator.py     # 20 tests
├── transformer.py        # Module 2
├── test_transformer.py   # 22 tests
├── reporter.py           # Module 3 (imports from validator + transformer)
├── test_reporter.py      # 16 tests
├── requirements.txt
└── README.md             ← you are here
```

---

## 🧪 Running Tests Locally

Make sure all tests pass before writing your workflow:

```bash
cd GH_Actions/lab3
pip install -r requirements.txt

# Run each suite individually
pytest test_validator.py -v
pytest test_transformer.py -v
pytest test_reporter.py -v

# Or run all at once
pytest -v
```

---

## 🎯 Your Challenge: Parallel Jobs

### The Problem with Sequential Jobs

Imagine each test suite takes **30 seconds** to run. A workflow with three sequential jobs takes:

```
test-validator  ──30s──►
                         test-transformer  ──30s──►
                                                    test-reporter  ──30s──►
Total: 90 seconds
```

### The Solution: Parallel Jobs

Jobs that do **not** declare a `needs:` dependency run **simultaneously** on separate runners:

```
test-validator  ──30s──►
test-transformer ──30s──►  ← all start at the same time
test-reporter   ──30s──►
Total: ~30 seconds  (3× faster!)
```

---

## 📋 Your Task

### Step 1: Understand the file locations

The workflow file goes in the **repository root**, not inside `lab3/`:

```
Repository Root/
├── .github/
│   └── workflows/
│       └── lab3-parallel.yml   ← create this file
└── GH_Actions/
    └── lab3/
        ├── validator.py
        ├── transformer.py
        └── reporter.py
```

### Step 2: Create `lab3-parallel.yml`

Create `.github/workflows/lab3-parallel.yml` with **three parallel test jobs** — one for each module.

Your workflow must:

1. **Trigger** on push to `main` and on pull requests
2. **Define three jobs** (`test-validator`, `test-transformer`, `test-reporter`)
3. **Run jobs in parallel** — without any `needs:` dependency between them
4. Each job must:
   - Check out the code (`actions/checkout@v5`)
   - Set up Python 3.11
   - Install dependencies from `requirements.txt`
   - Run the correct test file with `pytest`
   - Use `working-directory: './GH_Actions/lab3'`

### Step 3: Add a fan-in summary job

After all three parallel jobs complete, add a **fourth job** called `pipeline-summary` that:
- Uses `needs: [test-validator, test-transformer, test-reporter]`
- Runs even if some tests failed (`if: always()`)
- Prints the result of each parallel job

---

## 💡 Key Concepts

### Parallel by default

```yaml
jobs:
  job-a:         # ← no 'needs' → starts immediately
    runs-on: ubuntu-latest
    ...

  job-b:         # ← no 'needs' → also starts immediately, runs alongside job-a
    runs-on: ubuntu-latest
    ...
```

### Fan-in with `needs`

```yaml
  summary:
    runs-on: ubuntu-latest
    needs: [job-a, job-b]   # waits for BOTH to finish before starting
    if: always()             # runs even if job-a or job-b failed
```

### Checking a job's result

Inside a downstream job you can read the outcome of any job listed in `needs`:

```yaml
    steps:
      - run: echo "job-a result: ${{ needs.job-a.result }}"
```

Possible values: `success`, `failure`, `cancelled`, `skipped`.

---

## ✨ Bonus Challenges

Once your basic parallel workflow is working, try these:

**Bonus 1 — Cross-platform matrix**
Run each test job on three operating systems in parallel:

```yaml
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
    runs-on: ${{ matrix.os }}
```

**Bonus 2 — `fail-fast: false`**
By default, if one matrix job fails, GitHub cancels the rest. Disable this so you always see results for every OS:

```yaml
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
```

**Bonus 3 — Code coverage per module**
Add `--cov=<module_name> --cov-report=term-missing` to each `pytest` call and upload the XML report as an artifact.

**Bonus 4 — Security scan job**
Add a fifth job `security-scan` (using `pip-audit` or `bandit`) that runs **in parallel** with the test jobs (no `needs:`). The `pipeline-summary` job then waits for all four jobs.

**Bonus 5 — Timing comparison**
Add a second workflow file `lab3-sequential.yml` where the three test jobs run in sequence using `needs`. Push both to GitHub, compare the total run times in the Actions tab.

---

## 📊 Expected Workflow Execution

```
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 1 (parallel — all start at the same time)                 │
│                                                                 │
│   [test-validator]   [test-transformer]   [test-reporter]       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ all must finish (needs: [...])
┌──────────────────────────▼──────────────────────────────────────┐
│ STAGE 2                                                         │
│                                                                 │
│                  [pipeline-summary]                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## ✔️ Success Criteria

Your workflow is successful when:

- ✅ All three test jobs appear as **separate boxes** in the GitHub Actions visual graph
- ✅ The three test boxes start **at the same time** (no waiting between them)
- ✅ `pipeline-summary` starts only **after** all three complete
- ✅ All tests pass (green checkmarks)
- ✅ Total runtime is roughly **equal to the slowest single job** — not the sum of all three

---

## 📚 Resources

- [GitHub Actions: Jobs that depend on other jobs](https://docs.github.com/en/actions/using-workflows/advanced-workflow-features#creating-dependent-jobs)
- [GitHub Actions: Using a matrix](https://docs.github.com/en/actions/using-jobs/using-a-matrix-for-your-jobs)
- [GitHub Actions: Context and expression syntax](https://docs.github.com/en/actions/learn-github-actions/contexts)
- [pytest documentation](https://docs.pytest.org/)

Good luck! 🎓
