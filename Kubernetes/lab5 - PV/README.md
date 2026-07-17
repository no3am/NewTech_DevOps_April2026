# Lab 5: Kubernetes Persistent Storage — PVs, PVCs & StorageClasses

## Learning Objectives

By the end of this lab you will be able to:

1. Explain why container storage is ephemeral and why this breaks stateful apps
2. Use `emptyDir` for intra-Pod shared storage and understand its limits
3. Read and write the **PV → PVC → StorageClass** abstraction model
4. Distinguish between **static** (manual) and **dynamic** (StorageClass-driven) provisioning
5. Correctly use the three access modes (`RWO`, `ROX`, `RWX`)
6. Choose the right reclaim policy (`Delete` vs `Retain`) for a workload
7. Store database credentials in a **Secret** instead of plaintext environment variables

---

## Prerequisites

- Minikube running: `minikube start`
- `kubectl` configured: `kubectl cluster-info`
- Familiarity with Pods and Deployments (Labs 1–4)

---

## Core Concepts

### Why Does Storage Matter in Kubernetes?

Every Pod gets a writable **overlay filesystem** layered on top of its container image.  
This filesystem is **completely ephemeral**:

- It is destroyed when the Pod is deleted (intentionally, by a scheduler, or on a node failure)
- A brand-new Pod gets a **blank** overlay filesystem — previous data is gone
- This is perfect for stateless apps (web servers, APIs)
- This is catastrophic for stateful apps (databases, file stores, message queues)

Kubernetes solves this with **Volumes**.

---

### The Kubernetes Storage Model

```
┌──────────────────────────────────────────────────────────────────┐
│                         CLUSTER                                  │
│                                                                  │
│  StorageClass ──── (automatically provisions) ──────► PV        │
│  e.g. "standard"                                   (the actual  │
│                                                     storage)    │
│                                                         ▲       │
│                                                    binds│       │
│                                                         │       │
│  Pod ─────── volumeMount ──────────────────────► PVC   │       │
│  (App)                                         (request│       │
│                                                 for    │       │
│                                                 storage)        │
└──────────────────────────────────────────────────────────────────┘
```

| Object | Who creates it | What it represents |
|--------|----------------|-------------------|
| **PV** (PersistentVolume) | Admin or StorageClass | The actual storage resource (a disk, an NFS share, a cloud volume) |
| **PVC** (PersistentVolumeClaim) | Developer / App manifests | A *request* for storage. Decouples apps from the storage backend |
| **StorageClass** | Admin | A template that tells Kubernetes *how* to provision PVs on-demand |

**The key insight:** Developers write PVCs (how much, what access mode). Admins configure
StorageClasses and/or create PVs. Neither side needs to know the implementation details of the other.

---

### Volume Types Covered in This Lab

| Type | Lifecycle | Use Case |
|------|-----------|----------|
| `emptyDir` | Lives and dies with the **Pod** | Sharing temp files between containers in the same Pod |
| `hostPath` | Lives on the **node** | Dev/testing only — ties your Pod to a specific node |
| **PVC + PV** | Independent of Pod lifecycle | Any workload that must outlive its Pod |

---

### Access Modes

A PV advertises which access modes it supports. A PVC requests one of them.

| Mode | Short | Meaning |
|------|-------|---------|
| `ReadWriteOnce` | **RWO** | Mounted read-write by **one node** at a time |
| `ReadOnlyMany` | **ROX** | Mounted read-only by **many nodes** simultaneously |
| `ReadWriteMany` | **RWX** | Mounted read-write by **many nodes** simultaneously |

> Most cloud block storage (AWS EBS, GCP Persistent Disk, Azure Disk) supports **RWO only**.  
> NFS and specialized CSI drivers support **RWX**.  
> Postgres should always use **RWO** — only one writer at a time is safe.

---

### Reclaim Policies

When a PVC is deleted, what happens to the PV?

| Policy | Behavior | When to use |
|--------|----------|-------------|
| `Delete` | PV **and** the underlying storage are deleted automatically | Cloud volumes in dev/test environments |
| `Retain` | PV stays. Data is preserved. Admin must clean up manually | **Production databases** — never auto-delete data |

> **Warning:** Dynamic provisioning (StorageClass) often defaults to `Delete`. Always check the
> reclaim policy before deploying a production stateful workload.

---

## Lab Setup

All resources in this lab live in a dedicated namespace to keep things isolated.

```bash
kubectl apply -f k8s/01-namespace.yaml
kubectl get namespace lab5-storage
```

---

## Part 1: emptyDir — Intra-Pod Shared Storage

`emptyDir` is the simplest Kubernetes volume. It is created when a Pod is scheduled onto a node
and deleted when that Pod leaves the node (for any reason).

**It is NOT persistent storage.** It is useful for:
- Sharing files between sidecar containers in the same Pod
- Cache or scratch space within a single Pod's lifetime
- Passing data between an init container and the main container

### 1.1 Deploy the demo Pod

This Pod has two containers sharing one `emptyDir` volume:
- **writer** — appends a timestamped line to `/shared/log.txt` every 3 seconds
- **reader** — prints the file contents every 3 seconds

```bash
kubectl apply -f k8s/02-emptydir-demo.yaml
kubectl get pod emptydir-demo -n lab5-storage
```

### 1.2 Watch the containers share data

```bash
# Follow the reader container — it reads what the writer writes
kubectl logs -f emptydir-demo -c reader -n lab5-storage
```

You should see timestamped lines appearing every few seconds. Press `Ctrl+C` to stop.

Two containers. One volume. No persistent storage — but real-time sharing.

### 1.3 Prove emptyDir is ephemeral

```bash
# Delete the Pod
kubectl delete pod emptydir-demo -n lab5-storage

# Re-create it
kubectl apply -f k8s/02-emptydir-demo.yaml

# Check the reader logs — the file starts fresh with no old entries
kubectl logs emptydir-demo -c reader -n lab5-storage
```

**Takeaway:** `emptyDir` data disappears when the Pod is deleted. It *does* survive container
restarts within a Pod (e.g. an OOMKill), but not Pod deletion.

---

## Part 2: The Problem — Stateless Postgres (Data Loss)

Now let's see what happens when a real database runs without any volume.

First, apply the Secret that holds the Postgres credentials (we'll reuse this throughout the lab):

```bash
kubectl apply -f k8s/04-postgres-secret.yaml
```

> **Why a Secret?** Putting credentials in a Secret keeps them out of plaintext YAML files,
> decouples config from application manifests, and lets Kubernetes handle base64 encoding.
> Never hardcode passwords in `env` blocks of Deployment specs.

### 2.1 Deploy Postgres with no volume

```bash
kubectl apply -f k8s/03-postgres-no-volume.yaml
kubectl get pods -l app=postgres-no-vol -n lab5-storage
```

Wait for `Running`, then connect and create some data:

```bash
kubectl exec -it \
  $(kubectl get pod -l app=postgres-no-vol -n lab5-storage -o jsonpath='{.items[0].metadata.name}') \
  -n lab5-storage \
  -- psql -U labuser -d labdb -c "
    CREATE TABLE employees (id SERIAL PRIMARY KEY, name TEXT, role TEXT);
    INSERT INTO employees (name, role) VALUES ('Alice', 'Engineer'), ('Bob', 'DevOps');
    SELECT * FROM employees;
  "
```

Expected output:
```
 id | name  |   role
----+-------+----------
  1 | Alice | Engineer
  2 | Bob   | DevOps
(2 rows)
```

### 2.2 Simulate a Pod crash

```bash
# Delete the Pod — the Deployment will immediately create a replacement
kubectl delete pod -l app=postgres-no-vol -n lab5-storage

# Watch the replacement start up
kubectl get pods -l app=postgres-no-vol -n lab5-storage -w
# Press Ctrl+C when you see Running
```

### 2.3 Check for your data

```bash
kubectl exec -it \
  $(kubectl get pod -l app=postgres-no-vol -n lab5-storage -o jsonpath='{.items[0].metadata.name}') \
  -n lab5-storage \
  -- psql -U labuser -d labdb -c "SELECT * FROM employees;"
```

**Result:** `ERROR: relation "employees" does not exist`

Alice and Bob are gone. The new Pod got a fresh container filesystem. Postgres re-initialized
from scratch. This is the problem persistent volumes solve.

---

## Part 3: Static Provisioning — Manual PV + PVC

In **static provisioning**, an admin pre-creates a `PersistentVolume`. A developer then creates a
`PVC` that matches it. Kubernetes **binds** them together.

```
Admin role:      kubectl apply -f 05-manual-pv.yaml       → PV created (Available)
Developer role:  kubectl apply -f 06-manual-pvc.yaml      → PVC created → K8s binds PVC ↔ PV
App:             kubectl apply -f 07-postgres-manual-pv.yaml → Pod mounts PVC
```

### 3.1 Create the PV (admin role)

```bash
kubectl apply -f k8s/05-manual-pv.yaml
kubectl get pv postgres-pv-manual
```

Expected output:
```
NAME               CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS      STORAGECLASS
postgres-pv-manual 1Gi        RWO            Retain           Available   manual
```

`STATUS: Available` — the PV exists but has not been claimed by anything yet.  
`RECLAIM POLICY: Retain` — if the PVC is deleted, this PV (and its data) will NOT be deleted.

### 3.2 Create the PVC (developer role)

```bash
kubectl apply -f k8s/06-manual-pvc.yaml
```

Immediately check both objects:

```bash
kubectl get pv postgres-pv-manual
kubectl get pvc postgres-pvc-manual -n lab5-storage
```

Both should now show `STATUS: Bound`. Kubernetes matched the PVC to the PV because:
- `storageClassName` on both is `manual`
- The PVC's access mode (`RWO`) is supported by the PV
- The requested capacity (`1Gi`) fits within the PV's capacity (`1Gi`)

### 3.3 Deploy Postgres with the manual PV

```bash
kubectl apply -f k8s/07-postgres-manual-pv.yaml
kubectl get pods -l app=postgres-manual -n lab5-storage -w
# Ctrl+C when Running
```

> **`subPath` explained:** The manifest uses `subPath: pgdata`. This mounts only a subdirectory
> called `pgdata/` inside the PVC volume to `/var/lib/postgresql/data`. Without this, Postgres
> can fail because it expects an empty or Postgres-owned directory root — and hostPath volumes
> can contain other files. Using `subPath` isolates Postgres's data into its own clean subdirectory.

### 3.4 Create data and prove persistence

```bash
kubectl exec -it \
  $(kubectl get pod -l app=postgres-manual -n lab5-storage -o jsonpath='{.items[0].metadata.name}') \
  -n lab5-storage \
  -- psql -U labuser -d labdb -c "
    CREATE TABLE employees (id SERIAL PRIMARY KEY, name TEXT, role TEXT);
    INSERT INTO employees (name, role) VALUES ('Carol', 'SRE'), ('Dave', 'Architect');
    SELECT * FROM employees;
  "
```

Delete the Pod and let it be recreated:

```bash
kubectl delete pod -l app=postgres-manual -n lab5-storage

kubectl get pods -l app=postgres-manual -n lab5-storage -w
# Ctrl+C when Running
```

Query the data again:

```bash
kubectl exec -it \
  $(kubectl get pod -l app=postgres-manual -n lab5-storage -o jsonpath='{.items[0].metadata.name}') \
  -n lab5-storage \
  -- psql -U labuser -d labdb -c "SELECT * FROM employees;"
```

**Result:** Carol and Dave are still there. The new Pod mounted the same PVC, which points to the
same PV, which stores the actual Postgres data files on the node.

### 3.5 Inspect the binding in detail

```bash
kubectl describe pvc postgres-pvc-manual -n lab5-storage
```

Pay attention to:
- `Volume: postgres-pv-manual` — which PV it bound to
- `StorageClass: manual`
- `Access Modes: RWO`

```bash
kubectl describe pv postgres-pv-manual
```

Pay attention to:
- `Claim: lab5-storage/postgres-pvc-manual` — which PVC claimed it
- `Reclaim Policy: Retain` — data survives PVC deletion
- `Source.Type: HostPath` — the data is in a directory on the Minikube node
- `Source.Path: /mnt/lab5/manual` — exact path on the node

---

## Part 4: Dynamic Provisioning — StorageClass Does the Work

Static provisioning requires an admin to pre-create each PV. In production clusters (EKS, GKE,
AKS) and in Minikube, a **StorageClass** with an automated **provisioner** can create PVs
on-demand the moment a PVC is applied. This is **dynamic provisioning** — the standard in
modern Kubernetes.

### 4.1 Check your cluster's StorageClasses

```bash
kubectl get storageclass
```

Minikube output:
```
NAME                 PROVISIONER                RECLAIMPOLICY   VOLUMEBINDINGMODE
standard (default)   k8s.io/minikube-hostpath   Delete          Immediate
```

- `(default)` — any PVC that omits `storageClassName` uses this class automatically
- `k8s.io/minikube-hostpath` — the provisioner that creates PVs for you
- `Delete` — **important:** auto-created PVs are deleted when the PVC is deleted

### 4.2 Create a PVC (no manual PV needed)

```bash
kubectl apply -f k8s/08-dynamic-pvc.yaml
kubectl get pvc postgres-pvc-dynamic -n lab5-storage
```

Now look at PVs:

```bash
kubectl get pv
```

A PV was **automatically created** and is already bound. You never created a PV manifest.
The StorageClass provisioner did it the moment the PVC was applied.

### 4.3 Deploy Postgres with the dynamic PVC

```bash
kubectl apply -f k8s/09-postgres-dynamic.yaml
kubectl get pods -l app=postgres-dynamic -n lab5-storage -w
# Ctrl+C when Running
```

### 4.4 Verify persistence

```bash
# Create data
kubectl exec -it \
  $(kubectl get pod -l app=postgres-dynamic -n lab5-storage -o jsonpath='{.items[0].metadata.name}') \
  -n lab5-storage \
  -- psql -U labuser -d labdb -c "
    CREATE TABLE employees (id SERIAL PRIMARY KEY, name TEXT, role TEXT);
    INSERT INTO employees (name, role) VALUES ('Eve', 'Security'), ('Frank', 'Platform');
    SELECT * FROM employees;
  "

# Kill the Pod
kubectl delete pod -l app=postgres-dynamic -n lab5-storage

# Wait for the replacement
kubectl get pods -l app=postgres-dynamic -n lab5-storage -w
# Ctrl+C when Running

# Verify the data
kubectl exec -it \
  $(kubectl get pod -l app=postgres-dynamic -n lab5-storage -o jsonpath='{.items[0].metadata.name}') \
  -n lab5-storage \
  -- psql -U labuser -d labdb -c "SELECT * FROM employees;"
```

Eve and Frank survive. Dynamic provisioning works exactly the same as static from the Pod's
perspective — the PVC abstraction hides the difference.

### 4.5 Demonstrate the danger of the Delete reclaim policy

```bash
# Delete the Deployment first, then the PVC
kubectl delete -f k8s/09-postgres-dynamic.yaml
kubectl delete -f k8s/08-dynamic-pvc.yaml

# What happened to the auto-created PV?
kubectl get pv
```

**The PV is gone.** Because the default StorageClass has `reclaimPolicy: Delete`, the underlying
storage (and all data) was deleted automatically when the PVC was deleted.

Compare this to Part 3: if you delete `postgres-pvc-manual`, the PV `postgres-pv-manual` stays
in `Released` state with `Retain` policy — data intact, waiting for an admin to decide what to do.

---

## Summary & Key Takeaways

### Storage type comparison

| Storage type | Survives container restart? | Survives Pod deletion? | Shared across Pods? |
|--------------|-----------------------------|------------------------|---------------------|
| Container overlay FS | No | No | No |
| `emptyDir` | Yes (within Pod) | No | Same Pod only |
| PVC (RWO) | Yes | Yes | No (one node at a time) |
| PVC (RWX) | Yes | Yes | Yes (many nodes) |

### Provisioning comparison

| | Static provisioning | Dynamic provisioning |
|--|---------------------|----------------------|
| Who creates the PV | Admin, manually | StorageClass provisioner, automatically |
| PVC needs `storageClassName` | Yes (must match PV's class) | Optional (uses cluster default if omitted) |
| Requires a pre-existing PV | Yes | No |
| Common in practice | Legacy / bare-metal clusters | Standard on cloud-managed clusters |

### Reclaim policy comparison

| | `Delete` | `Retain` |
|--|----------|----------|
| PV deleted when PVC is deleted? | Yes | No |
| Underlying storage deleted? | Yes | No |
| Safe for production databases? | **No** | **Yes** |

### Best practices checklist

- [ ] Store credentials in **Secrets**, not plaintext `env` blocks
- [ ] Use `subPath` when mounting a PVC into a directory managed by an application (e.g. Postgres)
- [ ] Always check `RECLAIM POLICY` before deploying a stateful workload: `kubectl get pv`
- [ ] For production databases, use `Retain` reclaim policy
- [ ] For production databases, prefer a **StatefulSet** over a Deployment (Lab 6)

---

## Cleanup

```bash
# Deleting the namespace cascades to all namespaced resources (PVCs, Pods, Deployments, Secrets)
kubectl delete namespace lab5-storage

# The manually-created PV is cluster-scoped (not namespaced) — delete it separately
kubectl delete pv postgres-pv-manual

# Verify everything is gone
kubectl get pv
kubectl get namespace lab5-storage
```
