# Cuncun Core API v1 contract

> Status: design contract; endpoints are not implemented yet.
> Last updated: 2026-08-13.

This document fixes the boundary that future `cuncun-console` and
`cuncun-voice-gateway` clients will consume. API v1 is a domain API—not an HTTP
mirror of SQLite, Chroma, Flask internals, or Feishu payloads.

## Boundary

```text
Browser -> Console BFF -----\
                             -> Core API v1 -> application services -> domain ports
Voice client -> Voice BFF --/                                  -> adapters
```

Console and Voice processes must not mount Core database, backup, prompt, memory,
or artifact directories. They receive only typed DTOs with opaque public IDs.

## P0 endpoints

| Method and path | Purpose | Required scope |
|:---|:---|:---|
| `GET /api/v1/health/live` | Process liveness; returns only `status=ok` | Public |
| `GET /api/v1/health/ready` | Safe readiness signal without component details | Public |
| `GET /api/v1/system/health` | Redacted component, provider, resource, and degradation summary | `system:read` |
| `GET /api/v1/capabilities` | Core/API versions and available feature flags | `core:read` |
| `GET /api/v1/subjects` | Authorized subject directory using opaque Core IDs | `subjects:read` |
| `GET /api/v1/subjects/{sid}/conversations` | Conversation metadata; no message bodies | `conversations:read` |
| `POST /api/v1/subjects/{sid}/conversations` | Create a conversation | `conversations:write` |
| `PATCH /api/v1/subjects/{sid}/conversations/{cid}` | Update allowlisted title or mode fields | `conversations:write` |
| `POST /api/v1/subjects/{sid}/turns` | Channel-neutral conversation turn for Voice | `turns:create` |
| `GET /api/v1/subjects/{sid}/memory-items` | Unified memory review view | `memory:read_sensitive` |
| `POST /api/v1/subjects/{sid}/memory-items/{mid}:forget` | Idempotent, subject-bound forget action | `memory:moderate` |
| `GET /api/v1/observability/summary` | Redacted aggregate metrics | `observability:read` |

P1 may add message bodies behind `conversations:content:read`, a read-only
presence endpoint, an explicit `presence:refresh` write action, persistent
traces, and initiative review. Initiative generation, approval, rejection, and
send remain separate actions; there is no endpoint that silently approves and
sends in one call.

## Authentication and authorization

Core accepts service-to-service credentials only:

```http
Authorization: Bearer <opaque-service-token>
```

- Console BFF owns browser authentication, cookies, and CSRF protection.
- `cuncun-console` receives only its management scopes and authorized subjects.
- `cuncun-voice-gateway` normally receives only `turns:create` and a narrow
  subject allowlist.
- Missing or invalid credentials return `401`.
- Missing scope or subject access returns `404` to resist identifier probing.
- Tokens are high entropy; Core stores only their hashes and supports key IDs
  and overlapping rotation.
- Core listens on loopback or a private network by default, with no CORS.
  Internet exposure requires a TLS or mTLS reverse proxy.
- Authorization headers and complete request bodies are never logged.

The existing health/presence single-purpose tokens are compatibility settings,
not the authentication model for API v1.

## IDs and subject isolation

API identifiers are opaque and stable, such as `sub_...`, `conv_...`,
`msg_...`, and `mem_...`. Feishu `open_id`, SQLite row IDs, vector IDs, table
names, and path-derived IDs never cross the boundary.

Every repository lookup is scoped by the authenticated principal and
`subject_id`. Child IDs must not be queried globally and checked afterward.
A caller cannot enumerate whether another subject or resource exists.

## Envelope

Successful response:

```json
{
  "data": {},
  "meta": {
    "request_id": "req_opaque",
    "api_version": "v1",
    "timestamp": "2026-08-13T12:00:00Z"
  }
}
```

Error response:

```json
{
  "error": {
    "code": "validation_error",
    "message": "Invalid request",
    "details": [
      {"field": "input.text", "reason": "too_long"}
    ]
  },
  "meta": {
    "request_id": "req_opaque",
    "api_version": "v1",
    "timestamp": "2026-08-13T12:00:00Z"
  }
}
```

Internal paths, SQL, provider payloads, stack traces, and raw exception messages
never appear in the response.

## Voice turn

Request:

```http
POST /api/v1/subjects/sub_opaque/turns
Idempotency-Key: client-generated-opaque-value
Content-Type: application/json
```

```json
{
  "conversation_id": "conv_opaque",
  "input": {
    "type": "text",
    "text": "今天过得怎么样？"
  },
  "client": {
    "channel": "voice",
    "session_id": "opaque-client-session",
    "locale": "zh-CN"
  }
}
```

Clients cannot provide a system prompt, model, temperature, tool list, storage
ID, or arbitrary memory switch. Response:

```json
{
  "data": {
    "turn_id": "turn_opaque",
    "conversation_id": "conv_opaque",
    "user_message_id": "msg_opaque",
    "assistant_message": {
      "id": "msg_opaque",
      "text": "……",
      "speech_hints": {
        "emotion": "calm",
        "theme": "daily"
      }
    }
  },
  "meta": {
    "request_id": "req_opaque",
    "api_version": "v1",
    "timestamp": "2026-08-13T12:00:00Z"
  }
}
```

The response never includes prompts, retrieved context, local media paths,
vector metadata, or provider credentials.

A new headless `CoreTurnService` must implement this use case. The current
Feishu reply path has channel side effects, so it must not be wrapped directly.
Feishu and Voice adapters will both call the headless service. An explicit
`conversation_id` must flow through context assembly to avoid races around a
subject's currently active conversation.

## Consistency and retries

- All timestamps use UTC RFC 3339.
- Lists use opaque cursors, never database offsets.
- Sensitive responses include `Cache-Control: no-store`.
- Turns, forget actions, initiative decisions, and sends require
  `Idempotency-Key`.
- Reusing a key with a different body returns `409 idempotency_conflict`.
- Idempotency records are persistent; in-process event deques are insufficient.
- Editable resources return `ETag`; writes require `If-Match`. A stale version
  returns `412 precondition_failed`.
- Per-principal and per-subject request limits apply to all write endpoints.

## Privacy defaults

- Public health endpoints reveal neither component names nor deployment data.
- Authenticated health and observability use response-field allowlists and
  aggregate counts; they omit subject IDs, text previews, paths, and event
  details.
- Conversation lists expose title, mode, message count, and timestamps only.
- Message bodies require the separate sensitive scope.
- Presence reads never call AI or mutate a snapshot. Refresh is an explicit,
  authenticated write action.
- Presence omits chat hints, memory hints, media prompts, and media keys by
  default.
- Settings APIs expose typed allowlisted preferences, never arbitrary key/value
  storage.

## Preconditions before sensitive endpoints

Before `:forget` is exposed, retrieval must revalidate SQLite active state and
remove stale vectors through a retryable outbox. Changing SQLite status alone is
not sufficient if vector retrieval can still recall the memory.

Before initiative endpoints are exposed, Core needs a persistent state machine
for candidate, reviewed, approved, rejected, sent, and failed states. Approval
and delivery are distinct, audited operations.

Before traces are exposed, Core needs a persistent redacted trace repository
and DTO allowlist. In-process diagnostic events are not an API contract.

## Compatibility

The major version is carried in the path. Core package versions continue to use
SemVer independently.

API v1 may add optional fields, enum values, and endpoints. It must not remove
or rename fields, change field types, or add required request fields. Clients
must ignore unknown response fields and enum values.

`GET /api/v1/capabilities` reports `core_version`, `api_major`, and feature
flags. Breaking changes move to `/api/v2`; deprecation uses `Deprecation` and
`Sunset` headers plus a migration guide for at least one public release cycle.

An OpenAPI document becomes the executable source of truth when P0
implementation begins. CI will then validate schema changes and consumer
contracts for Console and Voice.

## Implementation order

1. Blueprint, envelope, stable errors, scoped auth, capabilities, live, and ready.
2. Subject directory and opaque public IDs.
3. Headless `CoreTurnService`, persistent idempotency, and synchronous turns.
4. Conversation metadata and unified `MemoryReviewService`.
5. Persistent redacted traces.
6. Initiative queue, human review, and independently gated delivery.
