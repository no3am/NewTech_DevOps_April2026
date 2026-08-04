# Lab 5 — Chain Reaction: Traces, Logs, and the Full LGTM Stack

## Learning Objectives

By the end of this lab you will be able to:

1. Explain what a **trace**, a **span**, and **context propagation** are.
2. Describe the role of the **OTel Collector** as a telemetry broker.
3. Deploy **Grafana Tempo** and query traces with **TraceQL**.
4. Read a **waterfall diagram** and identify a latency bottleneck across service boundaries.
5. Correlate a trace to its log lines in **Loki** using the TraceID — both manually and via Grafana's **derived fields** (one-click linking).
6. Explain how the `trace_id_filter` in the app code stamps every log line with the active trace ID.

---

## The Story

You have a 3-tier microservice: **Service-A** (Gateway) → **Service-B** (Logic) → **Service-C** (Database). Users are reporting slow responses. You can see ~2 seconds of end-to-end latency — but which service is responsible?

Without tracing, you'd grep through logs from three separate services trying to reconstruct a single request. With tracing, you open one waterfall diagram that shows every hop, each service's contribution to latency, and a link to the exact log lines for that request.

This is the **LGTM stack** capstone: Loki (logs) + Grafana (visualization) + Tempo (traces) + your existing Mimir (metrics) — the full production observability story.

---

## Core Concepts

### Traces and Spans

A **trace** represents a single end-to-end request. It's composed of **spans** — individual units of work, each with:
- A name (e.g. `GET /`)
- A start time and duration
- A service name
- Attributes (HTTP method, status code, etc.)
- A parent span ID (linking it to the caller)

When Service-A calls Service-B, A's span is the **parent**; B creates a **child span**. The tree of spans for one request is the trace.

```
Trace: abc123 (total: 2.1s)
├── service-a: GET /           (2.1s)  ← root span
│   └── service-b: GET /request (2.05s)
│       └── service-c: GET /request (2.0s)  ← the culprit
```

### Context Propagation

How does Service-B know it's part of Service-A's trace? Via the **`traceparent` HTTP header** (W3C Trace Context standard). When Service-A calls Service-B using `httpx`, the `HTTPXClientInstrumentor` automatically injects this header. Service-B's `FastAPIInstrumentor` reads it and creates a child span with the correct parent.

Without this header injection, each service would create an isolated trace — no waterfall, no cross-service view.

### OpenTelemetry (OTel)

OTel is the industry-standard, vendor-neutral framework for instrumenting applications. It defines:
- **APIs** — what your code calls (`trace.get_current_span()`, etc.)
- **SDKs** — the implementation that collects and exports data
- **OTLP** — the wire protocol for sending telemetry data

The app uses `FastAPIInstrumentor` and `HTTPXClientInstrumentor` — these auto-instrument HTTP requests and responses without changing business logic.

### The OTel Collector

Services send spans to the **OTel Collector** rather than directly to Tempo. The Collector is a telemetry broker that:
1. **Receives** OTLP data (gRPC on 4317, HTTP on 4318)
2. **Processes** — batches, filters, enriches
3. **Exports** to one or more backends (Tempo, in our case)

In production you might export to Tempo AND a cloud vendor simultaneously — the app only needs to know about the Collector.

### Tempo

Tempo is Grafana's distributed tracing backend. It stores traces indexed by TraceID and accepts OTLP. Queries use **TraceQL** — a query language for traces:

```
{ resource.service.name = "service-a" }           # traces that include service-a
{ duration > 1s }                                  # traces slower than 1 second
{ resource.service.name = "service-c" && duration > 1s }  # slow service-c spans
```

### Derived Fields — Trace ↔ Log Linking

The `trace_id_filter` in each service adds the active TraceID to every log line:

```python
def trace_id_filter(record):
    span = trace.get_current_span()
    ctx = span.get_span_context()
    record.trace_id = format(ctx.trace_id, "032x") if ctx.is_valid else ""
    return True
```

This means every log line emitted while handling a request carries the same `trace_id` as the trace in Tempo.

Grafana **derived fields** use this to make linking automatic:
- **Loki → Tempo**: A log line containing `"trace_id":"abc123"` shows a clickable "TraceID" button that opens that trace in Tempo.
- **Tempo → Loki**: The Tempo trace view has a "Logs" button that queries Loki for all log lines with that TraceID.

Both are pre-configured in `k8s/5-grafana.yaml` — no manual setup needed.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  namespace: chain-reaction                                               │
│                                                                          │
│  ┌──────────┐   HTTP    ┌──────────┐   HTTP    ┌──────────┐             │
│  │Service-A │──────────►│Service-B │──────────►│Service-C │             │
│  │(Gateway) │           │(Logic)   │           │(DB sim)  │             │
│  └────┬─────┘           └────┬─────┘           └────┬─────┘             │
│       │ OTLP HTTP            │ OTLP HTTP            │ OTLP HTTP          │
│       └──────────────────────┴──────────────────────┘                   │
│                              │                                           │
│                              ▼                                           │
│                    ┌──────────────────┐                                  │
│                    │  OTel Collector  │  receive → batch → export        │
│                    └────────┬─────────┘                                  │
│                             │ OTLP gRPC                                  │
│                             ▼                                            │
│                    ┌──────────────────┐                                  │
│                    │      Tempo       │  stores traces                   │
│                    └────────┬─────────┘                                  │
│                             │ TraceQL query                              │
│  stdout (JSON)              │                                            │
│  ─────────────►  Promtail  ─────────────► Loki                          │
│  (trace_id      (cri stage               (log storage)                  │
│   in every       unwraps                       │ LogQL query             │
│   log line)      envelope)                     │                        │
│                                                │                        │
│                    ┌───────────────────────────┘                        │
│                    │           Grafana                                   │
│                    │  DS: Tempo  (TraceQL + "Logs" button → Loki)       │
│                    │  DS: Loki   (LogQL + "TraceID" button → Tempo)     │
│                    └────────────────────────────────────────────────────┘
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- Minikube running (`minikube start --cpus=4 --memory=6144`).
- `kubectl` configured.
- This lab is **self-contained** — its own namespace, its own Grafana, Tempo, and Loki. No dependency on previous labs.

### Pre-pull images (prevents ImagePullBackOff)

```bash
eval $(minikube docker-env)

docker pull otel/opentelemetry-collector-contrib:0.96.0
docker pull grafana/tempo:2.2.2
docker pull grafana/loki:3.1.0
docker pull grafana/promtail:3.1.0
docker pull grafana/grafana:11.1.0
docker pull python:3.11-slim
```

---

## Part 0: Deploy the Observability Stack

Apply all infrastructure manifests. Order matters: the namespace must exist before other resources.

```bash
kubectl apply -f k8s/0-otel-collector.yaml   # creates namespace + OTel Collector
kubectl apply -f k8s/1-tempo.yaml
kubectl apply -f k8s/2-loki.yaml
kubectl apply -f k8s/4-promtail.yaml
kubectl apply -f k8s/5-grafana.yaml
```

Wait for everything to be ready:

```bash
kubectl get pods -n chain-reaction -w
```

Expected pods (all `Running`):
```
grafana-...         1/1   Running
loki-...            1/1   Running
otel-collector-...  1/1   Running
promtail-...        1/1   Running
tempo-...           1/1   Running
```

This may take 3–5 minutes on first run while images are pulled. Grafana, Tempo, and Loki are provisioned and linked — no manual datasource configuration needed.

---

## Part 1: Build and Deploy the Apps

```bash
eval $(minikube docker-env)
docker build -t chain-reaction-app:latest ./app
kubectl apply -f k8s/3-apps.yaml
```

Verify all three services are running:

```bash
kubectl get pods -n chain-reaction -l app=service-a
kubectl get pods -n chain-reaction -l app=service-b
kubectl get pods -n chain-reaction -l app=service-c
```

---

## Part 2: Generate Traffic

Port-forward Service-A and run a traffic loop:

```bash
kubectl port-forward -n chain-reaction svc/service-a 8000:8000
```

In a second terminal, keep traffic flowing:

```bash
while true; do curl -s http://localhost:8000/ | python3 -m json.tool; sleep 2; done
```

Notice the ~2 second response time. Each request chains A → B → C. Keep this running throughout the lab.

---

## Part 3: Find Your First Trace in Tempo

Open Grafana:

```bash
kubectl port-forward -n chain-reaction svc/grafana 3000:3000
```

Open **http://localhost:3000** → Login: `admin` / `admin`.

Go to **Connections → Data sources** — you should see **Tempo** and **Loki** already provisioned.

1. Left menu → **Explore**.
2. Select datasource: **Tempo**.
3. Switch query type to **TraceQL**.
4. Run:
   ```
   { resource.service.name = "service-a" }
   ```
5. Set time range to **Last 5 minutes**.
6. Click **Run query**.

You will see a list of traces. Click on one to open the **waterfall view**.

---

## Part 4: Read the Waterfall

The waterfall shows every span in the trace, arranged by time:

```
service-a: GET /          ████████████████████  2.1s  (root)
service-b: GET /request    ███████████████████  2.05s
service-c: GET /request     ██████████████████  2.0s   ← culprit
```

**Service-C** holds the request for 2 seconds. In production this would be a slow database query, lock contention, or external API call. The waterfall makes it immediately obvious without grepping logs from three separate services.

### TraceQL deep dive — find only slow traces

Back in Explore → Tempo, run:

```
{ resource.service.name = "service-c" && duration > 1.5s }
```

This returns only traces where Service-C's span took more than 1.5 seconds. In production you'd alert on this threshold.

---

## Part 5: Trace → Log Correlation

This is where the `trace_id` in every log line pays off.

### Via the Grafana "Logs" button (automatic)

In the Tempo waterfall view, look for the **Logs** button in the top-right of the trace panel (or on individual spans). Click it — Grafana automatically queries Loki for all log lines with that TraceID and displays them inline.

This works because `k8s/5-grafana.yaml` configures `tracesToLogsV2` in the Tempo datasource, telling Grafana to query the Loki datasource and filter by `trace_id`.

### Via manual LogQL (manual)

Copy the TraceID from the Tempo trace view (the 32-character hex string). In Explore → Loki, run:

```logql
{namespace="chain-reaction"} | json | trace_id="<paste-your-trace-id-here>"
```

You will see log lines from all three services (A, B, C) for that single request — the chain reaction in one view.

> **Why does `| json` work here?**  
> This lab's Promtail is configured with a `cri: {}` pipeline stage that unwraps the containerd log envelope before shipping to Loki. So Loki stores the app's raw JSON (not the outer wrapper), and `| json` correctly parses `trace_id`, `level`, `msg`, etc.

### Via the Loki "TraceID" link (automatic — other direction)

In Grafana Explore → Loki, run:

```logql
{namespace="chain-reaction", app="service-c"}
```

Expand a log line. You will see a **"TraceID"** field with a clickable link. Click it — Grafana jumps directly to that trace in Tempo. This is the `derivedFields` configuration in `k8s/5-grafana.yaml`.

The two-way linking means you can start your investigation from either side: a slow trace leads you to the logs, or an error log leads you to the trace.

---

## Part 6: Understand the Instrumentation Code

Open `app/service_a.py` (or look at all three — they use the same pattern).

**OTel setup:**

```python
resource = Resource.create({"service.name": "service-a"})
provider = TracerProvider(resource=resource)
provider.add_span_processor(BatchSpanProcessor(
    OTLPSpanExporter(endpoint="http://otel-collector:4318/v1/traces")
))
trace.set_tracer_provider(provider)
FastAPIInstrumentor.instrument_app(app)    # auto-instruments all HTTP endpoints
HTTPXClientInstrumentor().instrument()     # auto-injects traceparent into outgoing calls
```

`FastAPIInstrumentor` creates a span for every incoming HTTP request. `HTTPXClientInstrumentor` propagates the trace context into every outgoing `httpx` call — this is what creates the parent-child relationship between services.

**The correlation key:**

```python
def trace_id_filter(record):
    span = trace.get_current_span()
    ctx = span.get_span_context()
    record.trace_id = format(ctx.trace_id, "032x") if ctx.is_valid else ""
    return True

logger.addFilter(trace_id_filter)
```

This Python logging `Filter` runs before every log record is emitted. It reads the currently active OTel span context and stamps the `trace_id` (as a 32-char hex string) onto the log record. The `JsonFormatter` then includes it in the JSON output. Result: every log line for a request carries the same `trace_id` as the trace in Tempo.

Without this filter, metrics, logs, and traces would be three separate, uncorrelated data streams.

---

## Summary

| Phase | What you did |
|---|---|
| **0** | Deployed the full stack: OTel Collector, Tempo, Loki, Promtail, Grafana — all with pre-provisioned datasources and derived fields. |
| **1** | Built the instrumented app image and deployed three services into the `chain-reaction` namespace. |
| **2–3** | Generated traffic, found traces in Tempo using TraceQL, read the waterfall to identify Service-C as the latency source. |
| **4–5** | Correlated traces to logs via Grafana's automatic "Logs" button, manual LogQL with `trace_id`, and the Loki "TraceID" derived field link. |
| **6** | Studied how `FastAPIInstrumentor`, `HTTPXClientInstrumentor`, and `trace_id_filter` work together. |

**Key concepts to take away:**
- A trace is a tree of spans across service boundaries. Context propagation via the `traceparent` header stitches them together.
- The OTel Collector decouples apps from backends — apps speak OTLP once; the collector routes to any backend.
- TraceQL is to traces what PromQL is to metrics and LogQL is to logs.
- Stamping `trace_id` on every log line is what makes trace-log correlation possible. It's a one-time code change with permanent payoff.
- Grafana derived fields eliminate manual copy-paste — one click navigates between traces and logs in either direction.

---

## Cleanup

```bash
kubectl delete namespace chain-reaction
```

This removes everything in the lab — all deployments, services, ConfigMaps, and the namespace itself.

---

## Troubleshooting

### No traces in Tempo after generating traffic

1. Ensure traffic is actually reaching Service-A (the `curl` loop returns data).
2. Set the time range in Explore to **Last 5 minutes**.
3. Confirm the OTel Collector received spans:
   ```bash
   kubectl logs -n chain-reaction -l app=otel-collector --tail=20
   ```
   Look for `"msg":"Exporting items"`.
4. Confirm the app pods are using the latest image:
   ```bash
   eval $(minikube docker-env)
   docker build -t chain-reaction-app:latest ./app
   kubectl rollout restart deployment/service-a deployment/service-b deployment/service-c -n chain-reaction
   ```

### No logs in Loki / TraceID search returns empty

Check the Promtail logs for push activity:

```bash
kubectl logs -n chain-reaction -l app=promtail --tail=20
```

Look for `"msg":"send batch","status":204"`.

If Promtail reports `/var/log/pods` is empty (Minikube Docker driver issue), run:

```bash
minikube ssh "ls /var/log/pods"
```

If empty, your Minikube Docker driver isn't writing logs to the expected host path. Restart Minikube with a different driver:

```bash
minikube delete
minikube start --cpus=4 --memory=6144 --driver=docker
```

Or use the existing Loki + Promtail from lab3 (`monitoring` namespace): deploy `k8s/3-apps.yaml` into `monitoring` instead, and query with `{namespace="monitoring"}`.

### Grafana derived field "TraceID" link doesn't appear

The link appears only when a log line contains `"trace_id":"<32-char-hex>"`. If the app is running without a trace context (e.g. a startup log line logged before any request), `trace_id` will be an empty string and the link won't appear. Generate a request and look at post-startup log lines.
