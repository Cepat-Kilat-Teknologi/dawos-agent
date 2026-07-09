# Monitoring Integration

This guide covers how to integrate DawOS Agent with external monitoring systems. It explains the available endpoints, metric definitions, health probes, real-time event streaming, and provides ready-to-use configurations for Prometheus, Grafana, and common alerting setups.

---

## Overview

DawOS Agent exposes several monitoring interfaces:

| Interface | Endpoint | Auth | Purpose |
|-----------|----------|------|---------|
| Prometheus metrics | `GET /metrics` | None | Metric scraping |
| Liveness probe | `GET /health` | None | Process health |
| Readiness probe | `GET /health/ready` | None | Dependency health |
| WebSocket events | `WS /ws/events` | API key | Real-time event stream |
| Audit log | `GET /api/v1/audit` | Admin key | Write operation trail |
| Monitoring API | `GET /api/v1/monitoring/*` | API key | Exporter management |

All public endpoints (`/metrics`, `/health`, `/health/ready`) are exempt from rate limiting to ensure reliable collection at any scrape interval.

---

## Prometheus Integration

### Metrics Endpoint

The `/metrics` endpoint returns all collected metrics in Prometheus text exposition format. No authentication is required, following the standard convention for metrics scraping.

```bash
curl -sf http://localhost:8470/metrics
```

### Available Metrics

DawOS Agent registers the following metrics:

**HTTP request metrics** (updated by the metrics middleware):

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `dawos_http_requests_total` | Counter | `method`, `endpoint`, `status` | Total HTTP requests received |
| `dawos_http_request_duration_seconds` | Histogram | `method`, `endpoint` | Request processing time |

**accel-cmd metrics** (updated by service layer and retry logic):

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `dawos_accel_cmd_errors_total` | Counter | — | accel-cmd command failures (non-zero exit) |
| `dawos_accel_cmd_retries_total` | Counter | — | Retry attempts for transient failures |

**Rate limiting metrics** (updated by the metrics middleware):

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `dawos_rate_limit_hits_total` | Counter | — | Requests rejected with HTTP 429 |

The `endpoint` label uses the **route path template** (e.g. `/api/v1/sessions/{username}`) rather than the concrete URL. This prevents label cardinality explosion from dynamic path segments.

Paths `/metrics`, `/health`, and `/health/ready` are excluded from metric recording to avoid self-instrumentation loops.

### Prometheus Scrape Configuration

**Single node:**

```yaml
# prometheus.yml
scrape_configs:
  - job_name: dawos-agent
    scrape_interval: 15s
    static_configs:
      - targets: ["10.0.1.1:8470"]
        labels:
          node: "bng-prod-01"
```

**Multiple BNG nodes:**

```yaml
scrape_configs:
  - job_name: dawos-agent
    scrape_interval: 15s
    static_configs:
      - targets:
          - "10.0.1.1:8470"
          - "10.0.1.2:8470"
          - "10.0.1.3:8470"
    relabel_configs:
      - source_labels: [__address__]
        regex: "(.+):.*"
        target_label: instance
```

**With service discovery (file-based):**

```yaml
scrape_configs:
  - job_name: dawos-agent
    scrape_interval: 15s
    file_sd_configs:
      - files:
          - /etc/prometheus/dawos-targets.json
        refresh_interval: 5m
```

Target file (`dawos-targets.json`):

```json
[
  {
    "targets": ["10.0.1.1:8470"],
    "labels": {"node": "bng-prod-01", "site": "jakarta"}
  },
  {
    "targets": ["10.0.1.2:8470"],
    "labels": {"node": "bng-prod-02", "site": "surabaya"}
  }
]
```

### Verifying the Scrape

After adding the configuration, verify Prometheus can reach the agent:

```bash
# Check target status from Prometheus
curl -sf http://prometheus:9090/api/v1/targets | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  [print(t['labels']['job'], t['health']) for t in d['data']['activeTargets'] \
   if t['labels']['job']=='dawos-agent']"

# Verify metrics are being collected
curl -sf 'http://prometheus:9090/api/v1/query?query=dawos_http_requests_total' | \
  python3 -m json.tool
```

---

## Grafana Dashboards

### Request Rate Panel

Total request rate across all endpoints:

```promql
sum(rate(dawos_http_requests_total[5m])) by (instance)
```

Request rate by HTTP method:

```promql
sum(rate(dawos_http_requests_total[5m])) by (method)
```

### Error Rate Panel

HTTP 5xx error rate as a percentage of total requests:

```promql
sum(rate(dawos_http_requests_total{status=~"5.."}[5m]))
  /
sum(rate(dawos_http_requests_total[5m]))
  * 100
```

### Latency Panels

P50, P95, and P99 response time across all endpoints:

```promql
# P50
histogram_quantile(0.50, sum(rate(dawos_http_request_duration_seconds_bucket[5m])) by (le))

# P95
histogram_quantile(0.95, sum(rate(dawos_http_request_duration_seconds_bucket[5m])) by (le))

# P99
histogram_quantile(0.99, sum(rate(dawos_http_request_duration_seconds_bucket[5m])) by (le))
```

Per-endpoint latency (useful for identifying slow endpoints):

```promql
histogram_quantile(0.95,
  sum(rate(dawos_http_request_duration_seconds_bucket[5m])) by (le, endpoint)
)
```

### accel-cmd Health Panel

Error rate for accel-cmd subprocess calls:

```promql
rate(dawos_accel_cmd_errors_total[5m])
```

Retry activity (spikes indicate transient accel-ppp issues):

```promql
rate(dawos_accel_cmd_retries_total[5m])
```

### Rate Limiting Panel

Rate limit rejection rate:

```promql
rate(dawos_rate_limit_hits_total[5m])
```

---

## Alerting Rules

### Prometheus Alert Configuration

Create a rules file and include it in your Prometheus configuration:

```yaml
# prometheus.yml
rule_files:
  - /etc/prometheus/rules/dawos.yml
```

### Recommended Alerts

```yaml
# /etc/prometheus/rules/dawos.yml
groups:
  - name: dawos-agent
    rules:
      # Agent is down (no metrics received for 2 minutes)
      - alert: DawosAgentDown
        expr: up{job="dawos-agent"} == 0
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "dawos-agent is unreachable on {{ $labels.instance }}"
          description: "Prometheus has not received metrics from this agent for over 2 minutes."

      # High error rate (more than 5% of requests returning 5xx)
      - alert: DawosHighErrorRate
        expr: |
          sum(rate(dawos_http_requests_total{status=~"5.."}[5m])) by (instance)
            /
          sum(rate(dawos_http_requests_total[5m])) by (instance)
            > 0.05
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High error rate on {{ $labels.instance }}"
          description: "More than 5% of HTTP requests are returning 5xx errors."

      # Slow responses (P95 above 2 seconds)
      - alert: DawosSlowResponses
        expr: |
          histogram_quantile(0.95,
            sum(rate(dawos_http_request_duration_seconds_bucket[5m])) by (le, instance)
          ) > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Slow API responses on {{ $labels.instance }}"
          description: "P95 response time exceeds 2 seconds."

      # accel-cmd failures (sustained error rate)
      - alert: DawosAccelCmdErrors
        expr: rate(dawos_accel_cmd_errors_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "accel-cmd failures on {{ $labels.instance }}"
          description: "accel-cmd is failing at a sustained rate. Check accel-ppp service status."

      # Rate limiting active (clients being throttled)
      - alert: DawosRateLimitActive
        expr: rate(dawos_rate_limit_hits_total[5m]) > 1
        for: 10m
        labels:
          severity: info
        annotations:
          summary: "Rate limiting active on {{ $labels.instance }}"
          description: "Clients are being rate-limited. Consider increasing DAWOS_RATE_LIMIT."
```

### Alertmanager Integration

Route DawOS Agent alerts to your notification channel:

```yaml
# alertmanager.yml
route:
  receiver: default
  routes:
    - match:
        job: dawos-agent
        severity: critical
      receiver: pager
      repeat_interval: 5m
    - match:
        job: dawos-agent
        severity: warning
      receiver: slack
      repeat_interval: 30m

receivers:
  - name: slack
    slack_configs:
      - api_url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
        channel: "#bng-alerts"
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ .CommonAnnotations.description }}'

  - name: pager
    webhook_configs:
      - url: "https://your-pager-service/webhook"
```

---

## Health Probes

### Liveness Probe

`GET /health` returns HTTP 200 whenever the process is running. Use this for load balancer health checks and container orchestrator liveness probes.

```bash
curl -sf http://localhost:8470/health
```

Response:

```json
{
  "status": "ok",
  "node_name": "bng-prod-01",
  "version": "0.2.0",
  "uptime_seconds": 86412.3
}
```

### Readiness Probe

`GET /health/ready` validates that the agent can communicate with the accel-ppp daemon. Returns HTTP 200 when all checks pass, HTTP 503 when any dependency is unreachable.

```bash
curl -sf http://localhost:8470/health/ready
```

Response (healthy):

```json
{
  "ready": true,
  "checks": [
    {
      "service": "accel-ppp",
      "reachable": true,
      "detail": "1.13.0-f4014a4"
    }
  ]
}
```

Response (unhealthy, HTTP 503):

```json
{
  "ready": false,
  "checks": [
    {
      "service": "accel-ppp",
      "reachable": false,
      "detail": "accel-ppp unreachable"
    }
  ]
}
```

### Kubernetes Probes

If deploying in a containerized environment:

```yaml
# deployment.yaml
spec:
  containers:
    - name: dawos-agent
      ports:
        - containerPort: 8470
      livenessProbe:
        httpGet:
          path: /health
          port: 8470
        initialDelaySeconds: 5
        periodSeconds: 10
      readinessProbe:
        httpGet:
          path: /health/ready
          port: 8470
        initialDelaySeconds: 10
        periodSeconds: 15
        failureThreshold: 3
```

### HAProxy / Nginx Health Check

**HAProxy:**

```
backend dawos_agents
    option httpchk GET /health
    http-check expect status 200
    server bng-01 10.0.1.1:8470 check inter 10s fall 3 rise 2
    server bng-02 10.0.1.2:8470 check inter 10s fall 3 rise 2
```

**Nginx:**

```nginx
upstream dawos_agents {
    server 10.0.1.1:8470;
    server 10.0.1.2:8470;
}

server {
    location /api/ {
        proxy_pass http://dawos_agents;
    }

    location = /health {
        proxy_pass http://dawos_agents;
        access_log off;
    }
}
```

---

## WebSocket Real-time Events

### Connection

DawOS Agent provides a WebSocket endpoint for streaming server-side events in real time. Authentication uses the API key as a query parameter:

```
ws://host:8470/ws/events?key=YOUR_API_KEY
```

The minimum required role is **viewer**.

### Channels

Events are organized into four channels:

| Channel | Events |
|---------|--------|
| `session` | PPPoE session lifecycle (connect, disconnect, change) |
| `config` | Configuration mutations (write, rollback, checkpoint) |
| `audit` | HTTP audit trail for mutating requests |
| `system` | Service-level events (start, stop, health change) |

By default, new connections receive events from all channels.

### Client Protocol

After connecting, the client can send JSON control messages:

**Subscribe to specific channels:**

```json
{"action": "subscribe", "channels": ["session", "config"]}
```

**Unsubscribe from channels:**

```json
{"action": "unsubscribe", "channels": ["audit"]}
```

**Keepalive ping:**

```json
{"action": "ping"}
```

The server responds with `{"action": "pong"}`.

### Event Format

Events arrive as JSON messages:

```json
{
  "channel": "session",
  "type": "session.connect",
  "data": {
    "username": "customer-001",
    "ip": "10.0.0.15",
    "ifname": "ppp0"
  },
  "timestamp": "2026-07-09T12:00:00+00:00"
}
```

### Python Client Example

```python
import asyncio
import json
import websockets

async def listen():
    uri = "ws://10.0.1.1:8470/ws/events?key=YOUR_API_KEY"
    async with websockets.connect(uri) as ws:
        # Subscribe to session events only
        await ws.send(json.dumps({
            "action": "subscribe",
            "channels": ["session"]
        }))

        async for message in ws:
            event = json.loads(message)
            print(f"[{event['channel']}] {event['type']}: {event['data']}")

asyncio.run(listen())
```

### JavaScript Client Example

```javascript
const ws = new WebSocket("ws://10.0.1.1:8470/ws/events?key=YOUR_API_KEY");

ws.onopen = () => {
  // Subscribe to session and config channels
  ws.send(JSON.stringify({
    action: "subscribe",
    channels: ["session", "config"]
  }));
};

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`[${data.channel}] ${data.type}:`, data.data);
};

ws.onclose = (event) => {
  console.log(`Connection closed: ${event.code} ${event.reason}`);
};
```

### Integration with External Systems

Use WebSocket events to trigger external actions:

- **Session events** to update a customer portal or billing system in real time.
- **Config events** to log configuration changes to a CMDB or change management system.
- **Audit events** to feed a SIEM or compliance platform.
- **System events** to trigger PagerDuty or Opsgenie incidents.

---

## Audit Logging

### Audit Log Endpoint

`GET /api/v1/audit` returns recent write operations from the in-memory ring buffer (default size: 1000 entries). Requires admin-level API key.

```bash
curl -sf -H 'X-API-Key: YOUR_ADMIN_KEY' http://localhost:8470/api/v1/audit
```

### Audit Entry Format

Each audit entry records:

| Field | Description |
|-------|-------------|
| `timestamp` | ISO 8601 UTC timestamp |
| `method` | HTTP method (POST, PUT, PATCH, DELETE) |
| `path` | Request path |
| `client_ip` | Remote IP address |
| `request_id` | Trace ID (from `X-Request-ID` header or auto-generated) |
| `role` | RBAC role of the caller (viewer, operator, admin) |
| `status` | HTTP response status code |
| `duration_ms` | Response time in milliseconds |

### Structured Log Aggregation

When `DAWOS_LOG_FORMAT=json` is enabled in `agent.env`, audit entries are written as structured JSON to the application log. This integrates directly with log aggregators:

**Filebeat configuration:**

```yaml
filebeat.inputs:
  - type: journald
    id: dawos-agent
    include_matches:
      - _SYSTEMD_UNIT=dawos-agent.service

processors:
  - decode_json_fields:
      fields: ["message"]
      target: ""
      overwrite_keys: true

output.elasticsearch:
  hosts: ["http://elasticsearch:9200"]
  index: "dawos-agent-%{+yyyy.MM.dd}"
```

**Loki with Promtail:**

```yaml
# promtail.yml
scrape_configs:
  - job_name: dawos-agent
    journal:
      labels:
        job: dawos-agent
      path: /var/log/journal
    relabel_configs:
      - source_labels: ["__journal__systemd_unit"]
        target_label: unit
    pipeline_stages:
      - match:
          selector: '{unit="dawos-agent.service"}'
          stages:
            - json:
                expressions:
                  level: level
                  message: message
            - labels:
                level:
```

### Request Tracing

Every response includes an `X-Request-ID` header. If the caller supplies the header, DawOS Agent reuses it for distributed tracing. Otherwise, a random UUID is generated.

To trace a request through the system:

```bash
# Send a request with a trace ID
curl -sf -H 'X-API-Key: KEY' -H 'X-Request-ID: trace-abc123' \
  http://localhost:8470/api/v1/sessions

# Find the trace in logs
sudo journalctl -u dawos-agent | grep 'trace-abc123'
```

---

## Monitoring API

The `/api/v1/monitoring` endpoints manage monitoring exporters (Prometheus node exporter, SNMP exporter) installed on the BNG host.

### Check Monitoring Status

```bash
curl -sf -H 'X-API-Key: YOUR_KEY' http://localhost:8470/api/v1/monitoring/status
```

### Get Exporter Metrics

```bash
curl -sf -H 'X-API-Key: YOUR_KEY' \
  http://localhost:8470/api/v1/monitoring/metrics/node-exporter
```

### Enable/Disable an Exporter

```bash
# Enable
curl -sf -X POST -H 'X-API-Key: YOUR_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"service": "node-exporter", "enable": true}' \
  http://localhost:8470/api/v1/monitoring/configure

# Disable
curl -sf -X POST -H 'X-API-Key: YOUR_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"service": "snmp-exporter", "enable": false}' \
  http://localhost:8470/api/v1/monitoring/configure
```

### Restart an Exporter

```bash
curl -sf -X POST -H 'X-API-Key: YOUR_KEY' \
  http://localhost:8470/api/v1/monitoring/restart/node-exporter
```

---

## Quick Reference

### Verify the Monitoring Stack

Run these commands to confirm all monitoring interfaces are operational:

```bash
# 1. Prometheus metrics endpoint
curl -sf http://localhost:8470/metrics | head -5

# 2. Application-specific metrics
curl -sf http://localhost:8470/metrics | grep dawos_

# 3. Liveness probe
curl -sf http://localhost:8470/health

# 4. Readiness probe
curl -sf http://localhost:8470/health/ready

# 5. WebSocket connectivity (requires wscat or websocat)
wscat -c "ws://localhost:8470/ws/events?key=YOUR_KEY" \
  -x '{"action": "ping"}'

# 6. Audit log
curl -sf -H 'X-API-Key: YOUR_ADMIN_KEY' http://localhost:8470/api/v1/audit
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DAWOS_RATE_LIMIT` | `120/minute` | Per-IP rate limit (empty to disable) |
| `DAWOS_LOG_FORMAT` | `text` | Log format — `json` for structured logging |
| `DAWOS_LOG_LEVEL` | `info` | Log verbosity |
| `DAWOS_AUDIT_BUFFER_SIZE` | `1000` | In-memory audit ring buffer size |
| `DAWOS_RETRY_MAX` | `3` | Max retry attempts for transient failures |
| `DAWOS_RETRY_DELAY` | `1.0` | Base retry delay in seconds |
