# Lab 3: Kubernetes Services

## Learning Objectives

By the end of this lab you will be able to:

1. Explain why Services exist and what problem they solve
2. Describe all four Service types and choose the right one for a given scenario
3. Explain the difference between `port`, `targetPort`, and `nodePort`
4. Explain how a Service finds its Pods using label selectors
5. Observe a Service load-balancing live traffic across multiple Pods

---

## Core Concepts

### Why Services Exist

Pods are **ephemeral**. When a Pod crashes and is rescheduled, it gets a **new IP address**.
If Service A hard-codes Service B's Pod IP, that connection breaks the moment B's Pod
restarts. Services solve this with a **stable virtual address** that never changes, regardless
of how many times the Pods behind it are replaced.

```
Without a Service:               With a Service:
                                  
Pod A → 10.244.1.5 (Pod B)       Pod A → whoami-service (stable DNS name)
                                           ↓
Pod B restarts → 10.244.1.9      Service → 10.244.1.9  (new Pod B, automatically)
Pod A is now broken              Pod A keeps working
```

A Service also **load-balances** across multiple Pod replicas — each request is forwarded
to one of the healthy Pods behind it.

---

### How a Service Finds Its Pods: Label Selectors

A Service does not reference Pods by name or IP. It uses a **label selector**: any Pod
whose labels match the selector automatically becomes a backend for the Service.

```yaml
# Service selector:
selector:
  app: whoami       ← match all Pods that have this label

# Pod labels (in Deployment template):
labels:
  app: whoami       ← this Pod will receive traffic from the Service
```

When a Pod is added, removed, or replaced, Kubernetes automatically updates the list of
backends (called **Endpoints**). You never have to touch the Service config.

---

### Port Terminology

Three different port numbers appear in a Service spec — they are easy to confuse:

```yaml
ports:
  - port: 80          # The port YOUR CLIENT talks to (e.g. curl http://whoami-service:80)
    targetPort: 5000  # The port the CONTAINER is actually listening on
    nodePort: 30007   # (NodePort type only) The port opened on every Node
```

```
Client → port:80 → Service → targetPort:5000 → Container
                              (translation
                               happens here)
```

The Service translates `port → targetPort` for you. This means you can change the
container port without updating any client — just update `targetPort` in the Service.

---

### The Four Service Types

Each type is a **superset** of the previous one — LoadBalancer includes everything NodePort
does, which includes everything ClusterIP does.

```
ClusterIP
  └── NodePort        (adds external node access on top of ClusterIP)
        └── LoadBalancer  (adds cloud load balancer on top of NodePort)

ExternalName            (completely different — no selector, no proxy)
```

---

#### ClusterIP (default)

Assigns the Service a **virtual IP that only works inside the cluster**. External traffic
cannot reach it.

```
[Pod A] ──────────────────────────────► [ClusterIP: 10.96.14.3:80]
                                               ↓
                                         [Pod B replicas]

❌ Your laptop cannot reach 10.96.14.3
✅ Other Pods inside the cluster can
```

**When to use:** Any communication between services inside the cluster — frontend → backend,
app → database, microservice → microservice. This is the default and most common type.

**Example:** A `database-service` with type ClusterIP. Your app Pod calls
`http://database-service:5432`. Nothing outside the cluster can reach the database directly.

---

#### NodePort

Builds on ClusterIP: also opens a **static port on every Node** in the cluster (range 30000–32767).
Traffic arriving at `<any-node-ip>:<nodePort>` is forwarded into the cluster to the Service.

```
Your laptop ──► http://192.168.49.2:30007
                      (Minikube node IP)
                           ↓
               [NodePort 30007 on every Node]
                           ↓
                    [ClusterIP Service]
                           ↓
                     [Pod replicas]
```

**When to use:** Development and testing when you don't have a cloud load balancer.
Not recommended for production — you expose a non-standard port and must know a Node IP.

---

#### LoadBalancer

Builds on NodePort: also provisions an **external cloud load balancer** (AWS ELB, GCP
Load Balancer, Azure LB) and assigns a real public IP or DNS name.

```
Internet ──► 34.102.88.5 (cloud load balancer public IP)
                  ↓
        [Cloud Load Balancer]
                  ↓
        [NodePort on each Node]
                  ↓
          [ClusterIP Service]
                  ↓
           [Pod replicas]
```

**When to use:** Any production workload that needs to be reachable from outside the cluster.
This is the standard type for internet-facing services in cloud environments.

**On Minikube:** There is no cloud provider to create the LB, so the EXTERNAL-IP stays
`<pending>`. Run `minikube tunnel` in a separate terminal to simulate a local LoadBalancer
and get an IP assigned.

> **Cost note:** Cloud providers charge per load balancer. One LoadBalancer service = one
> LB = money. In production, teams often put a single **Ingress** controller behind one LB
> and route multiple services through it to save cost — that's a later lab.

---

#### ExternalName

Does not use a selector and does not proxy traffic. It simply creates a **DNS CNAME record**
inside the cluster that maps a Service name to an external hostname.

```yaml
apiVersion: v1
kind: Service
metadata:
  name: prod-database
spec:
  type: ExternalName
  externalName: mydb.us-east-1.rds.amazonaws.com
```

```
Pod calls: prod-database:5432
               ↓
    Kubernetes DNS returns CNAME:
    mydb.us-east-1.rds.amazonaws.com
               ↓
         External AWS RDS
```

**When to use:** When you want Pods to use a stable internal Service name to reach an
**external** resource (like an RDS database or a third-party API), so you can change the
external endpoint without redeploying your application — just update the Service.

---

### All Four Types at a Glance

| Type | Reachable from | Use case | Minikube access |
|------|---------------|----------|-----------------|
| **ClusterIP** | Inside cluster only | Service-to-service communication | `kubectl exec` + curl |
| **NodePort** | Node IP + static port | Dev/test external access | `<minikube ip>:<nodePort>` |
| **LoadBalancer** | Public IP / DNS | Production internet-facing services | `minikube tunnel` |
| **ExternalName** | Inside cluster only | Map internal name to external DNS | N/A (DNS alias) |

---

## Prerequisites

- Minikube installed and running
- kubectl installed
- Docker (for building the image)

---

## Step 1: Build the Image

```bash
docker build -t whoami:latest .
```

### Make the image available inside Minikube

Minikube has its **own Docker daemon**. Your local `whoami:latest` image is not visible
inside Minikube by default. Use **one** of these options:

**Option A — Load the image into Minikube (recommended):**

```bash
minikube image load whoami:latest
```

**Option B — Build directly against Minikube's Docker daemon:**

```bash
eval $(minikube docker-env)
docker build -t whoami:latest .
```

---

## Step 2: Deploy

Create the **whoami** Deployment (3 replicas):

```bash
kubectl apply -f k8s/1-deployment.yaml
kubectl get pods -l app=whoami
```

You should see **3 Pods** in `Running` state. Notice they all have the label `app: whoami` —
that is what both Services will use as their selector.

---

## Step 3: Apply Both Services

```bash
kubectl apply -f k8s/2-service-clusterip.yaml
kubectl apply -f k8s/3-service-nodeport.yaml
kubectl get svc
```

You should see two Services:
- `whoami-internal` — type `ClusterIP`, no external port
- `whoami-external` — type `NodePort`, with port `30007`

Both have the **same selector** (`app: whoami`) and the same `targetPort: 5000` — they
both route to the same 3 Pods. The only difference is who can reach them.

---

## Step 4: Test the ClusterIP Service (internal only)

ClusterIP is not reachable from your laptop. Prove this by trying to reach it from inside
the cluster using a temporary Pod:

```bash
# Get the ClusterIP address
kubectl get svc whoami-internal

# Curl it from inside the cluster
kubectl run curl-test --image=curlimages/curl --restart=Never --rm -it \
  -- curl http://whoami-internal:80
```

You should get a response showing a Pod name. From your laptop, the same IP is unreachable.

---

## Step 5: Test the NodePort Service — Prove Load Balancing

```bash
minikube service whoami-external --url
```

Use the URL shown (e.g. `http://192.168.49.2:30007`).

### curl loop — watch the Pod name rotate

```bash
for i in {1..10}; do
  echo "Request $i:"
  curl -s http://$(minikube ip):30007
  echo ""
done
```

### Expected output

```
Request 1:  Request served by Pod: whoami-7d8f9c-xyz12
Request 2:  Request served by Pod: whoami-7d8f9c-abc34
Request 3:  Request served by Pod: whoami-7d8f9c-def56
Request 4:  Request served by Pod: whoami-7d8f9c-xyz12
...
```

The Pod name changes because the Service is **load-balancing** across all 3 replicas.
One URL, one Service, three Pods — kube-proxy distributes each request to a different backend.

---

## Cleanup

```bash
kubectl delete -f k8s/3-service-nodeport.yaml
kubectl delete -f k8s/2-service-clusterip.yaml
kubectl delete -f k8s/1-deployment.yaml
```

---

## Summary

| Concept | Key point |
|---------|-----------|
| **Why Services** | Pods get new IPs when restarted; Services give a stable address |
| **Label selector** | The Service finds Pods dynamically by matching labels — no hard-coded IPs |
| **port vs targetPort** | `port` = what clients use; `targetPort` = what the container listens on |
| **ClusterIP** | Default, internal-only, used for service-to-service traffic |
| **NodePort** | Adds a static port on every node — useful for dev/test access |
| **LoadBalancer** | Adds a cloud LB with a public IP — the standard for production |
| **ExternalName** | DNS alias to an external hostname — no proxy, no Pods |
