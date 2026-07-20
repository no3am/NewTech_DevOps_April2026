{{/*
_helpers.tpl: reusable named template definitions.

This file is NOT deployed to Kubernetes. Helm processes it but the output is only
used when another template calls {{ include "my-chart.<name>" . }}.

Centralising name logic and labels here means:
  - A label change requires editing ONE file, not every template
  - All resources are consistently named and labelled
  - Templates stay readable — no repeated boilerplate
*/}}

{{/*
Generate a full resource name: "<release-name>-<chart-name>"
Truncated to 63 characters because Kubernetes DNS labels have a 63-char limit.
trimSuffix removes a trailing "-" if the truncation lands mid-word.
*/}}
{{- define "my-chart.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Standard Kubernetes recommended labels (https://kubernetes.io/docs/concepts/overview/working-with-objects/common-labels/).
Applied to every resource. Used by tooling like Helm, Argo CD, and kubectl for
discovery, filtering, and management.
*/}}
{{- define "my-chart.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels: the minimal stable set used by selector.matchLabels and Service.selector.
WARNING: these must never change after the first install — Kubernetes rejects changes
to selector labels on existing Deployments and Services.
*/}}
{{- define "my-chart.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}
