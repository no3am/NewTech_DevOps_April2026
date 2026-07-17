# Lab 7: Kubernetes DaemonSets

## Learning Objectives

By the end of this lab you will be able to:

1. Explain what a DaemonSet is and why there is no `replicas` field
2. Use tolerations to run a DaemonSet on control-plane nodes
3. Watch a new agent Pod appear automatically when a node joins (Minikube multi-node)
4. Restrict a DaemonSet to specific nodes using `nodeSelector`
5. Inject node metadata into Pods using the **Downward API**
6. Choose between `RollingUpdate` and `OnDelete` update strategies
7. Know when to use a DaemonSet vs a Deployment vs a StatefulSet

---

## Prerequisites

- Minikube running, `kubectl` configured
- Labs 5 and 6 completed (familiarity with controllers and PVCs)

---

## Core Concepts

### What is a DaemonSet?

A DaemonSet ensures **exactly one copy of a Pod runs on every schedulable node** in the cluster
(or on a subset of nodes you define with a `nodeSelector`).

- When a **node joins** the cluster → a Pod is automatically scheduled on it
- When a **node leaves** the cluster → its Pod is garbage-collected
- There is **no `replicas` field** — desired count is always derived from node count

```
3-node cluster:       5-node cluster (2 added):
                           →
[node-1] ← Pod        [node-1] ← Pod
[node-2] ← Pod        [node-2] ← Pod
[node-3] ← Pod        [node-3] ← Pod
                       [node-4] ← Pod  (auto-scheduled)
                       [node-5] ← Pod  (auto-scheduled)
```

---

### When to use a DaemonSet

Use a DaemonSet when you need a **node-level agent** — a process that must run once on every node:

| Use Case | Example Tools |
|----------|--------------|
| Log collection | Fluentd, Filebeat, Fluent Bit |
| Metrics / monitoring | Node Exporter, Datadog Agent, Dynatrace |
| Network plugins (CNI) | Calico, Cilium, Flannel |
| Storage plugins | Longhorn, Ceph, OpenEBS |
| Security scanning | Falco, Aqua Security |

---

### Deployment vs StatefulSet vs DaemonSet

By now you have seen all three controllers. Here is the decision guide:

| Controller | Pod count | Pods are | Storage | Use when |
|-----------|-----------|----------|---------|----------|
| **Deployment** | N (you set) | Interchangeable | Shared or none | Stateless apps, APIs, web servers |
| **StatefulSet** | N (you set) | Unique, ordered, sticky | Per-pod, dedicated | Databases, Kafka, ZooKeeper |
| **DaemonSet** | 1 per node (auto) | Node-scoped | Node `hostPath` | Log agents, monitoring, CNI |

---

### Tolerations

By default, the scheduler avoids nodes that have **taints**. Minikube's control-plane node
carries a `NoSchedule` taint. Without a matching toleration, the DaemonSet would show `DESIRED=0`
on a single-node Minikube cluster.

```
Node taint:    node-role.kubernetes.io/control-plane:NoSchedule
Pod toleration: key: node-role.kubernetes.io/control-plane, effect: NoSchedule
```

A toleration says "I am allowed to run here even though the node has this taint."

---

### nodeSelector

DaemonSets do not have to run on *every* node. A `nodeSelector` restricts scheduling to nodes
with a specific label:

```yaml
nodeSelector:
  monitor: "true"   # Only schedule on nodes labelled monitor=true
```

Practical uses:
- GPU driver agents — only nodes with GPUs
- Security scanners — only nodes opted-in by a team label
- Log forwarders — only nodes running sensitive workloads

---

### The Downward API

The Downward API lets a Pod learn about **itself and its environment** at runtime without
querying the Kubernetes API server. For DaemonSet agents, injecting `spec.nodeName` as an
environment variable is the standard pattern — the agent needs to tag its metrics and logs
with the node they came from.

```yaml
env:
  - name: NODE_NAME
    valueFrom:
      fieldRef:
        fieldPath: spec.nodeName   # Set by the scheduler when the Pod is assigned
```

Note: `hostname` inside a container returns the **Pod name**, not the node name. The Downward
API is the correct way to get the node name.

---

### updateStrategy

| Strategy | Behavior | Use when |
|----------|----------|----------|
| `RollingUpdate` (default) | Pods updated one node at a time, automatically | Normal agent updates |
| `OnDelete` | Pods only updated when you manually delete them | Need node-by-node validation before proceeding |

---

## Setup

```bash
kubectl apply -f k8s/01-namespace.yaml
```

---

## Part 1: Deploy and Verify — One Pod Per Node

```bash
kubectl apply -f k8s/02-node-agent-ds.yaml
kubectl get ds -n lab7-daemonset
```

Expected:
```
NAME         DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR
node-agent   1         1         1       1            1           <none>
```

`DESIRED = number of schedulable nodes`. On single-node Minikube this is 1.

Check the Pod and note its node:

```bash
kubectl get pods -n lab7-daemonset -o wide
```

### Inspect what the agent sees on the node

```bash
kubectl logs -n lab7-daemonset -l app=node-agent -f
```

You should see:
```
===============================
 Node Agent Starting
===============================
Node:      minikube
Pod:       node-agent-xxxxx
Namespace: lab7-daemonset

Host log files visible to this agent:
alternatives.log
apt
...

[12:34:56Z] Agent alive on node: minikube
```

Press `Ctrl+C` to stop.

The node name (`minikube`) came from the **Downward API** via `spec.nodeName` — not from
`hostname`, which would have returned the Pod name.

### Confirm there is no replicas field

```bash
kubectl get ds node-agent -n lab7-daemonset -o jsonpath='{.spec.replicas}'
```

Returns nothing. The DaemonSet controller does not use a replica count.

---

## Part 2: Automatic Scheduling — Add a Node

This is the defining demo of a DaemonSet. Add a second Minikube node and watch a new agent
Pod appear on it automatically — with no `kubectl apply` and no replica count change.

```bash
# Check current state: 1 node, 1 pod
kubectl get nodes
kubectl get pods -n lab7-daemonset -o wide
```

### Add a second Minikube node

```bash
minikube node add
```

This provisions `minikube-m02`. Wait for it to reach Ready:

```bash
kubectl get nodes -w
# Ctrl+C when minikube-m02 shows Ready
```

### Watch the DaemonSet react

```bash
kubectl get pods -n lab7-daemonset -o wide -w
# Ctrl+C when both pods are Running
```

A new Pod is scheduled on `minikube-m02` automatically. Check the DaemonSet status:

```bash
kubectl get ds -n lab7-daemonset
```

`DESIRED` is now 2. No manifest was changed. No replica count was set.

### Remove the node and watch the Pod disappear

```bash
minikube node delete minikube-m02

kubectl get pods -n lab7-daemonset -o wide -w
# Ctrl+C when only 1 pod remains

kubectl get ds -n lab7-daemonset
# DESIRED is back to 1
```

---

## Part 3: nodeSelector — Target Specific Nodes

Deploy a second DaemonSet that only runs on nodes labelled `monitor=true`. Use this to
understand how to restrict a DaemonSet to a subset of the cluster.

### Apply the DaemonSet before labelling any node

```bash
kubectl apply -f k8s/03-node-selector-ds.yaml
kubectl get ds node-agent-monitored -n lab7-daemonset
```

Expected: `DESIRED=0` — no node has the label yet, so no Pod is scheduled.

### Label the Minikube node

```bash
kubectl label node minikube monitor=true

kubectl get ds node-agent-monitored -n lab7-daemonset
```

`DESIRED` jumps to 1. A Pod appears on `minikube`:

```bash
kubectl get pods -n lab7-daemonset -l app=node-agent-monitored -o wide
kubectl logs -n lab7-daemonset -l app=node-agent-monitored
```

### Remove the label and watch the Pod terminate

```bash
kubectl label node minikube monitor-    # trailing "-" removes the label

kubectl get pods -n lab7-daemonset -l app=node-agent-monitored -o wide -w
# Ctrl+C when the pod is gone

kubectl get ds node-agent-monitored -n lab7-daemonset
# DESIRED is back to 0
```

The DaemonSet still exists — it's just waiting for a node with its label to appear.

---

## Part 4: Update Strategies

### RollingUpdate (default)

Trigger a rolling restart without changing the image:

```bash
kubectl rollout restart daemonset/node-agent -n lab7-daemonset

kubectl rollout status daemonset/node-agent -n lab7-daemonset
```

On a single-node cluster this causes a brief gap. On a multi-node cluster the agent
stays running on all other nodes while each node's Pod is replaced one at a time.

### OnDelete

With `OnDelete`, Pods are only replaced when you manually delete them. This gives you full
control over when each node's agent restarts — useful for major config changes you want to
validate node by node.

```bash
# Switch the strategy to OnDelete
kubectl patch daemonset node-agent -n lab7-daemonset \
  -p '{"spec":{"updateStrategy":{"type":"OnDelete"}}}'

# Trigger a spec change (add an annotation) — this would cause a rolling update
# under RollingUpdate, but with OnDelete nothing happens automatically
kubectl annotate daemonset node-agent -n lab7-daemonset updated-at="v2" --overwrite

# Check status — it will report "waiting for rollout to finish"
kubectl rollout status daemonset/node-agent -n lab7-daemonset

# Manually delete the Pod to apply the update on this node
kubectl delete pod -l app=node-agent -n lab7-daemonset

# A replacement Pod starts with the updated spec
kubectl get pods -n lab7-daemonset
```

---

## Summary & Key Takeaways

### Controller decision guide

| You need... | Use |
|-------------|-----|
| N identical replicas, any order | **Deployment** |
| N ordered replicas, unique identity, per-pod storage | **StatefulSet** |
| Exactly one Pod per node (or per labelled node) | **DaemonSet** |

### DaemonSet quick reference

| Property | Behaviour |
|----------|-----------|
| `replicas` field | Does not exist — count equals number of matching nodes |
| Pod naming | Random suffix: `node-agent-x7k2p` |
| Startup order | No guarantee — all matching nodes get a Pod simultaneously |
| Storage | Typically `hostPath` to access node-level data |
| Node joins | Pod automatically scheduled |
| Node removed | Pod automatically garbage-collected |

### Tolerations vs nodeSelector

| | Purpose |
|--|---------|
| **Toleration** | Allows scheduling on nodes with a matching **taint** (e.g. control-plane) |
| **nodeSelector** | Restricts scheduling to only nodes with a specific **label** |

These compose: use `nodeSelector` to opt-in specific nodes, tolerations to bypass `NoSchedule`
taints on those nodes.

---

## Cleanup

```bash
kubectl delete namespace lab7-daemonset

# Remove the node label if you applied it
kubectl label node minikube monitor-
```

## Summary & Key Takeaways

### Controller decision guide

| You need... | Use |
|-------------|-----|
| N identical replicas, any order | **Deployment** |
| N ordered replicas, unique identity, per-pod storage | **StatefulSet** |
| Exactly one Pod per node (or per labelled node) | **DaemonSet** |

### DaemonSet quick reference

| Property | Behaviour |
|----------|-----------|
| `replicas` field | Does not exist — count equals number of matching nodes |
| Pod naming | Random suffix: `node-agent-x7k2p` |
| Startup order | No guarantee — all matching nodes get a Pod simultaneously |
| Storage | Typically `hostPath` to access node-level data |
| Node joins | Pod automatically scheduled |
| Node removed | Pod automatically garbage-collected |

### Tolerations vs nodeSelector

| | Purpose |
|--|---------|
| **Toleration** | Allows scheduling on nodes with a matching **taint** (e.g. control-plane) |
| **nodeSelector** | Restricts scheduling to only nodes with a specific **label** |

These compose: use `nodeSelector` to opt-in specific nodes, tolerations to bypass `NoSchedule`
taints on those nodes.

---

## Cleanup

```bash
kubectl delete namespace lab7-daemonset

# Remove the node label if you applied it
kubectl label node minikube monitor-
```

## Objective

Use a **DaemonSet** so that one instance of a Pod runs on **every node** in the cluster. This is the usual pattern for node-level “background” services such as:

- **Log collectors** (e.g. Fluentd)
- **Monitoring agents** (e.g. Node Exporter)
- **Networking / storage plugins**

In this lab you will:

- Deploy a **Fluentd** logging agent via a DaemonSet.
- See that **Desired** Pod count matches the number of nodes (one Pod per node).
- See that **no node runs more than one** Fluentd Pod.
- (On a multi-node cluster) See that when a **new node is added**, a new Pod is scheduled on it automatically.
- See how DaemonSets **ignore normal replica counts** and scheduling constraints to get node-level coverage.

---

## Prerequisites

- A Kubernetes cluster (v1.20+).
- **Ideal:** At least **two worker nodes** so you can clearly see “one Pod per node.”  
  On Minikube you typically have one node; the DaemonSet will still run one Pod on that node.

---

## The Exercise

### 1. DaemonSet (`fluentd-ds.yaml`)

The manifest defines:

- A **DaemonSet** named `fluentd-logging` in `kube-system`.
- **Tolerations** so the Pod can run on control-plane nodes that have `NoSchedule` taints (`node-role.kubernetes.io/control-plane` and `node-role.kubernetes.io/master`).
- A single container: **Fluentd** (log forwarder), with resource limits/requests.
- A **hostPath** volume mounting the node’s `/var/log` so Fluentd can read node logs.

There is **no `replicas`** field: the DaemonSet controller ensures one Pod per node.

---

## Deployment

Apply the manifest:

```bash
kubectl apply -f k8s/fluentd-ds.yaml
```

---

## Verification

### 1. DaemonSet status

Check that **Desired** matches the number of nodes (and that **Current** matches **Desired**):

```bash
kubectl get ds -n kube-system fluentd-logging
```

Example (3-node cluster):

```
NAME              DESIRED   CURRENT   READY   UP-TO-DATE   AVAILABLE   NODE SELECTOR   AGE
fluentd-logging   3         3         3       3            3          <none>          1m
```

**Desired = number of (schedulable) nodes.** That’s the “one Pod per node” behavior.

### 2. Pod distribution (one per node)

List the Pods with node names. You should see **at most one** Fluentd Pod per node:

```bash
kubectl get pods -n kube-system -o wide -l name=fluentd-logging
```

Example:

```
NAME                    READY   STATUS    NODE
fluentd-logging-xxxxx   1/1     Running   node-1
fluentd-logging-yyyyy   1/1     Running   node-2
fluentd-logging-zzzzz   1/1     Running   node-3
```

No node should have two Fluentd Pods.

### 3. (Optional) Add a node and watch a new Pod appear

If your cluster has multiple nodes and you can add one (e.g. scale a node pool, or add a worker):

1. Note the current number of Fluentd Pods: `kubectl get pods -n kube-system -l name=fluentd-logging`.
2. Add the new node and wait until it is Ready.
3. Run again: `kubectl get pods -n kube-system -l name=fluentd-logging` and `kubectl get ds -n kube-system fluentd-logging`.

You should see **Desired** and the Pod count increase by one, and a new Fluentd Pod on the new node. The DaemonSet ensures node-level coverage without manual scaling.

---

## Summary

| Aspect | DaemonSet behavior |
|--------|--------------------|
| **Scheduling** | One Pod per node; no `replicas` field. |
| **New nodes** | When a new node joins, a new Pod is scheduled on it automatically. |
| **Limits** | Ignores normal replica/scheduling limits to achieve node coverage. |
| **Use cases** | Log collectors, monitoring agents, networking/storage plugins. |

---

## Cleanup

```bash
kubectl delete -f k8s/fluentd-ds.yaml
```
