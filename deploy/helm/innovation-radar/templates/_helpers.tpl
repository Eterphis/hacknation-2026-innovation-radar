{{- define "radar.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}{{ .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else -}}{{ printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}{{- end -}}
{{- end -}}

{{- define "radar.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
{{- end -}}

{{- define "radar.selector" -}}
app.kubernetes.io/name: {{ .root.Chart.Name }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "radar.image" -}}
{{ .Values.image.repository }}:{{ .Values.image.tag | default .Chart.AppVersion }}
{{- end -}}

{{- define "radar.secretName" -}}
{{ .Values.existingSecret | default (printf "%s-secrets" (include "radar.fullname" .)) }}
{{- end -}}

{{- define "radar.databaseUrl" -}}
{{- if .Values.postgresql.enabled -}}
postgresql+psycopg://{{ .Values.postgresql.user }}:{{ .Values.postgresql.password }}@{{ include "radar.fullname" . }}-postgres:5432/{{ .Values.postgresql.database }}
{{- else -}}{{ .Values.externalDatabase.url }}{{- end -}}
{{- end -}}

{{- define "radar.brokerUrl" -}}
{{- if .Values.rabbitmq.enabled -}}
amqp://{{ .Values.rabbitmq.user }}:{{ .Values.rabbitmq.password }}@{{ include "radar.fullname" . }}-rabbitmq:5672//
{{- else -}}{{ .Values.externalBroker.url }}{{- end -}}
{{- end -}}

{{/* Env shared by every role. */}}
{{- define "radar.env" -}}
- name: RADAR_SOURCES_FILE
  value: {{ if .Values.sources }}/config/sources.yaml{{ else }}/app/sources.yaml{{ end }}
- name: RADAR_DEMO_MODE
  value: {{ .Values.config.demoMode | ternary "1" "0" | quote }}
- name: RADAR_LLM_PROVIDERS
  value: {{ .Values.config.llmProviders | quote }}
- name: RADAR_ANTHROPIC_MODEL
  value: {{ .Values.config.anthropicModel | quote }}
- name: RADAR_OPENAI_BASE_URL
  value: {{ .Values.config.openaiBaseUrl | quote }}
- name: RADAR_OPENAI_MODEL
  value: {{ .Values.config.openaiModel | quote }}
- name: RADAR_LOG_LEVEL
  value: {{ .Values.config.logLevel | quote }}
- name: RADAR_DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.externalDatabase.existingSecret | default (printf "%s-internal" (include "radar.fullname" .)) }}
      key: RADAR_DATABASE_URL
- name: RADAR_BROKER_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.externalBroker.existingSecret | default (printf "%s-internal" (include "radar.fullname" .)) }}
      key: RADAR_BROKER_URL
{{- with .Values.extraEnv }}
{{ toYaml . }}
{{- end }}
{{- end -}}

{{- define "radar.envFrom" -}}
- secretRef:
    name: {{ include "radar.secretName" . }}
    optional: true
{{- end -}}

{{- define "radar.volumes" -}}
{{- if .Values.sources }}
- name: sources
  configMap:
    name: {{ include "radar.fullname" . }}-sources
{{- end }}
- name: tmp
  emptyDir: {}
{{- end -}}

{{- define "radar.volumeMounts" -}}
{{- if .Values.sources }}
- name: sources
  mountPath: /config
  readOnly: true
{{- end }}
- name: tmp
  mountPath: /tmp
{{- end -}}

{{/* Pod-level boilerplate: securityContext, scheduling. */}}
{{- define "radar.podCommon" -}}
{{- with .Values.imagePullSecrets }}
imagePullSecrets: {{ toYaml . | nindent 2 }}
{{- end }}
securityContext: {{ toYaml .Values.podSecurityContext | nindent 2 }}
{{- with .Values.nodeSelector }}
nodeSelector: {{ toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.tolerations }}
tolerations: {{ toYaml . | nindent 2 }}
{{- end }}
{{- with .Values.affinity }}
affinity: {{ toYaml . | nindent 2 }}
{{- end }}
{{- end -}}

{{/* Checksum annotation so pods restart when sources or secrets change. */}}
{{- define "radar.checksums" -}}
checksum/sources: {{ toYaml .Values.sources | sha256sum }}
checksum/secrets: {{ toYaml .Values.secrets | sha256sum }}
{{- end -}}
