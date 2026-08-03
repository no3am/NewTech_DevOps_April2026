# Lab 4 — Mimir: Long-Term Metrics Storage

## Learning Objectives

By the end of this lab you will be able to:

1. Explain the **Prometheus retention problem** and why long-term metric storage is needed.
2. Describe how **remoteWrite** works — what Prometheus pushes, where, and when.
3. Deploy **Grafana Mimir** in monolithic mode and understand what each config block does.
4. Configure Prometheus to write to Mimir using the `helm upgrade --reuse-values` pattern.
5. Query Mimir from Grafana using the **Prometheus-compatible API** and compare results with the local Prometheus datasource.

---

## The Problem Mimir Solves

By default Prometheus keeps data for **15 days** on a local volume. For most labs that's fine, but in production two problems appear quickly:

1. **Data loss on restart.** If the Prometheus pod is deleted or the node dies, the local TSDB (time-series database) goes with it. RemoteWrite solves this by writing every scraped sample to durable external storage in real time.

2. **No long-term trends.** Capacity planning, quarterly reports, and SLO calculations often need months of history. 15 days isn't enough.

**Mimir** is Grafana's open-source, horizontally scalable, long-term metrics store. It accepts data via the same **Prometheus remote write protocol** and exposes a **Prometheus-compatible query API** — so the same PromQL you already know works unchanged, just with a longer time window.

---

## Core Concepts

### remoteWrite — The Push Side

Prometheus has a built-in mechanism to push data out as it scrapes. After each scrape cycle, Prometheus:

1. Writes samples to its local TSDB (short-term, ~15 days default).
2. Simultaneously sends the same samples to any configured `remoteWrite` endpoints via HTTP POST.

The payload uses the [Prometheus Remote Write protocol](https://prometheus.io/docs/concepts/remote_write_spec/) — a Snappy-compressed protobuf of `(labels, timestamp, value)` tuples. Mimir's **distributor** receives this at `/api/v1/push`.

```
                   every scrape cycle
Prometheus ────────────────────────────► Local TSDB  (short-term, default 15 days)
           │
           └── remoteWrite ───────────► Mimir /api/v1/push  (long-term)
```

### Mimir's Prometheus-Compatible API — The Query Side

Mimir exposes a `/prometheus` path that mirrors the Prometheus HTTP API exactly. That means:

- `GET /prometheus/api/v1/query` — instant query
- `GET /prometheus/api/v1/query_range` — range query
- `GET /prometheus/api/v1/labels` — label names

Grafana treats Mimir exactly like a Prometheus datasource. Switch a panel's datasource from Prometheus to Mimir and the same PromQL returns data — just from the long-term store.

### Monolithic Mode (`-target=all`)

Mimir has a distributed architecture with separate components: distributor, ingester, querier, compactor, store-gateway. For production you'd run these independently (more replicas, separate scaling). For a lab, `-target=all` runs all components in a single process, making it trivial to deploy and debug.

### TSDB Blocks

Mimir stores data as immutable **2-hour blocks** (same format as Prometheus TSDB). The compactor periodically merges small blocks into larger ones and deletes old data beyond the retention period. In this lab blocks live on a local `emptyDir` — they're lost if the pod restarts, which is fine for learning. In production you'd point the blocks at an object store (S3, GCS, Azure Blob).

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  namespace: monitoring                                               │
│                                                                      │
│  ┌─────────────────┐  scrape    ┌─────────────────┐                 │
│  │ payment-processor│──────────►│   Prometheus     │                │
│  │  /metrics        │           │   (local TSDB    │                │
│  └─────────────────┘           │    ~15d default)  │                │
│                                 └────────┬──────────┘               │
│                                          │ remoteWrite               │
│                                          │ POST /api/v1/push         │
│                                          ▼                           │
│                                 ┌─────────────────┐                 │
│                                 │      Mimir       │                 │
│                                 │  (monolithic,    │                 │
│                                 │  filesystem      │                 │
│                                 │  long-term)      │                 │
│                                 └────────┬─────────┘                │
│                                          │ /prometheus query API     │
│                                          │                           │
│             ┌────────────────────────────┴──────────────────┐       │
│             │                  Grafana                       │       │
│             │  datasource: Prometheus ──► short-term PromQL │       │
│             │  datasource: Loki       ──► LogQL              │       │
│             │  datasource: Mimir      ──► long-term PromQL  │       │
│             └────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

- **Lab 3 complete:** kube-prometheus-stack running in the `monitoring` namespace, payment-processor and traffic-generator deployed.
- `helm` and `kubectl` configured.

### Pre-pull the Mimir image

```bash
eval $(minikube docker-env)
docker pull grafana/mimir:2.12.0
```

---

## Part 0: Deploy Mimir

Apply the Mimir manifest — it creates a ConfigMap (Mimir's config), a Deployment, and a ClusterIP Service:

```bash
kubectl apply -f k8s/4-mimir.yaml
```

Wait for the pod to be ready:

```bash
kubectl get pods -n monitoring -l app=mimir -w
```

Ctrl-C when you see `1/1 Running`. Mimir is now listening on **port 8080** but isn't receiving any data yet — Prometheus doesn't know about it.

**Verify the API is up:**

```bash
kubectl run -n monitoring curl-test --rm -it --restart=Never --image=curlimages/curl \
  -- curl -s http://mimir-service.monitoring.svc.cluster.local:8080/ready
```

Should return `ready`. On first startup you may briefly see:

```
Ingester not ready: waiting for 15s after being ready
```

That's normal — Mimir's ingester has a built-in 15-second warm-up after all components initialize. Wait a few seconds and curl again. If it doesn't return `ready` after 30 seconds, check the pod logs:

```bash
kubectl logs -n monitoring -l app=mimir --tail=30
```

---

## Part 1: Wire Prometheus → Mimir

This is the critical step. You will **upgrade** the existing kube-prometheus-stack release to:
1. Add `remoteWrite` to Prometheus's config (data pipeline).
2. Provision the Mimir datasource in Grafana (no manual UI clicking).

The upgrade uses `--reuse-values` so every setting from the original install (disabled components, `adminPassword: admin`, Loki datasource, `serviceMonitorSelector: {}`) is preserved. The values file only **adds** new configuration on top.

```bash
helm upgrade monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --reuse-values \
  -f k8s/5-prometheus-values.yaml
```

### What `5-prometheus-values.yaml` adds

```
prometheus.prometheusSpec.remoteWrite:
  - url: http://mimir-service.monitoring.svc.cluster.local:8080/api/v1/push
```

Prometheus will start pushing every scraped sample to that URL immediately — no restart needed.

```
grafana.additionalDataSources:
  - name: Mimir   (type: prometheus, url: .../prometheus)
  - name: Loki    (re-declared to prevent Helm from removing it)
```

> **Why re-declare Loki?** Helm's `additionalDataSources` is a list. If you only specify Mimir in the upgrade values, Helm replaces the entire list and Loki disappears. Re-declaring both is the correct pattern.

After the upgrade, Grafana's sidecar needs to reload the new datasource ConfigMap. If Mimir doesn't appear in **Connections → Data sources** within 30 seconds, restart the Grafana pod:

```bash
kubectl rollout restart deployment/monitoring-grafana -n monitoring
kubectl rollout status deployment/monitoring-grafana -n monitoring
```

Then re-run the port-forward (the old one dies when the pod restarts):

```bash
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
```

### Verify Prometheus is sending data

Wait about 30 seconds after the upgrade, then check the Prometheus remote write stats:

```bash
kubectl port-forward -n monitoring svc/monitoring-kube-prometheus-prometheus 9090:9090
```

Open **http://localhost:9090/graph** and query:

```promql
prometheus_remote_storage_samples_total
```

A non-zero, increasing value confirms Prometheus is writing to Mimir. You can also check:

```promql
prometheus_remote_storage_queue_highest_sent_timestamp_seconds
```

If this is recent (within the last minute), the pipeline is healthy.

Kill the port-forward when done.

---

## Part 2: Query Mimir from Grafana

```bash
kubectl port-forward -n monitoring svc/monitoring-grafana 3000:80
```

Open **http://localhost:3000** (login: `admin` / `admin`).

Go to **Connections → Data sources**. You should now see three datasources: **Prometheus**, **Loki**, and **Mimir** — all provisioned, no manual setup needed.

### Compare the two metric datasources side by side

1. Left menu → **Explore**.
2. Click **Split** to open two panels.
3. **Left panel** — datasource: **Prometheus**, query:
   ```promql
   sum(rate(http_requests_total[1m]))
   ```
4. **Right panel** — datasource: **Mimir**, same query:
   ```promql
   sum(rate(http_requests_total[1m]))
   ```
5. Click **Run query** on both.

Both panels should show the same shape and values. The data is identical — Prometheus scraped it, wrote it locally AND pushed it to Mimir simultaneously. You're now reading from two independent stores with the same PromQL.

### The retention gap — why remoteWrite from day one matters

In Explore (split view), set the time range to **before you ran the `helm upgrade`** (the time when remoteWrite was not yet configured).

- **Prometheus (left):** Shows data — it has been scraping and storing locally since the app was deployed.
- **Mimir (right):** Shows nothing — it only has data from the moment remoteWrite was turned on.

Now set the range to **after the upgrade**. Both panels show matching data.

This is the key lesson: Prometheus does **not** backfill historical data to Mimir when you add remoteWrite. It only pushes new samples going forward. In production, remoteWrite should be configured from day one — not added retroactively when you realise you need long-term history.

---

## Part 3: PromQL Challenges

**Challenge 1 — Error rate from Mimir:**

Run this in the **Mimir** datasource:

```promql
sum(rate(http_requests_total{status="500"}[1m]))
```

Same result as from Prometheus (for the overlapping time window)? It should be — data is mirrored via remoteWrite.

**Challenge 2 — Total request volume per status code:**

```promql
sum by (status) (increase(http_requests_total[5m]))
```

Run this in both Prometheus and Mimir. Do the numbers match?

**Challenge 3 — Check remoteWrite lag**

Back in the **Prometheus** datasource, query:

```promql
prometheus_remote_storage_highest_timestamp_in_seconds
- 
prometheus_remote_storage_queue_highest_sent_timestamp_seconds
```

This is the lag in seconds between what Prometheus has scraped and what it has successfully delivered to Mimir. A healthy value is **< 30 seconds**. If it's growing over time, Mimir's ingester can't keep up with the write rate — something an on-call engineer would page on.

**Challenge 4 — Build a Mimir-backed dashboard**

1. Left menu → **Dashboards** → **New dashboard** → **Add visualization**.
2. Set the datasource to **Mimir**.
3. Add this query:
   ```promql
   sum(rate(http_requests_total[1m]))
   ```
4. Set panel title to `Total request rate (from Mimir)`.
5. Save the dashboard as `Mimir — Payment Processor`.

This is the production pattern: dashboards for long-term capacity analysis are explicitly wired to the long-term store (Mimir), while real-time alert dashboards use the local Prometheus. They can coexist in the same Grafana instance.

---

## Part 4: Peek Inside Mimir (Bonus)

Mimir exposes a UI at `/mimir-ui` on port 8080:

```bash
kubectl port-forward -n monitoring svc/mimir-service 8080:8080
```

Open **http://localhost:8080/mimir-ui/**. You'll see:

- **Ring** pages — show the hash-ring state for each component (distributor, ingester, etc.)
- **Config** — the running configuration
- **Runtime config** — per-tenant overrides

Because we're running in monolithic mode (`-target=all`) with a single replica, each ring will show exactly one member. In production with distributed mode you'd see multiple members distributing the load.

---

## Summary

| Step | What you did |
|---|---|
| **0** | Deployed Mimir (monolithic, `grafana/mimir:2.12.0`) with ConfigMap, Deployment, and Service. Verified `/ready` endpoint. |
| **1** | Upgraded kube-prometheus-stack with `--reuse-values` to add `remoteWrite` to Mimir and provision the Mimir datasource in Grafana. |
| **2** | Compared Prometheus vs Mimir in Explore split view. Observed the retention gap — Mimir only holds data from when remoteWrite was enabled. |
| **3** | Checked remoteWrite lag via `prometheus_remote_storage` metrics. Built a Mimir-backed dashboard for long-term capacity analysis. |

**Key concepts to take away:**
- Prometheus's local TSDB is ephemeral and short-lived. RemoteWrite sends data to durable external storage in real time — configure it from day one.
- Mimir exposes the same Prometheus HTTP API — no new query language to learn.
- `helm upgrade --reuse-values -f file.yaml` is the safe pattern for adding config to an existing release without wiping previous settings.
- List values (like `additionalDataSources`) are replaced on upgrade — always re-declare the full list.
- In production, wire long-term dashboards to Mimir and real-time alert dashboards to Prometheus — both live in the same Grafana.

---

## Cleanup

```bash
# Remove Mimir
kubectl delete -f k8s/4-mimir.yaml

# Roll back Prometheus remoteWrite and Mimir datasource
helm upgrade monitoring prometheus-community/kube-prometheus-stack \
  --namespace monitoring \
  --reuse-values \
  --set prometheus.prometheusSpec.remoteWrite=null

# Or to clean up the full lab3+4 stack:
helm uninstall promtail -n monitoring
helm uninstall loki -n monitoring
helm uninstall monitoring -n monitoring
kubectl delete namespace monitoring
```
