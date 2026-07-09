# Architecture Decision Records

This document captures the key architectural decisions made during DawOS Agent development, their context, and their consequences. Each record follows the format: context (why the decision was needed), decision (what was chosen), and consequences (trade-offs accepted).

---

## ADR-001: FastAPI as the HTTP Framework

**Status:** Accepted  
**Date:** 2025-12-01

### Context

DawOS Agent needs to expose a REST API that wraps accel-ppp CLI commands and Linux system utilities. The framework must support async operations (subprocess calls), automatic OpenAPI documentation, request validation, and middleware composition.

### Decision

Use FastAPI with Uvicorn as the ASGI server, Pydantic v2 for request/response validation, and pydantic-settings for configuration management.

### Consequences

- Automatic OpenAPI/Swagger documentation for all 138 endpoints.
- Native async support for subprocess-based service calls without blocking the event loop.
- Pydantic v2 provides strict type validation and serialization with minimal boilerplate.
- Python 3.9+ requirement excludes older distributions (Ubuntu 18.04 and below).
- Single-process deployment is sufficient for the expected load profile (one BNG node, operational API traffic).

---

## ADR-002: Router-Service-Shell Architecture

**Status:** Accepted  
**Date:** 2025-12-01

### Context

The codebase needs a clear separation between HTTP handling, business logic, and system command execution. Without structure, endpoint handlers tend to accumulate shell commands, validation, and response formatting in a single function.

### Decision

Adopt a three-layer architecture:

1. **Routers** (`routers/`) handle HTTP concerns only — request parsing, response models, error codes.
2. **Services** (`services/`) contain business logic and orchestrate shell commands.
3. **Shell execution** uses a per-module `_run()` helper that wraps `asyncio.create_subprocess_exec`.

Each service module defines its own `_run()` function rather than sharing a global one. This duplication is intentional (`duplicate-code` is disabled in pylint configuration).

### Consequences

- Clear responsibility boundaries make it easy to test each layer independently.
- Router tests mock at the service level; service tests mock at the subprocess level.
- The duplicated `_run()` pattern means each service is self-contained and can be modified without affecting others.
- Adding a new domain requires three files (router, service, test) following the established pattern.

---

## ADR-003: API Key Authentication with RBAC

**Status:** Accepted  
**Date:** 2026-01-15

### Context

The agent runs on BNG nodes that are not internet-facing but are accessible from the operator network. Authentication must be simple to configure (single environment variable) while supporting role-based access control for multi-user scenarios.

### Decision

Implement API key authentication via the `X-API-Key` HTTP header with three role tiers:

- **Viewer** — read-only access (GET endpoints).
- **Operator** — read + write access (POST, PUT, DELETE).
- **Admin** — full access including audit logs and system configuration.

Keys are configured in `agent.env` using the `DAWOS_API_KEY` (operator), `DAWOS_VIEWER_KEY`, and `DAWOS_ADMIN_KEY` variables. Invalid or missing keys return HTTP 401 (not 403).

### Consequences

- Simple single-header auth works with all HTTP clients, scripts, and automation tools.
- WebSocket connections cannot use header-based auth during the handshake, so the `/ws/events` endpoint accepts the key as a query parameter (`?key=...`).
- No session management, token refresh, or OAuth complexity.
- Key rotation requires a service restart (the agent reads configuration at startup only).
- Suitable for internal network deployments; not intended for public-facing use without a reverse proxy.

---

## ADR-004: Prometheus Metrics via prometheus_client

**Status:** Accepted  
**Date:** 2026-02-01

### Context

Operators need visibility into API request rates, error rates, response latency, and accel-ppp command health. The monitoring solution must integrate with existing ISP infrastructure (typically Prometheus + Grafana).

### Decision

Use the `prometheus_client` library to instrument the application. Expose metrics at `GET /metrics` in Prometheus text exposition format. The endpoint is public (no auth) and exempt from rate limiting.

Metrics are collected by a pure ASGI middleware (`MetricsMiddleware`) rather than `BaseHTTPMiddleware` to avoid known stacking issues in Starlette.

### Consequences

- Standard Prometheus integration with no additional exporters required.
- The `endpoint` label uses route templates (e.g. `/api/v1/sessions/{username}`) to prevent cardinality explosion from dynamic path segments.
- Self-instrumentation paths (`/metrics`, `/health`, `/health/ready`) are excluded from recording.
- No authentication on `/metrics` means it should not be exposed to untrusted networks without a reverse proxy.

---

## ADR-005: Pure ASGI Middleware for Metrics

**Status:** Accepted  
**Date:** 2026-02-01

### Context

The application uses three middleware layers: `RequestIdMiddleware`, `AuditLogMiddleware`, and `MetricsMiddleware`. Stacking three or more `BaseHTTPMiddleware` instances in Starlette can cause issues with request body consumption and response streaming.

### Decision

Implement `MetricsMiddleware` as a pure ASGI middleware (raw `__call__` with `scope/receive/send`) instead of inheriting from `BaseHTTPMiddleware`. The other two middlewares remain as `BaseHTTPMiddleware` since they execute before the metrics layer.

### Consequences

- Avoids the known Starlette issue with deeply stacked `BaseHTTPMiddleware`.
- The ASGI middleware captures the response status code via a `send_wrapper` without interfering with streaming responses (SSE, WebSocket upgrades).
- Slightly more verbose implementation compared to `BaseHTTPMiddleware`, but more reliable.

---

## ADR-006: In-Memory Audit Buffer

**Status:** Accepted  
**Date:** 2026-03-01

### Context

Operators need to review recent write operations without parsing log files. A persistent database would add deployment complexity (the agent runs on BNG nodes with minimal infrastructure).

### Decision

Maintain an in-memory ring buffer (`collections.deque` with `maxlen`) that stores the most recent audit entries. Expose the buffer via `GET /api/v1/audit` (admin-only). The buffer size is configurable via `DAWOS_AUDIT_BUFFER_SIZE` (default: 1000).

Audit entries are also written to the application log and fired as webhook events for external persistence.

### Consequences

- No database dependency — the agent remains a single-binary deployment.
- Audit data is lost on service restart (acceptable because the log and webhooks provide persistent alternatives).
- Fixed memory footprint regardless of request volume.
- The ring buffer naturally evicts the oldest entries, providing a rolling window of recent activity.

---

## ADR-007: Webhook Event Delivery

**Status:** Accepted  
**Date:** 2026-03-15

### Context

External systems (billing, monitoring, CMDB) need to react to events on the BNG node. Polling the API is inefficient and introduces latency.

### Decision

Implement a fire-and-forget webhook system that sends HTTP POST requests to configured URLs when specific events occur. Webhooks are non-blocking — delivery failures do not affect API response times or availability.

### Consequences

- External systems receive near-real-time notifications without polling.
- Fire-and-forget means no delivery guarantees — if the receiver is down, events are lost.
- No retry mechanism for failed webhook deliveries (by design, to avoid blocking the event loop).
- Webhook URLs are configured in `agent.env` and require a restart to change.

---

## ADR-008: WebSocket Event Bus for Real-time Streaming

**Status:** Accepted  
**Date:** 2026-07-01

### Context

The webhook system provides push notifications to external services, but operators and dashboards need a persistent, low-latency connection for real-time monitoring of session events, configuration changes, and audit trail.

### Decision

Implement an in-memory event bus (`EventBus`) backed by per-subscriber `asyncio.Queue` objects. Expose it via a WebSocket endpoint at `/ws/events` with API key authentication via query parameter.

The bus supports four channels (`session`, `config`, `audit`, `system`) with client-controlled subscriptions via JSON control messages.

### Consequences

- Sub-second event delivery to connected clients.
- Per-subscriber queues prevent slow consumers from blocking the publisher (full queues are skipped).
- Authentication via query parameter is necessary because WebSocket handshakes cannot use standard HTTP header dependencies.
- In-memory only — no event persistence or replay. Clients that disconnect miss events during the disconnection period.
- The `asyncio.Queue` maxsize (default 100) bounds memory usage per subscriber.

---

## ADR-009: Rate Limiting with SlowAPI

**Status:** Accepted  
**Date:** 2026-02-15

### Context

The API is exposed on the operator network where automated scripts or misconfigured clients could overwhelm the agent. A rate limiter protects the accel-ppp daemon from excessive subprocess spawning.

### Decision

Use SlowAPI (a Starlette-compatible rate limiter) with per-IP limiting. The default limit is `120/minute`, configurable via `DAWOS_RATE_LIMIT`. Health and metrics endpoints are exempt.

### Consequences

- Protects against accidental API abuse from scripts or monitoring tools with aggressive intervals.
- Per-IP limiting means a misbehaving client does not affect other clients.
- Rate-limited requests return HTTP 429 with a `Retry-After` header.
- The `dawos_rate_limit_hits_total` Prometheus metric tracks rejection volume.
- Setting `DAWOS_RATE_LIMIT=` (empty) disables limiting entirely.

---

## ADR-010: Retry with Exponential Backoff

**Status:** Accepted  
**Date:** 2026-02-15

### Context

`accel-cmd` occasionally fails with transient errors (CLI port busy, momentary process contention). Without retry logic, these transient failures propagate as HTTP 500 errors to the caller.

### Decision

Wrap `accel-cmd` calls in an exponential backoff retry loop. The maximum number of attempts (`DAWOS_RETRY_MAX`, default 3) and base delay (`DAWOS_RETRY_DELAY`, default 1.0s) are configurable. Each retry is tracked by the `dawos_accel_cmd_retries_total` Prometheus counter.

### Consequences

- Transient `accel-cmd` failures are automatically recovered without caller intervention.
- The retry counter provides visibility into accel-ppp stability — a rising retry rate indicates an underlying issue.
- Maximum latency for a retried request is bounded: `sum(delay * 2^i for i in range(max_retries))`.
- Only `accel-cmd` calls are retried, not arbitrary shell commands — this prevents retrying destructive operations.

---

## ADR-011: DELETE Returns 204 No Content

**Status:** Accepted  
**Date:** 2026-01-15

### Context

REST API conventions vary on DELETE response bodies. Some APIs return the deleted resource, others return a confirmation message, and others return no body.

### Decision

All DELETE endpoints return HTTP 204 with no response body. No `response_model` is declared on DELETE route decorators. Error conditions still raise `HTTPException` with appropriate status codes and detail messages.

### Consequences

- Consistent behavior across all DELETE endpoints.
- Clients can check for `204` without parsing a response body.
- If a client needs to verify the deletion, it should follow up with a GET request.

---

## ADR-012: Least-Privilege Sudoers

**Status:** Accepted  
**Date:** 2025-12-15

### Context

DawOS Agent runs as an unprivileged `dawos` user but needs to execute certain system commands (`nft`, `ip`, `tc`, `vtysh`, `sysctl`, `tee`) that require root privileges.

### Decision

Grant passwordless sudo access to exactly six commands via `/etc/sudoers.d/dawos-agent`. The agent process runs as `dawos:dawos` with no other elevated privileges. The systemd unit uses `ReadWritePaths` to restrict filesystem access.

### Consequences

- The attack surface is limited to six well-defined system commands.
- Compromising the agent process does not grant unrestricted root access.
- Adding new privileged operations requires updating the sudoers file, systemd unit, and documentation — a deliberate friction that forces security review.

---

## ADR-013: Structured Logging with Text/JSON Toggle

**Status:** Accepted  
**Date:** 2026-02-01

### Context

Development environments benefit from human-readable text logs, while production deployments need structured JSON for log aggregators (ELK, Loki, CloudWatch).

### Decision

Support two log formats controlled by `DAWOS_LOG_FORMAT`:

- `text` (default) — human-readable, colored output suitable for `journalctl` and terminal viewing.
- `json` — structured JSON with consistent fields (`timestamp`, `level`, `message`, `request_id`) for machine parsing.

Both formats include the request ID from `X-Request-ID` for distributed tracing.

### Consequences

- Same codebase serves both development and production logging needs.
- JSON format integrates with Filebeat, Promtail, Fluentd, and other log shippers without custom parsing rules.
- The audit logger (`dawos_agent.audit`) uses the same format, allowing log aggregators to filter audit entries by logger name.
- No external logging dependencies — uses Python's built-in `logging` module with custom formatters.

---

## ADR-014: Config Checkpoint and Rollback

**Status:** Accepted  
**Date:** 2026-04-01

### Context

Applying configuration changes to a production BNG node carries risk. A misconfigured `accel-ppp.conf` can disconnect all active PPPoE sessions. Operators need a way to quickly revert to a known-good configuration.

### Decision

Implement a checkpoint system that:

1. Creates a timestamped backup before applying changes (`POST /api/v1/config/checkpoint`).
2. Stores checkpoints in `/etc/accel-ppp.d/checkpoints/` with ISO 8601 filenames.
3. Supports rollback to any checkpoint (`POST /api/v1/config/checkpoint/rollback`).
4. Lists available checkpoints (`GET /api/v1/config/checkpoints`).

### Consequences

- Operators can safely apply changes knowing they can roll back in seconds.
- Checkpoint storage is local to the BNG node — no external dependencies.
- The `dawos` user needs write access to `/etc/accel-ppp.d/` (documented in installation guide).
- No automatic rollback on failure — the operator must explicitly trigger rollback if the health check fails after applying changes. The deploy wizard in dawos-cli automates this workflow.
