# Lab 8: Helm Fundamentals

## Learning Objectives

By the end of this lab you will be able to:

1. Explain the difference between a Chart, a Release, and a Repository
2. Use `helm lint`, `helm template`, and `--dry-run` to inspect before deploying
3. Read and write the five most common Go template functions used in real charts
4. Understand `_helpers.tpl` and why centralising label/name logic matters
5. Override values with `--set` (CLI) and `-f` (values file) and know the precedence
6. Inspect a deployed release with `helm get manifest`, `helm get values`, `helm status`
7. Run the full lifecycle: Install â†’ Inspect â†’ Upgrade â†’ Break â†’ Rollback

---

## Prerequisites

- Minikube running, `kubectl` configured
- Helm 3 installed â€” check with: `helm version`

---

## Core Concepts

### The Helm Model

| Term | Analogy | Definition |
|------|---------|------------|
| **Chart** | Package (`.deb`, `.rpm`) | A bundle of Kubernetes YAML templates + default values |
| **Release** | Installed instance | One named running deployment of a Chart, with its own history |
| **Repository** | apt/yum repo | A collection of published Charts (e.g. Bitnami, Artifact Hub) |
| **Values** | Config file | Key-value pairs that fill in the template blanks |

You can install the same Chart multiple times â€” each becomes its own Release with its own
name, resources, and revision history.

---

### The Mad Libs Model

```
values.yaml                    templates/deployment.yaml             rendered output
-----------                    -------------------------             ---------------
replicaCount: 3           â†’    replicas: {{ .Values.replicaCount }}  â†’  replicas: 3
image:                         image: "{{ .Values.image.repository }}
  repository: nginx                     :{{ .Values.image.tag }}"   â†’  image: "nginx:1.27"
  tag: "1.27"
```

`values.yaml` is the only file you should edit to change configuration. Templates stay fixed.

---

### Values Override Precedence

```
values.yaml  <  -f override.yaml  <  --set key=value
  (lowest)                              (highest)
```

`--set` always wins. `-f` overrides `values.yaml`. Use this to keep defaults in the chart
and override per-environment without touching the chart itself.

---

### The Chart Structure

```
my-chart/
  Chart.yaml               â€” Chart metadata (name, version, appVersion)
  values.yaml              â€” Default configuration values
  templates/
    _helpers.tpl           â€” Named template definitions. NOT deployed to Kubernetes.
    deployment.yaml        â€” Deployment template
    service.yaml           â€” Service template
    NOTES.txt              â€” Post-install message. Rendered by Helm, NOT deployed.
```

---

### Go Template Functions Used in This Chart

| Function | Example | What it does |
|----------|---------|-------------|
| `include` | `{{ include "my-chart.fullname" . }}` | Calls a named template from `_helpers.tpl` |
| `nindent` | `\|{{- include "my-chart.labels" . \| nindent 4 }}` | Adds leading newline + N-space indent |
| `toYaml` | `{{- toYaml .Values.resources \| nindent 12 }}` | Renders a Go map as YAML text |
| `quote` | `{{ .Values.environment \| quote }}` | Wraps value in `"..."` â€” safe for booleans/numbers |
| `printf` | `{{ printf "%s-%s" .Release.Name .Chart.Name }}` | String formatting |
| `trunc` | `\| trunc 63` | Truncates to N chars (Kubernetes name length limit) |

---

## Part 1: Inspect Before You Deploy

Never deploy without inspecting your templates first. These three commands form the
standard pre-deploy checklist.

### 1.1 Lint the chart

`helm lint` catches syntax errors and best-practice violations:

```bash
helm lint ./my-chart
```

Expected: `1 chart(s) linted, 0 chart(s) failed`

### 1.2 Render templates locally

`helm template` renders all templates with the default values and prints the resulting YAML
to stdout. **Nothing is sent to Kubernetes.** Use this to review what Helm would apply:

```bash
helm template my-release ./my-chart
```

You should see the full rendered Deployment and Service YAML â€” notice how `my-release-web-server`
appears as the resource name (from `_helpers.tpl`: `printf "%s-%s" .Release.Name .Chart.Name`).

Try an override to see values flowing through:

```bash
helm template my-release ./my-chart --set replicaCount=5
```

The rendered Deployment should show `replicas: 5`.

### 1.3 Dry-run against the cluster

`--dry-run` sends the rendered manifests to the Kubernetes API server for validation but
creates nothing. It catches issues `helm template` misses (invalid field names, schema violations):

```bash
helm install my-release ./my-chart \
  --namespace lab8 \
  --create-namespace \
  --dry-run
```

If the output looks correct, you are ready to install.

---

## Part 2: Install

```bash
helm install my-release ./my-chart \
  --namespace lab8 \
  --create-namespace
```

Helm prints the `NOTES.txt` content after install â€” notice it shows your release name,
namespace, image, and the exact `port-forward` command to use.

### Verify the release

```bash
helm status my-release -n lab8
kubectl get all -n lab8
```

You should see one Pod, one Deployment, and one Service â€” all named `my-release-web-server`.

### Access the app

```bash
kubectl port-forward svc/my-release-web-server 8080:80 -n lab8
```

Open http://localhost:8080 â€” you should see the default Nginx welcome page.
Press `Ctrl+C` to stop.

---

## Part 3: Inspect the Deployed Release

These commands are essential for debugging and auditing.

```bash
# The exact Kubernetes manifests currently deployed by this release
helm get manifest my-release -n lab8

# Only the values you explicitly provided (--set or -f)
helm get values my-release -n lab8

# ALL values including defaults from values.yaml
helm get values my-release -n lab8 --all

# Re-read the post-install NOTES
helm get notes my-release -n lab8

# Full revision history
helm history my-release -n lab8
```

---

## Part 4: Upgrade with --set

`--set` overrides a value on the command line. This is the primary pattern in CI/CD
pipelines â€” e.g. injecting a new image tag from a build pipeline without editing any file.

Scale to 3 replicas:

```bash
helm upgrade my-release ./my-chart \
  --namespace lab8 \
  --set replicaCount=3
```

Confirm the upgrade:

```bash
helm history my-release -n lab8
kubectl get pods -n lab8
```

You should see Revision 2 in history and 3 running Pods.

### Override a nested value

```bash
# Update only the image tag, reuse all other previously-set values
helm upgrade my-release ./my-chart \
  --namespace lab8 \
  --set image.tag=1.26 \
  --reuse-values
```

> **`--reuse-values`:** Without this flag, `helm upgrade` resets everything to `values.yaml`
> defaults â€” you would lose `replicaCount=3`. With it, only the fields you explicitly pass
> via `--set` change. Always use `--reuse-values` when doing a targeted override.

Confirm the new image:

```bash
kubectl get pods -n lab8 -o jsonpath='{.items[0].spec.containers[0].image}'
```

---

## Part 5: Upgrade with a Values File

For environments (dev, staging, prod), a separate values override file is cleaner than
long `--set` chains. Create `prod-values.yaml` in the `lab8 - helm/` directory
(next to `my-chart/`, not inside it):

```yaml
replicaCount: 2

image:
  tag: "1.25"

environment: prod

resources:
  requests:
    cpu: 100m
    memory: 64Mi
  limits:
    cpu: 200m
    memory: 128Mi
```

Apply it:

```bash
helm upgrade my-release ./my-chart \
  --namespace lab8 \
  --values prod-values.yaml
```

Inspect what was applied:

```bash
helm get values my-release -n lab8
kubectl get pods -n lab8
kubectl get pods -n lab8 -o jsonpath='{.items[0].spec.containers[0].image}'
```

You should see 2 Pods running `nginx:1.25`. Check the `APP_ENV` environment variable:

```bash
kubectl exec -n lab8 \
  $(kubectl get pod -n lab8 -l app.kubernetes.io/name=web-server -o jsonpath='{.items[0].metadata.name}') \
  -- env | grep APP_ENV
```

Expected: `APP_ENV=prod`

---

## Part 6: Break and Rollback

First check the current history so you know which revision to roll back to:

```bash
helm history my-release -n lab8
```

### Break it

Upgrade with a non-existent image tag:

```bash
helm upgrade my-release ./my-chart \
  --namespace lab8 \
  --set image.tag=this-tag-does-not-exist \
  --reuse-values
```

Watch the Pods fail:

```bash
kubectl get pods -n lab8 -w
# You will see ErrImagePull or ImagePullBackOff
# Ctrl+C
```

Check history â€” a new revision was created even for the broken deploy:

```bash
helm history my-release -n lab8
```

### Rollback

Roll back to the previous revision (one step back):

```bash
helm rollback my-release -n lab8
```

Or specify an exact revision number if you want to jump back further:

```bash
helm rollback my-release 3 -n lab8   # replace 3 with your target revision number
```

Watch recovery:

```bash
kubectl get pods -n lab8 -w
# Ctrl+C when Pods are Running
```

Check history again:

```bash
helm history my-release -n lab8
```

The rollback is recorded as a **new revision** â€” Helm's history is append-only. You always
have a complete audit trail of every change made to a release.

---

## Summary & Key Takeaways

### Full command reference

| Command | What it does |
|---------|-------------|
| `helm lint ./chart` | Validate chart syntax and best practices |
| `helm template NAME ./chart` | Render templates locally â€” no cluster interaction |
| `helm install NAME ./chart --dry-run` | Render + validate against API server â€” nothing created |
| `helm install NAME ./chart -n NS --create-namespace` | Deploy (Revision 1) |
| `helm upgrade NAME ./chart -n NS --set key=val` | Re-deploy with new values (Revision N+1) |
| `helm upgrade NAME ./chart -n NS -f override.yaml` | Re-deploy with a values file |
| `helm upgrade NAME ./chart -n NS --reuse-values` | Keep all previous values, change only what's specified |
| `helm status NAME -n NS` | Release summary and NOTES |
| `helm get manifest NAME -n NS` | Rendered Kubernetes YAML currently deployed |
| `helm get values NAME -n NS --all` | All values including defaults |
| `helm history NAME -n NS` | Full revision history |
| `helm rollback NAME -n NS` | Roll back one revision |
| `helm rollback NAME REVISION -n NS` | Roll back to a specific revision |
| `helm uninstall NAME -n NS` | Delete the release and all its resources |

### Values override precedence

```
values.yaml  â†’  -f override.yaml  â†’  --set key=val
  (lowest)                              (highest)
```

### Why _helpers.tpl matters

Without `_helpers.tpl`, every template repeats the same name logic and label block.
With it:

```
Change label convention once in _helpers.tpl â†’ all templates update automatically
```

The standard `app.kubernetes.io/` labels used here are recognised by Helm, Argo CD,
kubectl, and most Kubernetes dashboards for resource discovery and grouping.

---

## Cleanup

```bash
helm uninstall my-release -n lab8
kubectl delete namespace lab8
```

