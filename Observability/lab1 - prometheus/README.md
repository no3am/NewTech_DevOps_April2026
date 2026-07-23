# Lab 1: Prometheus — The Pull Model

## Learning Objectives

By the end of this lab you will be able to:

1. Explain the Prometheus pull model and why it differs from push-based monitoring
2. Describe the three core metric types (Counter, Gauge, Histogram) and when to use each
3. Explain what labels are and how they add dimensions to metrics
4. Read the raw Prometheus text format that every scrape target exposes
5. Write basic PromQL: `rate()`, `sum by()`, `histogram_quantile()`
6. Deploy a complete scrape pipeline on Kubernetes from scratch

---

## Core Concepts

### What is Prometheus?

Prometheus is a **time-series database and monitoring system**. It stores sequences of
timestamped numbers — e.g. "the error count at T=0 was 5, at T=5 it was 7, at T=10 it was 9".
You query those sequences with **PromQL** to build dashboards and alerts.

### The Pull Model

Prometheus is in control of the data collection. It **periodically calls (scrapes)**
the `/metrics` HTTP endpoint of each target on a configured interval.

```
Every 5 seconds:

Prometheus ──── GET /metrics ────► metric-app-service:8000
               ◄─── text response ───
               (stores the values as a time series)
```

Compare this to a **push model** (e.g. StatsD): the app decides when to send data to a
collector. With pull, if an app goes down, Prometheus immediately sees it as a missing
scrape — the monitoring system detects outages on its own.

---

### Metric Types

Every metric in Prometheus is one of these three types:

#### Counter
A number that **only goes up** (it resets to 0 when the process restarts, never mid-run).

```
Total HTTP requests: 0 → 1 → 2 → 5 → 9 → 14 → ...
```

**Rule:** Never query a Counter directly for rate — the raw number is just a cumulative
total. Always use `rate()` to get "how many per second over a window":

```promql
rate(http_requests_total[1m])   ✅ meaningful: req/sec over last 1 minute
http_requests_total              ⚠️  just a large cumulative number
```

Examples: total requests, total errors, total bytes sent.

---

#### Gauge
A number that **can go up and down** — a point-in-time snapshot.

```
In-progress requests: 3 → 7 → 2 → 0 → 5 → ...
```

**Rule:** Query a Gauge directly. Using `rate()` on a Gauge is wrong — it treats an
up-and-down value as a monotonic counter and produces meaningless results.

```promql
in_progress_requests             ✅ current value right now
rate(in_progress_requests[1m])   ❌ meaningless
```

Examples: current memory usage, active connections, queue depth, CPU usage.

---

#### Histogram
Tracks the **distribution** of values across configurable buckets.

When you declare one `Histogram` metric in code, Prometheus automatically creates three
time series for you:

```
http_request_duration_seconds_bucket{le="0.1"}  ← requests that took ≤ 0.1s
http_request_duration_seconds_bucket{le="0.5"}  ← requests that took ≤ 0.5s
http_request_duration_seconds_bucket{le="1.0"}
... (one per bucket boundary)
http_request_duration_seconds_count             ← total number of observations
http_request_duration_seconds_sum               ← total combined duration
```

Use `histogram_quantile()` to compute percentiles — e.g. "how long did the slowest 1%
of requests take?"

Examples: request duration, response size, database query time.

---

### Labels

Labels are **key-value pairs** that add dimensions to a metric. The same metric name can
carry different labels to distinguish sub-types:

```
http_requests_total{status="200"}   ← successful requests
http_requests_total{status="500"}   ← error requests
```

PromQL lets you **filter** by label value and **aggregate** across labels:

```promql
http_requests_total{status="500"}                     # only errors
sum by (status) (rate(http_requests_total[1m]))        # rate broken down by status label
```

Labels are what make Prometheus metrics multidimensional. Keep them low-cardinality
(avoid user IDs or request IDs as label values — that creates millions of series).

---

### What `/metrics` Looks Like

Every scrape target exposes a plain-text HTTP endpoint. This is the raw format Prometheus
reads. You will `curl` it yourself in Part 4 — here is a preview:

```
# HELP http_requests_total Total HTTP requests
# TYPE http_requests_total counter
http_requests_total{status="200"} 142.0
http_requests_total{status="500"} 31.0

# HELP in_progress_requests Number of requests currently being processed
# TYPE in_progress_requests gauge
in_progress_requests 4.0

# HELP http_request_duration_seconds_bucket Request duration histogram
http_request_duration_seconds_bucket{le="0.1"} 12.0
http_request_duration_seconds_bucket{le="0.5"} 67.0
http_request_duration_seconds_bucket{le="1.0"} 103.0
http_request_duration_seconds_bucket{le="+Inf"} 142.0
http_request_duration_seconds_count 142.0
http_request_duration_seconds_sum 87.34
```

---

## Architecture

This lab deploys three things in the `default` namespace:

```
┌─────────────────────────────────────────────────────┐
│  Kubernetes cluster (Minikube)                       │
│                                                      │
│  ┌───────────────┐        scrapes every 5s           │
│  │  Prometheus   │ ────── GET /metrics ──────────►  │
│  │  (port 9090)  │ ◄───── text format ───────────   │
│  └───────────────┘                                   │
│         │ reads config                               │
│  ┌──────┴──────────────┐   ┌──────────────────────┐ │
│  │  prometheus-config  │   │  metric-app          │ │
│  │  (ConfigMap)        │   │  (port 8000)         │ │
│  │  scrape: app:8000   │   │  /metrics endpoint   │ │
│  └─────────────────────┘   └──────────────────────┘ │
└─────────────────────────────────────────────────────┘
```

**The app** (`metric-app`) simulates a web server. It exposes all three metric types on
`:8000/metrics` and keeps generating simulated traffic: 80% success (200), 20% errors
(500), with 10% of requests taking 2.5s (slow queries).

---

## Prerequisites

- Minikube running, `kubectl` configured
- Docker installed

---

## Part 1: Build the Image

The app lives in `app/`. It is a Python script that uses the `prometheus_client` library
to expose the three metric types you just read about.

Point Docker at Minikube's daemon so images built or pulled here are visible to the cluster:

```bash
eval $(minikube docker-env)
```

Pull the Prometheus image now so it is cached before the server deploys (avoids
`ImagePullBackOff` from Docker Hub rate limits later):

```bash
docker pull prom/prometheus:v2.53.3
```

Build the app image from the **lab1 - prometheus** folder (parent of `app/`):

```bash
docker build -t metric-app:v1 ./app
```

Verify both images are present:

```bash
docker images | grep -E "metric-app|prometheus"
```

> **Alternative if you skipped `eval $(minikube docker-env)`:** Build and load separately:
> ```bash
> docker build -t metric-app:v1 ./app
> docker pull prom/prometheus:v2.53.3
> minikube image load metric-app:v1
> minikube image load prom/prometheus:v2.53.3
> ```

---

## Part 2: Deploy

Apply in this order — the ConfigMap must exist before the Prometheus server starts,
because the server reads the config on startup.

**1. Deploy the app (Deployment + Service).**

```bash
kubectl apply -f k8s/1-app.yaml
```

This creates a `metric-app` Deployment (1 replica) and a `metric-app-service` ClusterIP
Service on port 8000. The Service is how Prometheus will reach the app — by DNS name,
not by Pod IP.

**2. Deploy the Prometheus config (ConfigMap).**

```bash
kubectl apply -f k8s/2-prometheus-config.yaml
```

Open `k8s/2-prometheus-config.yaml` and read it. The key section is:

```yaml
scrape_configs:
  - job_name: my-app-job
    static_configs:
      - targets:
          - metric-app-service:8000   ← DNS name of the Service, not a Pod IP
```

This tells Prometheus: "every `scrape_interval` (5s), GET `http://metric-app-service:8000/metrics`".
Using the Service DNS name means it keeps working even if the Pod restarts and gets a new IP.

**3. Deploy the Prometheus server (Deployment + Service).**

```bash
kubectl apply -f k8s/3-prometheus-server.yaml
```

**Wait until all Pods are ready:**

```bash
kubectl get pods -w
# Ctrl+C when both metric-app and prometheus show 1/1 Running
```

---

## Part 3: Verify the Wiring

Port-forward Prometheus to your machine:

```bash
kubectl port-forward svc/prometheus-service 9090:9090
```

Leave this running in one terminal. Open **http://localhost:9090** in your browser.

**Check the scrape target:**

1. Go to **Status → Targets**.
2. Find the job **my-app-job**.
3. The target `metric-app-service:8000` should show **State: UP** (green).

If the state is DOWN, the scrape pipeline is broken — see the error column and check
`kubectl logs deployment/prometheus` for details.

---

## Part 4: Peek at the Raw `/metrics` Endpoint

Before writing PromQL, see the raw data Prometheus is actually pulling. Run `curl`
against the app from inside the cluster:

```bash
kubectl run curl-test --image=curlimages/curl --restart=Never --rm -it \
  -- curl http://metric-app-service:8000/metrics
```

You should see the Prometheus text format — the same output shown in Core Concepts above.
Scroll through it and find:
- `http_requests_total{status="200"}` and `{status="500"}` — the Counter with two label values
- `in_progress_requests` — the Gauge, a single number
- `http_request_duration_seconds_bucket{le="..."}` — one line per histogram bucket

**This is exactly what Prometheus reads every 5 seconds.** Everything you query in PromQL
comes from this endpoint.

---

## Part 5: PromQL Challenges

Run each query in the Prometheus UI: go to **Graph**, paste the query into the box,
and click **Execute**. Switch between the **Table** tab (current values) and the
**Graph** tab (values over time).

---

**Challenge 1 — Counter rate:** *"How many requests per second are we getting?"*

```promql
rate(http_requests_total[1m])
```

`rate()` computes the per-second rate of change of a Counter over the last 1 minute.
You get two lines — one for `status="200"` and one for `status="500"`.

Switch to **Graph** and watch the lines move as the app keeps generating traffic.

---

**Challenge 2 — Sum by label:** *"What is the total request rate, split by success vs error?"*

```promql
sum by (status) (rate(http_requests_total[1m]))
```

`sum by (status)` aggregates all series that share the same `status` label value.
You still get two lines, but now the y-axis shows the combined rate per status.
The `status="200"` line should be roughly 4× higher than `status="500"` (80/20 split).

---

**Challenge 3 — Gauge:** *"How many requests are in-progress right now?"*

```promql
in_progress_requests
```

No `rate()`. This is a Gauge — the value itself is meaningful. It fluctuates between
0 and 10 as the simulation runs. On the **Graph** tab you'll see it jumping up and down,
which is exactly what a Gauge should look like.

---

**Challenge 4 — Error ratio:** *"What percentage of traffic is errors?"*

```promql
sum(rate(http_requests_total{status="500"}[1m]))
/
sum(rate(http_requests_total[1m]))
```

Dividing the error rate by the total rate gives a ratio. You should see approximately
`0.20` (20%) — matching the 80/20 split in the simulation.

---

**Challenge 5 — Histogram percentile:** *"How slow is the site for the unluckiest 1% of users?"*

```promql
histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))
```

Breaking this down:
- `http_request_duration_seconds_bucket` — the auto-generated bucket counters
- `rate(...[5m])` — per-second rate of observations landing in each bucket over 5 minutes
- `sum(...) by (le)` — aggregate across all instances, keeping the `le` (less-or-equal) label
- `histogram_quantile(0.99, ...)` — compute the 99th percentile from the bucket rates

You should see a value around **2.5** — the 2.5s slow queries that 10% of simulated
requests trigger. Use a 5m window so the estimate is stable (shorter windows are noisy).

---

## Summary

| Component | Role |
|-----------|------|
| **metric-app** | Exposes `/metrics` on port 8000 — Counter, Gauge, Histogram |
| **prometheus-config** | ConfigMap: tells Prometheus to scrape `metric-app-service:8000` every 5s |
| **Prometheus server** | Reads the config, scrapes the target, stores time series |

| PromQL pattern | When to use |
|----------------|-------------|
| `rate(counter[window])` | Counter — get per-second rate |
| `sum by (label) (...)` | Aggregate and split by a label |
| `gauge_name` | Gauge — read current value directly |
| `histogram_quantile(p, rate(metric_bucket[window]) by (le))` | Histogram — compute percentile |

---

## Cleanup

```bash
kubectl delete -f k8s/3-prometheus-server.yaml
kubectl delete -f k8s/2-prometheus-config.yaml
kubectl delete -f k8s/1-app.yaml
```
