# Lab 1 Solution Guide

This document walks through the provided GitHub Actions workflow and explains every concept it introduces.

## 📁 Solution File

The workflow is already active at: `.github/workflows/python-tests.yml`

No action needed — it runs automatically when you push to `main` or open a pull request.

## 🔍 Full Workflow Walkthrough

```yaml
name: Python Tests - Lab 1

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    runs-on: ubuntu-latest

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

    - name: Run tests
      run: |
        python -m unittest test_calculator.py -v
      working-directory: './GH_Actions/lab1'
```

### Section by section

#### `name:`

```yaml
name: Python Tests - Lab 1
```

The display name shown in the **Actions** tab on GitHub. Keep it short and descriptive.

---

#### `on:` — Triggers

```yaml
on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
```

Defines **when** the workflow runs. This one runs in two situations:

| Event | When |
|-------|------|
| `push` to `main` | Every time you push a commit directly to `main` |
| `pull_request` to `main` | Every time a PR is opened, updated, or re-opened targeting `main` |

**Why both?** Push catches direct commits; pull_request lets you check that a branch passes tests *before* merging.

---

#### `jobs:` — Units of work

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
```

A workflow contains one or more **jobs**. Each job runs on its own virtual machine. `ubuntu-latest` gives you a fresh Ubuntu Linux environment every time.

`test` is the job ID — you can name it anything (no spaces, use hyphens).

---

#### `steps:` — The individual actions

Each job has a list of steps that run **in order**, top to bottom.

---

**Step 1: Checkout**

```yaml
- name: Checkout code
  uses: actions/checkout@v5
```

`uses` means "run a pre-built action from the GitHub Actions marketplace". `actions/checkout@v5` clones your repository into the virtual machine so the next steps can access your files.

Without this step, the runner has no code to work with.

---

**Step 2: Set up Python**

```yaml
- name: Set up Python 3.11
  uses: actions/setup-python@v6
  with:
    python-version: '3.11'
```

Installs Python 3.11 on the runner. `with:` passes parameters to the action — here we specify the version we want.

---

**Step 3: Install dependencies**

```yaml
- name: Install dependencies
  run: |
    python -m pip install --upgrade pip
    pip install pytest pytest-cov
    if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
  working-directory: './GH_Actions/lab1'
```

`run:` executes shell commands. The `|` means multi-line.

- `pip install --upgrade pip` — always a good practice to upgrade pip first
- `pip install pytest pytest-cov` — installs the test runner and coverage tool
- `if [ -f requirements.txt ]...` — installs from `requirements.txt` only if it exists (safe for projects with or without one)

`working-directory:` changes the folder the command runs from. Without this, the command would run at the repository root and not find `requirements.txt`.

---

**Step 4: Run tests**

```yaml
- name: Run tests
  run: |
    python -m unittest test_calculator.py -v
  working-directory: './GH_Actions/lab1'
```

Runs the test suite. The `-v` flag enables verbose output so you see each test method individually in the workflow log.

If any test fails, this step returns a non-zero exit code, which marks the entire workflow as **failed** (shown as a red ✗ in GitHub).

---

## 🎓 Key Concepts

### 1. Workflow File Location

GitHub only recognises workflows stored in `.github/workflows/` at the **repository root**. Files inside `GH_Actions/lab1/` are not picked up — the path matters.

### 2. `uses` vs `run`

| Keyword | What it does |
|---------|-------------|
| `uses: owner/action@version` | Runs a pre-built, reusable action from the marketplace |
| `run: shell command` | Runs raw shell commands directly on the runner |

### 3. `working-directory`

Because the repo contains multiple projects (`lab1/`, `lab2/`, etc.), you need to tell each step *which folder* to run in. Set `working-directory` at step level to scope commands to a subfolder.

### 4. Fail fast

If any step exits with an error, GitHub Actions stops the job immediately and marks it as failed. This means a broken test prevents a bad merge.

---

## ✨ Bonus: Enhanced Workflow

Once you understand the basics, here's how to level up the Lab 1 workflow:

```yaml
name: Python Tests - Lab 1 (Enhanced)

on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]

jobs:
  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest

    # Matrix: run the same job for 3 Python versions in parallel
    strategy:
      matrix:
        python-version: ['3.9', '3.10', '3.11']

    steps:
    - name: Checkout code
      uses: actions/checkout@v5

    - name: Set up Python ${{ matrix.python-version }}
      uses: actions/setup-python@v6
      with:
        python-version: ${{ matrix.python-version }}

    - name: Install dependencies
      run: |
        python -m pip install --upgrade pip
        pip install pytest pytest-cov
        if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
      working-directory: './GH_Actions/lab1'

    # Use pytest with coverage instead of unittest
    - name: Run tests with coverage
      run: |
        pytest test_calculator.py -v --cov=calculator --cov-report=term-missing
      working-directory: './GH_Actions/lab1'
```

**What's new:**

| Feature | How it works |
|---------|-------------|
| Matrix builds | `strategy.matrix` creates 3 parallel jobs — one per Python version |
| `${{ matrix.python-version }}` | Expression syntax; GitHub substitutes the actual version at runtime |
| `pytest` instead of `unittest` | Richer output; enables coverage reporting with `--cov` flags |
| `--cov-report=term-missing` | Prints which lines of `calculator.py` are NOT covered by tests |

---

## 🧪 Verifying the Workflow

1. Push any change to `main` (or open a pull request)
2. Go to your repository on GitHub → **Actions** tab
3. Click the latest workflow run
4. Expand the **test** job → expand each step to see its output
5. All steps should show a green checkmark ✅

---

## 💡 What You Should Understand After Lab 1

1. **Workflow structure** — `name`, `on`, `jobs`, `steps`
2. **Triggers** — push vs pull_request, branch filters
3. **Runners** — what `ubuntu-latest` means
4. **Pre-built actions** — `uses: actions/checkout` and `actions/setup-python`
5. **Shell steps** — `run:` with single and multi-line commands
6. **Working directory** — scoping commands to a subfolder
7. **Fail fast behaviour** — how a broken test stops the workflow

These are the exact same building blocks used in Lab 2. Once you can read this workflow confidently, you're ready to write one from scratch.

---

## 🔗 Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Workflow syntax reference](https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions)
- [actions/checkout](https://github.com/actions/checkout)
- [actions/setup-python](https://github.com/actions/setup-python)
- [pytest documentation](https://docs.pytest.org/)
