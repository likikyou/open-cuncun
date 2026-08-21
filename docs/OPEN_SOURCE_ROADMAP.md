# Open-source scope and roadmap

> Last updated: 2026-08-13

`open-cuncun` is the canonical public source for Cuncun Core: a self-hosted,
Feishu-first AI companion runtime. It is not a mirror of a downstream
deployment. Generic runtime improvements should be designed here first,
released with a tag, and then consumed by downstream deployments.

## Repository map

The project is intentionally split into three focused repositories, with one
optional product kept separate until its design is mature:

| Repository | Responsibility | Status |
|:---|:---|:---|
| `open-cuncun` | Core runtime: webhook, conversations, memory, model routing, tools, scheduling, provider adapters, and stable API contracts | Active canonical repository |
| `cuncun-console` | Optional operator UI and BFF consuming Core API v1; no direct access to the Core database | Planned after API v1 is implemented |
| `cuncun-voice-gateway` | Optional speech input/output and media-delivery adapter; no persona or memory ownership | Planned after API v1 is implemented |
| `cuncun-knowledge-war` | Standalone learning/game product with its own domain, UI, and release cadence | Deferred; publish only after an independent content and license review |

Keeping `open-cuncun` avoids a disruptive rename while the public API is still
forming. A rename to `cuncun-core` may be considered for a 6.0 release with
redirects and a migration guide. `open-chat-cuncun` is not used because the
runtime already covers memory, proactive tasks, vision, and operations—not only
chat.

## What belongs in Cuncun Core

- protocol-neutral conversation, memory, context, model-routing, and tool ports
- Feishu/Lark as the first maintained transport adapter
- generic provider integrations and safe fallback behavior
- generic scheduling, initiative policy, observability, and evaluation primitives
- privacy-preserving API contracts and reference fixtures
- offline tests, deployment examples, and public-safe operational documentation

## What stays outside

- credentials, tokens, domains, host addresses, local filesystem paths, and process secrets
- real user conversations, memories, traces, databases, backups, or generated logs
- private personas, relationship history, operator policy, and deployment-specific prompts
- unlicensed voice, image, video, font, dataset, or game content
- deployment-specific Console pages and one-off business rules

Downstream deployments may compose public packages, but should not become the
upstream source of truth. Reusable changes return through a clean,
public-oriented implementation or a reviewed patch—not through a repository
mirror or history rewrite.

## Publication classes

Every feature moving into a public repository is classified before code moves:

| Class | Meaning | Action |
|:---|:---|:---|
| Public generic | General-purpose code with clean provenance and no deployment coupling | Port with tests and documentation |
| Public after rewrite | Useful idea coupled to private schemas, names, prompts, or paths | Reimplement against public ports and sanitized fixtures |
| Private only | Persona, relationship data, operator configuration, or owned runtime assets | Never publish |
| Blocked | License, provenance, privacy, or security is unclear | Keep out until reviewed |

## Release gate

Each public pull request must pass all of the following:

1. `python scripts/oss_release_audit.py`
2. `python scripts/verify.py --offline`
3. `python -m pytest tests`
4. `python -m ruff check app scripts tests`
5. Human review of prompts, screenshots, fixtures, dependency licenses, and migration notes

The automated audit is a guardrail, not proof that publication is safe. It
checks tracked filenames, common secret formats, runtime data, binary assets,
unexpectedly large files, and optional deployment-specific markers loaded from
an untracked file. Private/downstream release jobs should keep one marker per
line outside the repository and set `OSS_RELEASE_BLOCKLIST_FILE` (or pass
`--blocklist-file`). The audit never prints matched values. Reviewers must still
verify provenance and meaning.

## Delivery sequence

1. Stabilize the 5.8 Core refresh: public LLM ports, chat runner, opt-in Gemma
   vision, tests, documentation cleanup, and release audit.
2. Implement the protected, metadata-first Core API v1 described in
   [CORE_API_V1.md](CORE_API_V1.md).
3. Create `cuncun-console` against the API—never against SQLite files or Core
   implementation modules.
4. Create `cuncun-voice-gateway` against the same API and an explicit media
   contract.
5. Evaluate the separate learning/game repository only after its content and
   dependency provenance is independently cleared.

This structure keeps the useful platform small enough to understand while
allowing optional products to evolve without turning the Core repository into
a monolith.
