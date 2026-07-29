# Lab 3 — Loki: The Poison Pill

## Learning Objectives

By the end of this lab you will be able to:

1. Explain how Loki stores logs using **stream labels** instead of full-text indexing.
2. Describe the role of **Promtail** as the log collection agent.
3. Write **LogQL** queries using stream selectors, line filters, and JSON parsing.
4. Deploy the **kube-prometheus-stack** Helm chart and understand what it contains.
5. Use Grafana **Explore in split-view** to correlate a Prometheus error spike with Loki log lines — the same workflow SREs use in production.

---

## The Story

A "Payment Processor" app handles checkout requests. Error rates are spiking. The on-call engineer (you) needs to figure out **what** is failing and **why** — fast. You have Prometheus telling you *that* something is wrong, and Loki to tell you *why*. A hidden **poison pill** (`item=cursed_amulet`) returns 500 errors every time it's requested. Your job is to find it.

---

## Core Concepts

### What is Loki?

Loki is a log aggregation system from Grafana Labs, designed to be cost-efficient and easy to operate alongside Prometheus.

The key architectural difference from something like Elasticsearch is how Loki indexes data:

| | Elasticsearch / Splunk | Loki |
|---|---|---|
| What is indexed | Every field in every log line | Only the **labels** (metadata) |
| Log content | Indexed, searchable by field | Stored compressed, **not indexed** |
| Cost | High (index is large) | Low (index is tiny) |
| Query approach | Rich full-text search up front | Label selector first, then filter content |

**Stream labels** are the key concept. A *stream* is a unique combination of labels:

```
{namespace="monitoring", app="payment-processor"}
```

All log lines that share those labels belong to the same stream. Loki stores streams as compressed chunks. When you query, you first select a stream (uses the index, fast), then scan the log content within that stream (regex/string match, brute-force but fast because chunks are small).

**Rule of thumb:** Labels should be **low cardinality** — use `namespace`, `app`, `pod_name`, not `user_id` or `request_id` (those would create millions of streams and blow up the index).

---

### Push vs Pull

| | Prometheus (metrics) | Loki (logs) |
|---|---|---|
| Model | **Pull** — Prometheus scrapes `/metrics` on a schedule | **Push** — an agent reads log files and pushes to Loki |
| Agent | None (Prometheus does it) | **Promtail** (or Grafana Alloy) |

**Promtail** runs as a DaemonSet — one pod per node. It:

1. Reads container log files from `/var/log/pods/` on the node (where Kubernetes writes stdout/stderr).
2. Attaches Kubernetes metadata as labels (`namespace`, `pod`, `app`, the container name, etc.) using the Kubernetes API.
3. Ships log lines to Loki over HTTP (`/loki/api/v1/push`).

```
Pod stdout/stderr
  → /var/log/pods/ on the node
    → Promtail (DaemonSet) reads + labels
      → Loki (stores as streams)
        → Grafana (queries via LogQL)
```

---

### LogQL — Loki's Query Language

LogQL is modelled after PromQL. Every query starts with a **stream selector** (in curly braces) that uses the index. After that you chain **pipeline stages** that process the raw log content.

**Stream selector (required)**

```logql
{namespace="monitoring", app="payment-processor"}
```

Selects all log lines from that stream. Can use `=`, `!=`, `=~` (regex), `!~`.

**Line filter**

```logql
{namespace="monitoring"} |= "cursed_amulet"
```

`|= "string"` keeps only lines containing that string. `!= "string"` excludes them. Fast — scans raw bytes.

**JSON parsing + label filter**

```logql
{namespace="monitoring", app="payment-processor"} | json | level="error"
```

`| json` parses each log line as JSON and promotes every key to a label. Then `level="error"` filters to lines where the parsed `level` field equals `"error"`. This is how you do structured log filtering in Loki.

**Metric query (log volume over time)**

```logql
sum(rate({app="payment-processor"} |= "ERR-999" [1m]))
```

Counts matching log lines per second, grouped over time. Just like `rate()` in PromQL.

---

### What `kube-prometheus-stack` Contains

Instead of deploying bare Prometheus and Grafana (as in labs 1 and 2), this lab uses the **kube-prometheus-stack** Helm chart — the standard production approach.

It bundles:
- **Prometheus** + persistent storage
- **Prometheus Operator** — watches `ServiceMonitor` and `PrometheusRule` custom resources and configures Prometheus automatically (no hand-editing ConfigMaps)
- **Grafana** with pre-wired Prometheus datasource
- (optionally) AlertManager, kube-state-metrics, node-exporter — disabled in our values to keep the stack lean

The **ServiceMonitor** CRD is the production way to tell Prometheus about a scrape target. Instead of editing `prometheus.yaml`, you create a `ServiceMonitor` resource alongside your app, and the Operator picks it up.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│  namespace: monitoring                                              │
│                                                                     │
│  ┌──────────────────┐    /metrics    ┌────────────────────┐        │
│  │ payment-processor│◄──────────────│   Prometheus        │        │
│  │ (Flask + prom    │               │   (via ServiceMonitor│       │
│  │  client)         │               └────────────────────┘        │
│  │                  │ stdout (JSON)                                 │
│  └──────────────────┘ ────────────► /var/log/pods/ (node)          │
│                                          │                          │
│  ┌──────────────────┐                    ▼                          │
│  │ traffic-generator│          ┌──────────────────┐                │
│  │ (alpine curl loop│          │  Promtail         │               │
│  │  ~10% cursed     │          │  (DaemonSet)      │               │
│  │  amulet)         │          └────────┬─────────┘               │
│  └──────────────────┘                   │ push /loki/api/v1/push   │
│                                          ▼                          │
│                               ┌──────────────────┐                │
│                               │  Loki             │                │
│                               │  (single binary)  │                │
│                               └────────┬─────────┘               │
│                                         │                           │
│                    ┌────────────────────┴──────────────┐           │
│                    │           Grafana                  │           │
│                    │  DataSource 1: Prometheus          │           │
│                    │  DataSource 2: Loki (provisioned)  │           │
│                    └───────────────────────────────────┘           │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- Minikube running with at least **4 CPUs / 6 GB RAM** (kube-prometheus-stack is hungry):
  ```bash
  minikube start --cpus=4 --memory=6144
  ```
- `kubectl` and `helm` installed.
- Helm repos added:
  ```bash
  helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
  helm repo add grafana https://grafana.github.io/helm-charts
  helm repo update
  ```

### Pre-pull images into Minikube (prevents ImagePullBackOff)

Point your shell at Minikube's Docker daemon, then pull the images:

```bash
eval $(minikube docker-env)

# kube-prometheus-stack — Prometheus and Prometheus Operator
docker pull quay.io/prometheus/prometheus:v2.53.3
docker pull quay.io/prometheus-operator/prometheus-operator:v0.75.2
docker pull quay.io/prometheus-operator/prometheus-config-reloader:v0.75.2

# Grafana
docker pull grafana/grafana:11.1.0

# Loki
docker pull grafana/loki:3.1.0

# Promtail
docker pull grafana/promtail:3.1.0

# Payment Processor base image
docker pull python:3.9-slim

# Traffic generator
docker pull alpine:3.18
```

> These are the versions the Helm charts pin at the time of writing. If you see a different image in `ImagePullBackOff`, pull that version instead.

---

## Part 0: Install the Observability Stack

All three installs go into the `monitoring` namespace. Run them one after another and let the pods come up.

### 0.1 — kube-prometheus-stack (Prometheus + Grafana)

```bash
helm install monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace \
  -f helm-values/1-kube-prometheus-stack.yaml
```

Our `1-kube-prometheus-stack.yaml` values:
- Disables AlertManager, kube-state-metrics, and node-exporter (not needed here).
- Sets `adminPassword: admin` (deterministic — no secret lookup needed).
- Pre-provisions Loki as a second data source at `http://loki.monitoring.svc.cluster.local:3100`.
- Configures Prometheus to watch **all** ServiceMonitors in all namespaces (not just `release: monitoring` ones).

### 0.2 — Loki (log storage)

```bash
helm install loki grafana/loki \
  --namespace monitoring \
  -f helm-values/2-loki.yaml
```

Our `2-loki.yaml` values deploy Loki in **single-binary** mode — all components in one pod, storing data on a local volume. This is the development configuration; production uses distributed mode with object storage.

### 0.3 — Promtail (log collector)

```bash
helm install promtail grafana/promtail \
  --namespace monitoring \
  -f helm-values/3-promtail.yaml
```

Promtail installs as a DaemonSet. It picks up the push URL (`http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/push`) from our values file — no manual configuration needed.

### 0.4 — Wait for everything to be Ready

```bash
kubectl get pods -n monitoring -w
```

Expected pods (all should reach `Running`):
```
monitoring-grafana-...           1/1   Running
monitoring-prometheus-...        2/2   Running
prometheus-operator-...          1/1   Running
loki-0                           1/1   Running
promtail-xxxxx (one per node)    1/1   Running
```

This will take **3–8 minutes** on first run while images are pulled. Grab a coffee.

---

## Part 1: Deploy the App

### 1.1 — Build the Payment Processor image

Run this from the `lab3 - loki/` folder with Docker pointed at Minikube:

```bash
eval $(minikube docker-env)
docker build -t payment-processor:v1 ./app
```

> If you prefer to load instead of build inside Minikube:
> ```bash
> docker build -t payment-processor:v1 ./app   # uses your local Docker
> minikube image load payment-processor:v1
> ```

### 1.2 — Apply the manifests

```bash
kubectl apply -f k8s/
```

This creates three resources in the `monitoring` namespace:

| Manifest | What it creates |
|---|---|
| `1-payment-app.yaml` | `payment-processor` Deployment + ClusterIP Service |
| `2-service-monitor.yaml` | `ServiceMonitor` — tells the Prometheus Operator to scrape `/metrics` |
| `3-traffic-generator.yaml` | `traffic-generator` Deployment — curl loop, ~10% requests use `cursed_amulet` |

### 1.3 — Verify

```bash
kubectl get pods -n monitoring -l app=payment-processor
kubectl get pods -n monitoring -l app=traffic-generator
```

Both should be `Running`. The traffic generator starts sending requests immediately. Within 30 seconds the first metrics will be scraped.

**Confirm Prometheus is scraping the app:**

```bash
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

Open **http://localhost:9090/targets** and look for `payment-processor`. Status should be `UP`.

You can also run a quick PromQL check:

```promql
http_requests_total{job="payment-processor"}
```

If you see results, Prometheus is scraping the app. Kill the port-forward (`Ctrl-C`) when done.

---

## Part 2: Verify Logs Are Flowing into Loki

Before the main investigation, confirm Promtail is shipping logs.

```bash
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
```

Open **http://localhost:3000** → Login: `admin` / `admin`.

1. Left menu → **Explore**.
2. Data source dropdown → **Loki**.
3. Switch editor to **Code** mode.
4. Run this query:

```logql
{namespace="monitoring"} |= "payment"
```

You should see JSON log lines from the payment-processor within a few seconds. If you see logs, Promtail is working and Loki is receiving data. If you see nothing after 60 seconds, check the [Troubleshooting](#troubleshooting) section.

---

## Part 3: The Investigation — Correlate Metrics and Logs

This is the core exercise. You will use **Explore in split view** — Prometheus on the left showing *that* there's a problem, Loki on the right showing *why*.

Keep the port-forward to Grafana running (`kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80`).

1. Left menu → **Explore**.
2. Click **Split** (the split-view icon in the top-right of Explore). You now have two panels side by side.

### Left panel — Prometheus: detect the anomaly

- Data source: **Prometheus**
- Query:
  ```promql
  sum(rate(http_requests_total{status="500"}[1m]))
  ```
- Click **Run query**.

You will see periodic spikes. The traffic generator fires `cursed_amulet` approximately 10% of the time, so the 500 rate is not zero but spikes irregularly.

**Drill down further** — see the total error ratio:

```promql
sum(rate(http_requests_total{status="500"}[1m])) 
  / 
sum(rate(http_requests_total[1m]))
```

This tells you roughly 10% of all requests are failing. Unusual for a checkout endpoint.

### Right panel — Loki: find the cause

- Data source: **Loki**
- Query (structured — uses JSON parsing):
  ```logql
  {namespace="monitoring", app="payment-processor"} | json | level="error"
  ```
- Click **Run query**.

You should see error log lines appearing in sync with the Prometheus spikes. Expand a line — you will find:

```json
{
  "level": "error",
  "msg": "Payment Gateway Timeout",
  "item": "cursed_amulet",
  "error_code": "ERR-999",
  "endpoint": "/checkout"
}
```

The poison pill is `item=cursed_amulet`. Every time the traffic generator sends `cursed_amulet`, the app returns 500 and logs an error with `ERR-999`.

**Alternative query if the JSON filter isn't matching:**

```logql
{namespace="monitoring"} |= "ERR-999"
```

The `|=` line filter doesn't require JSON parsing — it matches the raw log string. Only the payment-processor logs `ERR-999`.

### What you just did

You used **metrics** to detect that there's a problem (error rate spike), then switched to **logs** to identify the exact request causing it (the cursed_amulet item). This is the canonical SRE workflow:

> Metrics tell you *that* something is broken. Logs tell you *what* is broken and *why*.

---

## Part 4: LogQL Challenges

Practice the LogQL concepts from the Core Concepts section.

**Challenge 1 — Count error log lines per minute:**

```logql
sum(rate({namespace="monitoring", app="payment-processor"} | json | level="error" [1m]))
```

Switch from "Logs" to "Metrics" view in Explore to see it as a time-series graph.

**Challenge 2 — See all successful checkouts:**

```logql
{namespace="monitoring", app="payment-processor"} | json | level="info"
```

What items are being purchased successfully?

**Challenge 3 — Count unique items that produced an error:**

```logql
sum by (item) (
  rate({namespace="monitoring", app="payment-processor"} | json | level="error" [1m])
)
```

Only `cursed_amulet` should appear — the only item that triggers 500s.

**Challenge 4 — Traffic generator access logs:**

```logql
{namespace="monitoring", app="traffic-generator"}
```

What do these logs look like? Why are they different from the payment-processor logs?

**Challenge 5 — Correlate on a specific time window:**

In the Prometheus panel, click on one of the error spikes. Grafana will snap the time range to that window. The Loki panel should automatically update to show logs from the same window. This is the time-sync feature of Explore split view.

---

## Part 5: What the ServiceMonitor Does (Bonus)

Run this to inspect the ServiceMonitor you applied:

```bash
kubectl describe servicemonitor payment-processor -n monitoring
```

Notice the `selector` field — it matches the Service label `app: payment-processor`. The Prometheus Operator watches for ServiceMonitor resources and automatically updates Prometheus's scrape configuration. You never edit `prometheus.yaml` directly. This is how scrape targets are managed at scale.

Compare this to lab 1 where you hand-edited the `prometheus-config` ConfigMap and restarted Prometheus. ServiceMonitor is the production alternative.

---

## Summary

| Step | What you did |
|---|---|
| **0** | Installed `kube-prometheus-stack` (Prometheus + Grafana + Operator), `grafana/loki` (single binary), and `grafana/promtail` (DaemonSet) in the `monitoring` namespace using trimmed Helm values files. |
| **1** | Built the payment-processor image and applied manifests: Deployment, Service, ServiceMonitor, traffic-generator. |
| **2** | Verified logs are flowing from pods → Promtail → Loki → Grafana Explore. |
| **3** | Used Grafana Explore in split view to correlate a Prometheus error spike (left) with Loki error log lines (right), identifying `cursed_amulet` as the poison pill. |
| **4** | Practiced LogQL: stream selectors, line filters, JSON parsing, metric queries. |

**Key concepts to take away:**
- Loki indexes only **labels**, not log content — this is why it's cheap to operate.
- Promtail runs as a DaemonSet and ships stdout/stderr to Loki with Kubernetes metadata attached as labels.
- LogQL always starts with a stream selector `{labels}` before filtering content.
- kube-prometheus-stack + ServiceMonitor is the production Prometheus deployment pattern.

---

## Cleanup

```bash
# Remove the app
kubectl delete -f k8s/

# Remove the observability stack
helm uninstall promtail -n monitoring
helm uninstall loki -n monitoring
helm uninstall monitoring -n monitoring

# Remove the namespace (optional — cleans up PVCs too)
kubectl delete namespace monitoring
```

---

## Troubleshooting

### No logs in Loki after 60 seconds

**Check Promtail is running:**

```bash
kubectl get pods -n monitoring -l app.kubernetes.io/name=promtail
kubectl logs -n monitoring -l app.kubernetes.io/name=promtail --tail=50
```

Look for lines like `"msg":"send batch","status":204"` — that means Promtail is successfully pushing to Loki.

**Check Loki is healthy:**

```bash
kubectl run -n monitoring curl-test --rm -it --restart=Never --image=curlimages/curl \
  -- curl -s "http://loki.monitoring.svc.cluster.local:3100/loki/api/v1/labels"
```

Should return JSON with `"values":[...]`. If it returns nothing or errors, Loki isn't ready — check `kubectl logs -n monitoring loki-0`.

**Promtail can't read node log files (Minikube Docker driver quirk):**

On macOS with the Docker driver, Promtail may not find log files at `/var/log/pods`. Verify:

```bash
minikube ssh "ls /var/log/pods"
```

If this is empty, the Docker driver is writing logs to a different path. Workaround: restart Minikube with the `--driver=hyperkit` or `--driver=virtualbox` driver, or check Grafana Alloy as a replacement for Promtail on Docker-driver Minikube.

### Payment Processor pod is ImagePullBackOff

```bash
eval $(minikube docker-env)
docker build -t payment-processor:v1 ./app
```

The image must be built INSIDE Minikube's Docker daemon, not your laptop's Docker. Make sure `eval $(minikube docker-env)` was run in the same terminal session before `docker build`.

### Prometheus isn't scraping the payment-processor

Check targets:

```bash
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
# open http://localhost:9090/targets
```

If `payment-processor` isn't listed, the Prometheus Operator hasn't picked up the ServiceMonitor. Verify:

```bash
kubectl get servicemonitor -n monitoring payment-processor
```

The Prometheus Operator selects ServiceMonitors based on `serviceMonitorSelector`. Our `1-kube-prometheus-stack.yaml` sets this to `{}` (all ServiceMonitors). If you installed kube-prometheus-stack WITHOUT the values file, the default selector only picks up ServiceMonitors with the label `release: monitoring`. You can add that label to fix it:

```bash
kubectl label servicemonitor payment-processor -n monitoring release=monitoring
```

### Grafana "Data source connected, but no labels received" for Loki

This means Loki is reachable but has no ingested logs yet. Wait 1–2 minutes for Promtail to ship its first batch, then run a Loki query again.
