# Lab 2: Grafana — Visualizing Prometheus Metrics

## Learning Objectives

By the end of this lab you will be able to:

1. Explain Grafana's role in the observability stack and how it connects to data sources
2. Navigate the Grafana UI: dashboards, panels, Explore, and Alerting
3. Import a dashboard from a JSON file and from the Grafana community
4. Build a dashboard from scratch with Stat, Time series, and Gauge panels
5. Add a template variable so one dashboard works across multiple environments
6. Export a dashboard as JSON and understand why this matters for GitOps
7. Explain provisioning — how dashboards and data sources are loaded from ConfigMaps at startup
8. Create an alert rule and watch it fire

---

## Core Concepts

### Grafana's Role

Grafana is the **visualisation and alerting layer** of the LGTM stack. It does not store
data — it queries data sources and renders the results. A single Grafana instance can
connect to Prometheus, Loki, Tempo, and Mimir simultaneously, which is exactly what this
course builds toward.

```
Prometheus ──┐
Loki        ─┤── Grafana ── Dashboards, Alerts, Explore
Tempo       ─┤              (single pane of glass)
Mimir       ─┘
```

This lab connects Grafana only to Prometheus (lab 1). Labs 3–5 add the remaining sources.

---

### Three Ways to Get a Dashboard

| Method | When to use |
|--------|-------------|
| **Provisioned** (ConfigMap) | Production/GitOps — loaded at startup, cannot be accidentally deleted |
| **Import** (JSON or community ID) | Quickly adopting a community or team dashboard |
| **Build from scratch** | Custom dashboards for your specific metrics |

You will practice all three in this lab.

---

### Provisioning — Dashboards as Code

When Grafana starts, it reads two provisioning directories:

```
/etc/grafana/provisioning/datasources/   ← .yaml files that configure data sources
/etc/grafana/provisioning/dashboards/    ← .yaml files that tell Grafana WHERE to find JSONs
/var/lib/grafana/dashboards/             ← the actual dashboard .json files
```

In this lab, all three are mounted from ConfigMaps. The dashboard loaded at startup
(`metric-app.json`) comes from `k8s/4-dashboards.yaml` — the same file that lives in
this Git repository. **That is GitOps for dashboards: the source of truth is the repo,
not the Grafana database.**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Kubernetes cluster (Minikube, default namespace)            │
│                                                              │
│  ┌──────────────────────┐   queries    ┌─────────────────┐  │
│  │  Grafana             │ ──────────►  │  Prometheus     │  │
│  │  :3000 (NodePort     │ ◄──────────  │  :9090          │  │
│  │   30300)             │   results    │  (from lab 1)   │  │
│  │                      │              └─────────────────┘  │
│  │  ConfigMap mounts:   │                      ▲            │
│  │  · datasources.yaml  │              scrapes every 5s     │
│  │  · provider.yaml     │              ┌─────────────────┐  │
│  │  · metric-app.json   │              │  metric-app     │  │
│  └──────────────────────┘              │  :8000          │  │
│                                        │  (from lab 1)   │  │
│                                        └─────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

**Lab 1 must be running.** Grafana queries `prometheus-service:9090` which was deployed in
lab 1. If it is not running, all dashboard panels will show "No data."

```bash
kubectl get pods -l app=prometheus
kubectl get pods -l app=metric-app
```

Both should show `1/1 Running`.

**Pre-pull the Grafana image** to avoid `ImagePullBackOff` from Docker Hub rate limits:

```bash
eval $(minikube docker-env)
docker pull grafana/grafana:11.1.0
```

> **Skipped `eval`?** Use: `docker pull grafana/grafana:11.1.0 && minikube image load grafana/grafana:11.1.0`

---

## Part 0: Deploy Grafana

Apply all four manifests at once:

```bash
kubectl apply -f k8s/
```

This creates:
- `grafana` Deployment and NodePort Service (port 30300)
- `grafana-datasources` ConfigMap — Prometheus auto-wired as default data source
- `grafana-dashboard-provider` ConfigMap — tells Grafana to scan `/var/lib/grafana/dashboards`
- `grafana-dashboards` ConfigMap — contains `metric-app.json`, loaded at startup

Wait for the Pod to be ready:

```bash
kubectl get pods -l app=grafana -w
# Ctrl+C when 1/1 Running
```

**Access Grafana:**

```bash
# Option A — NodePort (open in browser directly)
minikube service grafana --url

# Option B — port-forward
kubectl port-forward svc/grafana 3000:3000
# then open http://localhost:3000
```

Log in with **admin / admin**.

---

## Part 1: The Provisioned Dashboard

Before doing anything, look at the left sidebar: **Dashboards → Browse → Lab Dashboards**.
You should see **"Metric App — Observability"** already loaded.

Open it. All 6 panels should show live data:
- Three **Stat** panels across the top: Total Request Rate, Error Rate, Error Ratio
- One **Gauge** (In-Progress Requests) — should bounce between 0 and 10
- Two **Time series** panels: Request Rate by Status (two lines: 200 and 500) and P99 Latency (~2.5s)

**Why is this already here?** Because `k8s/4-dashboards.yaml` mounted `metric-app.json`
into the container at startup. Grafana read it before you logged in. This is provisioning —
no clicking required.

Notice the **lock icon** on the dashboard title bar. Provisioned dashboards are read-only
in the UI by design: the source of truth is the ConfigMap (and the JSON in this repository),
not the database. To change a provisioned dashboard, you edit the JSON in Git and re-apply
the ConfigMap.

> **If panels show "No data":** Confirm lab 1 is running (`kubectl get pods -l app=metric-app`).
> Wait 15 seconds for a few scrape cycles, then refresh.

---

## Part 2: Import a Dashboard

The import workflow is how you adopt dashboards from your team or from the community — the
same dialog accepts a JSON file, a pasted JSON blob, or a grafana.com dashboard ID.

### 2.1 Import from a JSON file

1. In the left sidebar, go to **Dashboards → New → Import**.
2. Click **Upload dashboard JSON file**.
3. Select `grafana/dashboards/metric-app.json` from this repository.
4. On the next screen, change the **Name** to `Metric App — Imported` to distinguish it.
5. Under **Prometheus**, select **Prometheus** from the dropdown.
6. Click **Import**.

You now have an identical copy of the provisioned dashboard — but this one is stored in
Grafana's database, not the ConfigMap. It is editable and will not survive a pod restart
(which is exactly why the provisioned version exists).

### 2.2 The community at grafana.com

The Grafana community publishes thousands of dashboards at [grafana.com/grafana/dashboards](https://grafana.com/grafana/dashboards).
Each one has a numeric ID. The import process is identical:

1. Go to **Dashboards → New → Import**.
2. Paste the ID (e.g. **3662** — "Prometheus 2.0 Overview") into the **"Import via grafana.com"** box.
3. Click **Load**, configure the data source, click **Import**.

Dashboard ID 3662 queries Prometheus's own internal metrics (scrape counts, storage size)
and will show live data immediately since Prometheus is running.

> **The mental model:** A dashboard JSON is a portable artifact — like a Docker image.
> It can be shared, versioned in Git, and imported anywhere. This is the same whether it
> comes from a file, a paste, or a community ID.

---

## Part 3: Build a Dashboard from Scratch

Creating panels manually gives you full control and teaches you how queries, visualisations,
and thresholds connect.

### 3.1 Create a new dashboard

1. **Dashboards → New → New dashboard**.
2. Click **Add visualisation**.
3. Select **Prometheus** as the data source.

### 3.2 Time series panel — Request rate by status

In the panel editor:

1. In the query box (bottom), enter:
   ```promql
   sum by (status) (rate(http_requests_total[$__rate_interval]))
   ```
2. Set **Legend** to `HTTP {{status}}` — Grafana fills in the label value.
3. At the top right, change the visualisation type to **Time series** (it may already be selected).
4. Under **Panel options** (right sidebar), set **Title** to `Request Rate by Status`.
5. Under **Standard options → Unit**, choose **Requests/sec (reqps)**.
6. Click **Apply**.

### 3.3 Stat panel — Error ratio

1. Click **Add panel → Add visualisation**.
2. Enter:
   ```promql
   sum(rate(http_requests_total{status="500"}[$__rate_interval]))
   /
   sum(rate(http_requests_total[$__rate_interval]))
   ```
3. Change visualisation type to **Stat**.
4. Title: `Error Ratio`.
5. Unit: **Percent (0.0-1.0)**.
6. Under **Thresholds**, add: green → 0, yellow → 0.15, red → 0.25.
7. **Apply**.

### 3.4 Gauge panel — In-progress requests

1. Add another panel.
2. Enter: `in_progress_requests`
3. Visualisation: **Gauge**.
4. Title: `In-Progress Requests`.
5. Set **Min** = 0, **Max** = 10.
6. **Apply**.

### 3.5 Add a template variable

Template variables make dashboards environment-agnostic — the same dashboard can query
`my-app-job` in dev and a different job in prod without editing any query.

1. Click the **dashboard settings** gear icon (top right).
2. Go to **Variables → Add variable**.
3. Configure:
   - **Type:** Query
   - **Name:** `job`
   - **Label:** `Job`
   - **Data source:** Prometheus
   - **Query:** `label_values(http_requests_total, job)`
4. Click **Run query** — the preview should show `my-app-job`.
5. **Save** the variable, then **Save** the dashboard.

Now go back to the dashboard and add `{job="$job"}` to each panel's query:

```promql
sum by (status) (rate(http_requests_total{job="$job"}[$__rate_interval]))
```

A `Job` dropdown appears at the top of the dashboard. You can now switch between jobs
without editing a single query — this is why Grafana exists instead of the raw Prometheus UI.

### 3.6 Save the dashboard

Click the **Save** button (or Ctrl+S). Name it `My Metric App Dashboard`.

---

## Part 4: Export and the GitOps Pattern

### 4.1 Export the dashboard you just built

1. Open the dashboard settings gear icon.
2. Go to **JSON Model**.
3. You will see the complete JSON representation of your dashboard.
4. Click **Copy to clipboard** or **Save to file** (`metric-app-custom.json`).

This JSON is the single source of truth for your dashboard. Anyone who has this file can
recreate the exact same dashboard by importing it. **This is why dashboards belong in Git.**

### 4.2 The ConfigMap pattern (already live)

Open `k8s/4-dashboards.yaml`. You will see the exact same JSON structure embedded in the
`data.metric-app.json` key of the ConfigMap. Compare it to
`grafana/dashboards/metric-app.json` in this repository — they are the same file.

The workflow in a real team:
```
Edit metric-app.json in Git
    → PR review
        → merge
            → kubectl apply -f k8s/4-dashboards.yaml
                → Grafana reloads from ConfigMap (within ~30s)
```

No one clicks in the UI. The dashboard is reviewed, versioned, and deployed like any other
infrastructure change. This is the GitOps pattern for Grafana.

> **Try it:** Delete the provisioned dashboard from the UI. Wait 30 seconds. It comes
> back automatically — Grafana reloads from the ConfigMap on the `updateIntervalSeconds`
> interval set in the provider config.

---

## Part 5: Alerting

Grafana's unified alerting lets you define conditions on any data source query and route
notifications to Slack, PagerDuty, email, etc. Here you create one rule to watch the error
rate.

### 5.1 Create an alert rule

1. In the left sidebar, go to **Alerting → Alert rules**.
2. Click **New alert rule**.
3. Configure:

   **Section 1 — Query:**
   - Data source: **Prometheus**
   - Query A:
     ```promql
     sum(rate(http_requests_total{job="my-app-job", status="500"}[1m]))
     ```
   - Query B (Threshold): Select **Classic condition** → **IS ABOVE** → `0.2`

   **Section 2 — Evaluation:**
   - Folder: choose any (or create `Lab Alerts`)
   - Evaluation group: `default`
   - Evaluate every: `10s`, for `0s`

   **Section 3 — Labels and annotations:**
   - Summary: `Error rate is above threshold`
   - Description: `500 error rate is {{ $values.A.Value | printf "%.2f" }} req/s`

4. Click **Save rule and exit**.

### 5.2 Watch it fire

1. Go to **Alerting → Alert rules**. The rule starts in **Pending** state.
2. After the evaluation period, it will move to **Firing** (the error rate is ~0.20 req/s,
   above the 0.2 threshold).
3. Go to **Alerting → Alert rules** and click the rule to see the query graph and the firing
   state.

> **The 20% error rate** comes from the metric-app simulation. The threshold of 0.2 req/s
> is deliberately set just below the actual error rate so the alert fires immediately in the lab.

> **Contact points:** We have not configured a notification channel, so the alert fires in
> the UI only. In production you would add a contact point (Slack webhook, PagerDuty key,
> etc.) under **Alerting → Contact points** and assign it to a notification policy.

---

## Summary

| Concept | Key point |
|---------|-----------|
| **Provisioning** | Dashboards and data sources loaded from ConfigMaps at startup — GitOps for Grafana |
| **Data source UID** | Must match between provisioning YAML and dashboard JSON (`uid: prometheus`) |
| **Import** | JSON file, pasted JSON, or grafana.com community ID — all the same dialog |
| **Template variables** | `label_values(metric, label)` → dropdown in dashboard header |
| **`$__rate_interval`** | Grafana magic variable — correct rate window based on time range and scrape interval |
| **Alert rule** | PromQL condition + evaluation interval → Firing/Resolved state |
| **GitOps pattern** | `metric-app.json` in Git → ConfigMap → Grafana loads on startup |

---

## Cleanup

```bash
kubectl delete -f k8s/
```

> **Keep lab 1 running** if you are continuing to lab 3 (Loki) — it reuses the same
> Prometheus and metric-app.
