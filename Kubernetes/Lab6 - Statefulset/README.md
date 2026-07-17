# Lab 6: Kubernetes StatefulSets

## Learning Objectives

By the end of this lab you will be able to:

1. Explain why Deployments are wrong for stateful workloads and what StatefulSets fix
2. Demonstrate the three StatefulSet guarantees: ordered deployment, stable identity, sticky storage
3. Explain how a Headless Service enables per-Pod DNS names
4. Write unique data to each Pod's volume and prove it survives Pod deletion
5. Observe ordered scale-down (reverse ordinal order)
6. Use the `partition` field to perform a canary rolling update

---

## Prerequisites

- Minikube running, `kubectl` configured
- Lab 5 completed — you should be comfortable with PVCs

---

## Core Concepts

### What Makes a Workload "Stateful"?

A workload is stateful when its Pods are **not interchangeable**:

- A database **primary** is different from a **replica** — they cannot swap identities mid-run
- A Kafka **broker-2** owns specific partitions — renaming it breaks the cluster
- A ZooKeeper node has a quorum ID baked into its configuration

**Deployments** are designed for *interchangeable* Pods. They get random names, start in any
order, and any Pod can replace any other. Perfect for web servers. Dangerous for databases.

**StatefulSets** give each Pod three guarantees a Deployment cannot provide:

| Guarantee | What it means |
|-----------|---------------|
| **Ordered deployment** | Pods start `0 → 1 → 2`. Each waits for the previous to be Running and Ready |
| **Stable identity** | Fixed names (`web-0`, `web-1`) and stable DNS hostnames — even after restarts |
| **Sticky storage** | A dedicated PVC per Pod that follows the Pod through deletion and recreation |

---

### Deployment vs StatefulSet Side-by-Side

| Property | Deployment | StatefulSet |
|----------|-----------|-------------|
| Pod names | Random: `web-9f8d2-xkl` | Ordinal: `web-0`, `web-1`, `web-2` |
| Startup order | All at once, any order | `0 → 1 → 2` strictly |
| Shutdown order | All at once, any order | `2 → 1 → 0` strictly |
| Storage | Shared PVC or none | One dedicated PVC per Pod |
| DNS per Pod | No | Yes, via Headless Service |
| Typical use | Stateless apps, APIs | Databases, Kafka, ZooKeeper, Elasticsearch |

---

### Headless Service and Per-Pod DNS

A normal Service (`clusterIP: 10.x.x.x`) load-balances across Pods — you can't address an
individual Pod by name.

A **Headless Service** (`clusterIP: None`) skips the load balancer. DNS returns the individual
Pod IPs directly, and Kubernetes registers a DNS record for each Pod:

```
web-0.nginx.lab6-statefulset.svc.cluster.local  →  10.x.x.1  (always web-0's IP)
web-1.nginx.lab6-statefulset.svc.cluster.local  →  10.x.x.2  (always web-1's IP)
web-2.nginx.lab6-statefulset.svc.cluster.local  →  10.x.x.3  (always web-2's IP)
```

These DNS names survive Pod restarts. If `web-1` is killed and rescheduled to a different node,
the record is updated to point to the new IP — but the name stays `web-1.nginx`.

---

### volumeClaimTemplates

A Deployment references an existing PVC in its `volumes` block — all replicas share it.
A StatefulSet uses `volumeClaimTemplates`: Kubernetes creates a **dedicated PVC per Pod**:

```
web-0  →  PVC "www-web-0"  (created automatically)
web-1  →  PVC "www-web-1"  (created automatically)
web-2  →  PVC "www-web-2"  (created automatically)
```

These PVCs are **not deleted** when a Pod is deleted. When the Pod is recreated, it is
automatically re-bound to its own PVC. The data is always there.

---

### podManagementPolicy

| Value | Behavior |
|-------|----------|
| `OrderedReady` (default) | Create/delete one Pod at a time in order. Each must be Ready before the next starts. |
| `Parallel` | Create or delete all Pods at once. Useful for quick bootstrapping. Loses ordering. |

---

### updateStrategy and partition

StatefulSet rolling updates run in **reverse** ordinal order: `2 → 1 → 0`.

The `partition` field enables **canary deployments**: set `partition: 2` and trigger an update
— only `web-2` (ordinal ≥ 2) gets the new image. Validate it, then lower the partition to
roll out to the rest.

---

## Setup

```bash
kubectl apply -f k8s/01-namespace.yaml
kubectl apply -f k8s/02-headless-service.yaml
```

---

## Part 1: Ordered Startup

Deploy the StatefulSet and watch Pods come up one at a time:

```bash
kubectl apply -f k8s/03-statefulset.yaml

kubectl get pods -n lab6-statefulset -w
```

You should see Pods appear strictly in order:

```
NAME    READY   STATUS              ...
web-0   0/1     ContainerCreating   ...
web-0   1/1     Running             ...   ← web-1 only starts after web-0 is Ready
web-1   0/1     ContainerCreating   ...
web-1   1/1     Running             ...   ← web-2 only starts after web-1 is Ready
web-2   0/1     ContainerCreating   ...
web-2   1/1     Running             ...
```

Press `Ctrl+C` once all three are Running.

### Verify each Pod got its own dedicated PVC

```bash
kubectl get pvc -n lab6-statefulset
```

Expected:
```
NAME        STATUS   VOLUME   CAPACITY   ACCESS MODES
www-web-0   Bound    ...      256Mi      RWO
www-web-1   Bound    ...      256Mi      RWO
www-web-2   Bound    ...      256Mi      RWO
```

Three Pods, three PVCs — each exclusively owned by one Pod. A Deployment with 3 replicas would
have all replicas sharing a single PVC, or each Pod getting no persistent storage at all.

---

## Part 2: Stable Network Identity

### Stable hostnames

Each Pod's hostname is fixed and matches its ordinal name:

```bash
for i in 0 1 2; do
  echo -n "web-$i hostname: "
  kubectl exec web-$i -n lab6-statefulset -- hostname
done
```

Expected:
```
web-0 hostname: web-0
web-1 hostname: web-1
web-2 hostname: web-2
```

In a Deployment, the hostname is the same random string as the Pod name — and it changes
every time the Pod is replaced.

### Per-Pod DNS via the Headless Service

Run a temporary debug Pod inside the cluster to resolve each Pod's DNS name:

```bash
kubectl run dns-test -n lab6-statefulset \
  --image=busybox:1.36 --restart=Never --rm -it \
  -- sh -c "
    for i in 0 1 2; do
      echo '--- web-'\$i' ---'
      nslookup web-\$i.nginx
    done
  "
```

Each lookup should return a **different IP** — one per Pod.

> **DNS format:** `<pod-name>.<service-name>.<namespace>.svc.cluster.local`
>
> Within the same namespace the short form `web-0.nginx` resolves because Kubernetes
> DNS search domains automatically append the namespace suffix.

---

## Part 3: Per-Pod Sticky Storage

This is the core proof of the lab. Write **different content** to each Pod's volume and
demonstrate that storage is isolated — not shared across Pods.

### Write unique content to each Pod's volume

```bash
for i in 0 1 2; do
  kubectl exec web-$i -n lab6-statefulset -- \
    sh -c "echo '<h1>I am web-$i | PVC: www-web-$i</h1>' > /usr/share/nginx/html/index.html"
done
```

### Verify each Pod serves its own unique page

```bash
for i in 0 1 2; do
  echo "=== web-$i ==="
  kubectl exec web-$i -n lab6-statefulset -- curl -s localhost
done
```

Expected:
```
=== web-0 ===
<h1>I am web-0 | PVC: www-web-0</h1>
=== web-1 ===
<h1>I am web-1 | PVC: www-web-1</h1>
=== web-2 ===
<h1>I am web-2 | PVC: www-web-2</h1>
```

Each Pod is serving content from its own dedicated volume — not a shared one.

---

## Part 4: Sticky Storage Survives Pod Deletion

Delete `web-1` and prove that when Kubernetes recreates it, it gets **its own PVC back** —
not a fresh empty volume, and not another Pod's data.

```bash
kubectl delete pod web-1 -n lab6-statefulset

# Watch web-1 be automatically recreated
kubectl get pods -n lab6-statefulset -w
# Ctrl+C when web-1 is Running again
```

Now check what `web-1` serves:

```bash
kubectl exec web-1 -n lab6-statefulset -- curl -s localhost
```

**Expected:** `<h1>I am web-1 | PVC: www-web-1</h1>`

`web-1` was automatically re-bound to `www-web-1`. The data is intact.

**This is what a Deployment cannot do.** A replaced Deployment Pod has no fixed identity —
it would get a fresh empty volume. It has no concept of "I am replica 1 and I own this
specific data."

---

## Part 5: Ordered Shutdown — Scale Down

Scale from 3 to 1. Watch Pods be removed in **reverse** ordinal order.

```bash
kubectl scale statefulset web --replicas=1 -n lab6-statefulset

kubectl get pods -n lab6-statefulset -w
# Ctrl+C when only web-0 remains
```

Expected deletion order:
```
web-2   Terminating   ← deleted first
web-2   (gone)
web-1   Terminating   ← deleted only after web-2 is fully terminated
web-1   (gone)
```

Now check the PVCs:

```bash
kubectl get pvc -n lab6-statefulset
```

All three PVCs still exist. Scaling down does **not** delete PVCs — the data on `www-web-1`
and `www-web-2` is preserved. Scale back up to prove it:

```bash
kubectl scale statefulset web --replicas=3 -n lab6-statefulset
kubectl get pods -n lab6-statefulset -w
# Ctrl+C when all three are Running

# web-1 and web-2 should still have their data
for i in 1 2; do
  echo "=== web-$i ==="
  kubectl exec web-$i -n lab6-statefulset -- curl -s localhost
done
```

---

## Part 6: Canary Rolling Update with partition

StatefulSet rolling updates run in reverse ordinal order and support the `partition` field
for controlled, canary-style rollouts.

### Step 1 — Update only web-2 (the canary)

```bash
# partition=2: only pods with ordinal >= 2 receive the new image
kubectl patch statefulset web -n lab6-statefulset \
  -p '{"spec":{"updateStrategy":{"rollingUpdate":{"partition":2}}}}'

# Trigger the update
kubectl set image statefulset/web nginx=nginx:1.27-alpine -n lab6-statefulset

kubectl rollout status statefulset/web -n lab6-statefulset
```

### Step 2 — Verify only web-2 was updated

```bash
kubectl get pods -n lab6-statefulset \
  -o custom-columns='NAME:.metadata.name,IMAGE:.spec.containers[0].image'
```

Expected:
```
NAME    IMAGE
web-0   nginx:1.27           ← old image, untouched
web-1   nginx:1.27           ← old image, untouched
web-2   nginx:1.27-alpine    ← canary: only highest ordinal updated
```

Validate `web-2` (check logs, responses) before proceeding.

### Step 3 — Complete the rollout

```bash
# Lower partition to 0 — all pods are now eligible for the update
kubectl patch statefulset web -n lab6-statefulset \
  -p '{"spec":{"updateStrategy":{"rollingUpdate":{"partition":0}}}}'

kubectl rollout status statefulset/web -n lab6-statefulset
```

Update proceeds `web-1 → web-0` (reverse ordinal, skipping `web-2` which is already done).

---

## Summary & Key Takeaways

### The Three StatefulSet Guarantees

| Guarantee | Mechanism | What breaks without it |
|-----------|-----------|------------------------|
| **Ordered deployment** | `podManagementPolicy: OrderedReady` | Replica 1 connects to a primary before it's ready |
| **Stable identity** | Fixed ordinal names + Headless Service | Kafka brokers lose partition ownership on restart |
| **Sticky storage** | `volumeClaimTemplates` | Pod gets empty volume on recreation — data lost |

### Rolling update order

| Operation | Deployment | StatefulSet |
|-----------|-----------|-------------|
| Scale up | All at once | `0 → 1 → 2` |
| Scale down | All at once | `2 → 1 → 0` |
| Rolling update | Any order | `2 → 1 → 0` |
| Canary update | Not built-in | `partition` field |

### When to use StatefulSet vs Deployment

**Use a StatefulSet when:**
- Each replica needs a distinct identity (database primary/replica, Kafka broker IDs)
- Each replica needs its own dedicated persistent storage
- Startup or shutdown order matters (e.g. ZooKeeper quorum formation)

**Use a Deployment when:**
- All replicas are identical and interchangeable (web servers, API services)
- You need simple horizontal scaling with no per-replica storage
- Pods can start and stop in any order

---

## Cleanup

```bash
# Deleting the namespace removes Pods, StatefulSet, Service, and PVCs
kubectl delete namespace lab6-statefulset

# Check if PVs were also cleaned up (depends on StorageClass reclaim policy)
kubectl get pv | grep www-web
```

> If PVs show `Released` instead of being deleted, the StorageClass reclaim policy is `Retain`.
> Delete them manually: `kubectl delete pv <name>`

---

## The Exercise

### 1. Headless Service (`nginx-service.yaml`)

StatefulSets need a **Headless Service** so that:

- The control plane can track and manage the Pods
- Each Pod gets a stable DNS name: `<pod-name>.<service-name>.<namespace>.svc.cluster.local`

**Headless** means `clusterIP: None`: no single Cluster IP. DNS returns the **individual Pod IPs**, so clients can reach `web-0`, `web-1`, `web-2` by name.

### 2. StatefulSet (`nginx-statefulset.yaml`)

The StatefulSet defines:

- **3 replicas** of Nginx
- **volumeClaimTemplate**: each Pod gets its **own** 1Gi PVC (e.g. `www-web-0`, `www-web-1`, `www-web-2`)
- **Stable names**: Pods are named `web-0`, `web-1`, `web-2` and keep those names and their volumes for their lifetime

---

## Deployment

Apply both manifests:

```bash
kubectl apply -f k8s/nginx-service.yaml -f k8s/nginx-statefulset.yaml
```

---

## Verification

### 1. Pod creation order

Pods are created **one by one**, in order (0, then 1, then 2):

```bash
kubectl get pods -w -l app=nginx
```

You should see `web-0` become Running, then `web-1`, then `web-2`. This is **ordered, graceful** rollout.

### 2. Stable hostnames

Each Pod has a **unique, stable** hostname that matches its name:

```bash
for i in 0 1 2; do kubectl exec web-$i -- hostname; done
```

Expected output:

```
web-0
web-1
web-2
```

### 3. Stable DNS

From another Pod in the cluster you can resolve:

- `web-0.nginx`
- `web-1.nginx`
- `web-2.nginx`

These names are stable even if a Pod is rescheduled.

### 4. One PV per Pod (sticky storage)

Each replica has its **own** PVC, created from the `volumeClaimTemplate`:

```bash
kubectl get pvc -l app=nginx
```

You should see three PVCs (e.g. `www-web-0`, `www-web-1`, `www-web-2`), each bound to a PV. Storage is **sticky**: when `web-1` is recreated, it gets the same PVC and the same data.

---

## Summary

| Feature            | StatefulSet behavior |
|--------------------|----------------------|
| **Ordering**       | Pods created/updated in order (0 → 1 → 2) |
| **Stable identity** | Fixed names and hostnames (web-0, web-1, web-2) |
| **Stable DNS**     | Headless Service gives each Pod a stable DNS name |
| **Sticky storage** | Each Pod has its own PVC from the volumeClaimTemplate |

---

## Cleanup

```bash
kubectl delete -f k8s/nginx-statefulset.yaml -f k8s/nginx-service.yaml
kubectl get pvc   # Delete any remaining PVCs if needed: kubectl delete pvc -l app=nginx
```
