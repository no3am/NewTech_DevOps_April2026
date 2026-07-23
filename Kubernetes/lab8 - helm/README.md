# Lab 8: Helm Fundamentals

## Learning Objectives

By the end of this lab you will be able to:

1. Explain the difference between a Chart, a Release, and a Repository
2. Add a Helm repository and search/inspect charts before installing
3. Use `helm lint`, `helm template`, and `--dry-run` to inspect before deploying
4. Read and write the most common Go template functions used in real charts
5. Use `{{ if }}`, `{{ with }}`, and `{{ range }}` to write conditional and looping templates
6. Understand `_helpers.tpl` and why centralising label/name logic matters
7. Override values with `--set` (CLI) and `-f` (values file) and know the precedence
8. Inspect a deployed release with `helm get manifest`, `helm get values`, `helm status`, `helm list`
9. Run the full lifecycle: Install → Inspect → Upgrade → Break → Rollback
10. Scaffold a new chart from scratch with `helm create`

---

## Prerequisites

- Minikube running, `kubectl` configured
- Helm 3 installed — check with: `helm version`

### Pre-pull images into Minikube

The chart uses `nginx` and later parts use a Bitnami nginx image. Pull both into
Minikube's Docker daemon now to avoid `ImagePullBackOff` from Docker Hub rate limits:

```bash
eval $(minikube docker-env)
docker pull nginx:1.27
docker pull nginx:1.26
docker pull nginx:1.25
```

> **Skipped `eval`?** Load the images instead:
> ```bash
> for tag in 1.27 1.26 1.25; do
>   docker pull nginx:$tag && minikube image load nginx:$tag
> done
> ```

---

## Core Concepts

### The Helm Model

| Term | Analogy | Definition |
|------|---------|------------|
| **Chart** | Package (`.deb`, `.rpm`) | A bundle of Kubernetes YAML templates + default values |
| **Release** | Installed instance | One named running deployment of a Chart, with its own history |
| **Repository** | apt/yum repo | A collection of published Charts (e.g. Bitnami, Artifact Hub) |
| **Values** | Config file | Key-value pairs that fill in the template blanks |

You can install the same Chart multiple times — each becomes its own Release with its own
name, resources, and revision history.

---

### The Mad Libs Model

```
values.yaml                    templates/deployment.yaml             rendered output
-----------                    -------------------------             ---------------
replicaCount: 3           →    replicas: {{ .Values.replicaCount }}  →  replicas: 3
image:                         image: "{{ .Values.image.repository }}
  repository: nginx                     :{{ .Values.image.tag }}"   →  image: "nginx:1.27"
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
  Chart.yaml               — Chart metadata (name, version, appVersion)
  values.yaml              — Default configuration values
  templates/
    _helpers.tpl           — Named template definitions. NOT deployed to Kubernetes.
    deployment.yaml        — Deployment template
    service.yaml           — Service template
    NOTES.txt              — Post-install message. Rendered by Helm, NOT deployed.
```

---

### Go Template Reference

#### Value and helper functions

| Function | Example | What it does |
|----------|---------|-------------|
| `include` | `{{ include "my-chart.fullname" . }}` | Calls a named template from `_helpers.tpl` |
| `nindent` | `\|{{- include "my-chart.labels" . \| nindent 4 }}` | Adds leading newline + N-space indent |
| `toYaml` | `{{- toYaml .Values.resources \| nindent 12 }}` | Renders a Go map as YAML text |
| `quote` | `{{ .Values.environment \| quote }}` | Wraps value in `"..."` — safe for booleans/numbers |
| `printf` | `{{ printf "%s-%s" .Release.Name .Chart.Name }}` | String formatting |
| `trunc` | `\| trunc 63` | Truncates to N chars (Kubernetes name length limit) |

#### Control flow

| Construct | When to use | Behaviour when value is empty/false |
|-----------|-------------|-------------------------------------|
| `{{ if .Values.x }}` | Conditional block | Skips the block entirely |
| `{{ with .Values.x }}` | Conditional + re-scope `.` to `x` | Skips the block entirely |
| `{{ range .Values.list }}` | Loop over a list or map | Produces no output |

The key rule: **empty map `{}` and empty list `[]` are both falsy** — `if`, `with`, and
`range` silently produce no output, so optional values stay truly optional.

---

## Part 0: Explore a Remote Repository

Before writing charts yourself, you need to know how to find and install published ones.
This is the first thing you do with Helm in any real project.

### 0.1 Add a repository

A **repository** is a hosted, indexed collection of Charts. Add the Bitnami repository —
one of the most widely used public Chart repositories:

```bash
helm repo add bitnami https://charts.bitnami.com/bitnami
helm repo update
```

`helm repo update` refreshes the local index from every repository you have configured —
the equivalent of `apt-get update`.

> **If the Bitnami HTTP repo is unavailable:** Bitnami migrated to OCI-based registries.
> Skip 0.2–0.3 and install directly with:
> `helm install demo-nginx oci://registry-1.docker.io/bitnamicharts/nginx --set service.type=ClusterIP -n lab8 --create-namespace`
> Then continue from step 0.4.

### 0.2 Search and inspect

```bash
# Find charts whose name or description matches "nginx"
helm search repo nginx
```

`helm search repo` scans the local index of every repo you have added. The result
shows the chart name, version, app version, and a short description.

Now inspect the full values file — this is how you discover every `--set` key a
chart accepts:

```bash
helm show values bitnami/nginx | head -60
```

That first section is all global/registry parameters. The values file is several
hundred lines long. In practice you search it for the key you want to override:

```bash
# Find the service block — this tells you the exact key names to use with --set
helm show values bitnami/nginx | grep -A8 "^service:"
```

You should see something like:

```yaml
service:
  type: LoadBalancer
  ...
```

`service.type` defaults to `LoadBalancer`. On Minikube there is no cloud load
balancer, so we override it to `ClusterIP`. The pattern — **find the key in
`helm show values`, then pass it with `--set`** — is how you configure any
unfamiliar chart.

### 0.3 Install from a remote chart

```bash
helm install demo-nginx bitnami/nginx \
  --set service.type=ClusterIP \
  --namespace lab8 \
  --create-namespace
```

Notice: no `./` prefix — Helm fetches the chart from the repository instead of a local
directory. Everything else (namespace, overrides, NOTES output) works identically.

### 0.4 Inspect with `helm list`

`helm list` is the first command to run when checking what is installed in a namespace:

```bash
helm list -n lab8
```

You should see `demo-nginx` with:
- **STATUS** `deployed`
- **REVISION** `1`
- **CHART** `nginx-x.y.z` (the chart version)
- **APP VERSION** (the Nginx version packaged in this chart)

Compare this to `kubectl get all -n lab8` — `helm list` gives you the Helm-level view
(release name, chart, revision) while `kubectl` gives you the Kubernetes-level view.

### 0.5 Clean up before continuing

```bash
helm uninstall demo-nginx -n lab8
```

`helm uninstall` removes the Kubernetes resources but **leaves the namespace** — the
remaining parts of this lab will reuse `lab8`.

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

You should see the full rendered Deployment and Service YAML — notice how `my-release-web-server`
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

Helm prints the `NOTES.txt` content after install — notice it shows your release name,
namespace, image, and the exact `port-forward` command to use.

### Verify the release

```bash
helm list -n lab8
helm status my-release -n lab8
kubectl get all -n lab8
```

`helm list` gives the Helm view; `kubectl get all` gives the Kubernetes view. You should
see one Pod, one Deployment, and one Service — all named `my-release-web-server`.

Watch the Pod reach `Running` and `1/1 READY` (readinessProbe passes after ~5 s):

```bash
kubectl get pods -n lab8 -w
# Ctrl+C when Ready
```

### Access the app

```bash
kubectl port-forward svc/my-release-web-server 8080:80 -n lab8
```

Open http://localhost:8080 — you should see the default Nginx welcome page.
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

# Full revision history
helm history my-release -n lab8
```

---

## Part 4: Upgrade with --set

`--set` overrides a value on the command line. This is the primary pattern in CI/CD
pipelines — e.g. injecting a new image tag from a build pipeline without editing any file.

### Scale to 3 replicas

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
> defaults — you would lose `replicaCount=3`. With it, only the fields you explicitly pass
> via `--set` change. Always use `--reuse-values` when doing a targeted override.

Confirm the new image:

```bash
kubectl get pods -n lab8 -o jsonpath='{.items[0].spec.containers[0].image}'
```

### The `--atomic` flag (CI/CD pattern)

In an automated pipeline you do not want a broken deploy to sit half-upgraded — you want
an automatic rollback on failure:

```bash
helm upgrade my-release ./my-chart \
  --namespace lab8 \
  --set image.tag=1.26 \
  --reuse-values \
  --atomic \
  --timeout 90s
```

`--atomic` watches the rollout; if any Pod fails to reach `Ready` within `--timeout`,
Helm **automatically rolls back** to the previous revision and exits with a non-zero code
(failing the pipeline). You will see this in action in Part 6.

---

## Part 5: Upgrade with a Values File

For environments (dev, staging, prod), a separate values override file is cleaner than
long `--set` chains. The file `prod-values.yaml` is already in the `lab8 - helm/`
directory (next to `my-chart/`, not inside it).

Inspect it:

```bash
cat prod-values.yaml
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

Check history — a new revision was created even for the broken deploy:

```bash
helm history my-release -n lab8
```

### Manual rollback

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

The rollback is recorded as a **new revision** — Helm's history is append-only. You always
have a complete audit trail of every change made to a release.

### Automatic rollback with `--atomic`

Re-run the breaking upgrade but this time with `--atomic`:

```bash
helm upgrade my-release ./my-chart \
  --namespace lab8 \
  --set image.tag=this-tag-does-not-exist \
  --reuse-values \
  --atomic \
  --timeout 60s
```

Helm watches the Pods, sees `ErrImagePull`, and **automatically reverts** to the last
good revision before the command exits. Check history to see the auto-rollback entry:

```bash
helm history my-release -n lab8
```

In a CI/CD pipeline, `--atomic` eliminates the need for a separate rollback step —
a broken deploy always self-heals and the pipeline fails loudly.

---

## Part 7: Go Template Patterns

The chart already contains three template control-flow patterns. This section explains
each one and lets you exercise them with `helm template` (no cluster changes needed).

### 7.1 `{{ if }}` — conditional block

**In `deployment.yaml`:**

```yaml
{{- if .Values.podAnnotations }}
annotations:
  {{- toYaml .Values.podAnnotations | nindent 8 }}
{{- end }}
```

`{{ if }}` renders the block only when the value is truthy. An empty map `{}` is falsy,
so when `podAnnotations` is empty (the default), the `annotations:` key is never emitted.

Exercise — render with pod annotations and grep for them:

```bash
helm template my-release ./my-chart \
  --set podAnnotations.version=v2 \
  --set podAnnotations.team=platform \
  | grep -A4 annotations
```

Expected output contains:

```yaml
annotations:
  team: platform
  version: v2
```

Without the flag, the annotations block is completely absent:

```bash
helm template my-release ./my-chart | grep annotations
# (no output)
```

---

### 7.2 `{{ with }}` — conditional + context re-scope

**In `deployment.yaml`:**

```yaml
{{- with .Values.nodeSelector }}
nodeSelector:
  {{- toYaml . | nindent 8 }}
{{- end }}
```

`{{ with }}` behaves like `{{ if }}` but also re-scopes `.` to the value being tested.
Inside the block, `.` is `.Values.nodeSelector`, so you write `toYaml .` instead of
`toYaml .Values.nodeSelector`. This keeps the template readable when the value is a
complex nested structure.

Exercise — render with a node selector:

```bash
helm template my-release ./my-chart \
  --set nodeSelector.disktype=ssd \
  | grep -A2 nodeSelector
```

Expected:

```yaml
nodeSelector:
  disktype: ssd
```

Without the flag, the `nodeSelector:` key is absent entirely.

---

### 7.3 `{{ range }}` — loop over a list

**In `deployment.yaml`:**

```yaml
{{- range .Values.extraEnv }}
- name: {{ .name }}
  value: {{ .value | quote }}
{{- end }}
```

`{{ range }}` iterates over a list. Each iteration sets `.` to the current item. An empty
list `[]` produces no output — the loop body never executes.

Exercise — render with two extra environment variables:

```bash
helm template my-release ./my-chart \
  --set 'extraEnv[0].name=LOG_LEVEL' \
  --set 'extraEnv[0].value=debug' \
  --set 'extraEnv[1].name=REGION' \
  --set 'extraEnv[1].value=eu-west-1' \
  | grep -A2 "LOG_LEVEL\|REGION"
```

Expected:

```yaml
- name: LOG_LEVEL
  value: "debug"
- name: REGION
  value: "eu-west-1"
```

---

### 7.4 Combining all three

A realistic upgrade that exercises all three patterns at once:

```bash
helm upgrade my-release ./my-chart \
  --namespace lab8 \
  --reuse-values \
  --set podAnnotations.version=v2 \
  --set nodeSelector.disktype=ssd \
  --set 'extraEnv[0].name=LOG_LEVEL' \
  --set 'extraEnv[0].value=info'
```

Verify the annotations landed on the Pod:

```bash
kubectl get pod -n lab8 \
  -l app.kubernetes.io/name=web-server \
  -o jsonpath='{.items[0].metadata.annotations}' \
  | python3 -m json.tool
```

Verify the extra env var:

```bash
kubectl exec -n lab8 \
  $(kubectl get pod -n lab8 -l app.kubernetes.io/name=web-server -o jsonpath='{.items[0].metadata.name}') \
  -- env | grep LOG_LEVEL
```

> **Note:** The `nodeSelector.disktype=ssd` will cause the Pod to remain `Pending` unless
> your node has that label. Roll it back or remove the selector:
> `helm upgrade my-release ./my-chart -n lab8 --reuse-values --set nodeSelector=null`

---

## Part 8: Scaffold a New Chart

When you need a chart for your own application, use `helm create` rather than starting
from a blank directory:

```bash
# Run this from the lab8 - helm/ directory
helm create hello-app
```

Explore what was generated:

```
hello-app/
  Chart.yaml
  values.yaml
  charts/                  ← subcharts live here
  templates/
    _helpers.tpl           ← same pattern as my-chart
    deployment.yaml
    service.yaml
    serviceaccount.yaml    ← creates an SA when serviceAccount.create=true
    ingress.yaml           ← conditional on ingress.enabled
    hpa.yaml               ← HorizontalPodAutoscaler, conditional on autoscaling.enabled
    NOTES.txt
    tests/
      test-connection.yaml ← helm test hook
```

Key things to read in the generated files:

```bash
# The scaffold uses the same _helpers.tpl pattern — familiar from my-chart
grep "define\|include" hello-app/templates/_helpers.tpl

# ingress.yaml is gated behind {{ if .Values.ingress.enabled }}
grep -n "if\|with\|range" hello-app/templates/ingress.yaml

# serviceaccount.yaml is gated behind {{ if .Values.serviceAccount.create }}
grep -n "if" hello-app/templates/serviceaccount.yaml
```

To adapt the scaffold for your own application:
1. Edit `Chart.yaml` — set `name`, `description`, `appVersion`
2. Edit `values.yaml` — replace the default image with your app's image
3. Edit `templates/deployment.yaml` — update container ports, env vars, probes
4. Delete template files you do not need (e.g. `hpa.yaml` if you do not use autoscaling)

Clean up the generated chart (you will not deploy it in this lab):

```bash
rm -rf hello-app
```

---

## Summary & Key Takeaways

### Full command reference

| Command | What it does |
|---------|-------------|
| `helm repo add NAME URL` | Add a remote chart repository |
| `helm repo update` | Refresh the local repository index |
| `helm search repo KEYWORD` | Find charts across all added repositories |
| `helm show values REPO/CHART` | Inspect all configurable values before installing |
| `helm lint ./chart` | Validate chart syntax and best practices |
| `helm template NAME ./chart` | Render templates locally — no cluster interaction |
| `helm install NAME ./chart --dry-run` | Render + validate against API server — nothing created |
| `helm install NAME ./chart -n NS --create-namespace` | Deploy (Revision 1) |
| `helm list -n NS` | Show all releases in a namespace |
| `helm status NAME -n NS` | Release summary and NOTES |
| `helm upgrade NAME ./chart -n NS --set key=val` | Re-deploy with new values (Revision N+1) |
| `helm upgrade NAME ./chart -n NS -f override.yaml` | Re-deploy with a values file |
| `helm upgrade NAME ./chart -n NS --reuse-values` | Keep all previous values, change only what's specified |
| `helm upgrade NAME ./chart -n NS --atomic --timeout 90s` | Auto-rollback if rollout fails |
| `helm get manifest NAME -n NS` | Rendered Kubernetes YAML currently deployed |
| `helm get values NAME -n NS --all` | All values including defaults |
| `helm history NAME -n NS` | Full revision history |
| `helm rollback NAME -n NS` | Roll back one revision |
| `helm rollback NAME REVISION -n NS` | Roll back to a specific revision |
| `helm uninstall NAME -n NS` | Delete the release and all its resources |
| `helm create NAME` | Scaffold a new chart |

### Values override precedence

```
values.yaml  →  -f override.yaml  →  --set key=val
  (lowest)                              (highest)
```

### Template control flow in one line

```
{{ if }}   → emit block when value is truthy (empty map/list = falsy)
{{ with }} → same as if, but also re-scopes "." to the tested value
{{ range}} → emit block once per item in a list/map (empty = no output)
```

### Why _helpers.tpl matters

Without `_helpers.tpl`, every template repeats the same name logic and label block.
With it:

```
Change label convention once in _helpers.tpl → all templates update automatically
```

The standard `app.kubernetes.io/` labels used here are recognised by Helm, Argo CD,
kubectl, and most Kubernetes dashboards for resource discovery and grouping.

---

## Cleanup

```bash
helm uninstall my-release -n lab8
kubectl delete namespace lab8
helm repo remove bitnami   # if you added it in Part 0
```
