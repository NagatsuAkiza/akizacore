# Explicit Memory CRUD and AI Maintenance Design

## Goal

Add a privacy-preserving, explicit memory feature for AI conversations without introducing
embeddings, vector search, or multi-agent orchestration. Users must choose what is stored and
must be able to inspect and remove it.

## Scope

### Included

- A `memories` database table for user-created memories.
- Repository and service operations for creating, listing, deleting, and clearing memories.
- Guild-scoped slash commands:
  - `/memory save`
  - `/memory list`
  - `/memory delete`
  - `/memory clear`
- Retrieval of a small, bounded set of active memories during AI context construction.
- Isolation by Discord user and guild.
- Tests for CRUD, isolation, prompt integration, opt-out behavior, and maintenance failures.
- A focused audit of conversation retention and `/forget` behavior.

### Excluded

- Automatic memory extraction from ordinary chat.
- Embedding providers, pgvector, semantic search, or similarity ranking.
- Cross-guild memory sharing.
- Multi-agent or task-planner implementation.
- Dashboard work.
- Redis or durable confirmation-state work.

## Data model

Add a `memories` table with:

- `id`: integer primary key.
- `user_id`: Discord user ID, foreign key to `users`, indexed.
- `server_id`: Discord guild ID, foreign key to `servers`, indexed.
- `content`: validated text stored as `Text`.
- `created_at`: timezone-aware timestamp.
- `updated_at`: timezone-aware timestamp if supported by the project conventions.
- `deleted_at`: nullable timestamp for soft deletion, if compatible with existing repository patterns.

The first implementation may use hard deletion for `/memory delete` and `/memory clear` if that
matches the existing schema conventions; the user-visible behavior must be deletion and no
subsequent retrieval. A unique content constraint is not required because deduplication is not
needed for the first explicit CRUD version.

## Service and repository boundaries

The repository owns SQL queries and returns typed model data. The service owns:

- content validation and length limits;
- user/server ownership scope;
- list ordering and result limits;
- empty-result behavior;
- deletion counts;
- opt-out policy.

The Discord cog remains thin and converts interaction inputs into service calls. No Discord types
may enter the repository or service layer.

Memory access is always filtered by both `server_id` and `user_id`. Bot-owner status does not
allow reading or deleting another user's memory.

## AI context integration

The orchestrator retrieves active memories for the current `(server_id, user_id)` scope before
building the prompt. It passes at most a small configured limit and a configured character budget.
Memories are labeled as user-provided context, not system instructions, so stored text cannot
override authorization, tool permissions, or safety rules.

When the user has opted out of AI, the orchestrator must not retrieve or write memory through AI
flows. Explicit memory commands should follow the same privacy policy and return a clear response
when memory is unavailable due to opt-out.

`/forget` continues to delete conversation history only. `/memory clear` is the explicit operation
for deleting saved memories, and help text must distinguish the two.

## Maintenance and privacy audit

The maintenance cog continues to purge expired conversation history. It must:

- wait for bot readiness before running;
- log failures without terminating the scheduled loop;
- report deletion counts on successful runs;
- preserve active conversations according to the configured retention cutoff.

Tests will cover the service-not-configured path and a purge exception. The implementation should
avoid changing retention semantics unless the audit finds a concrete bug.

## Error handling

- Invalid or blank memory content returns the repository-standard validation error.
- Missing or foreign memory IDs behave as not found within the caller's scope.
- Database/provider failures are logged or surfaced using existing application error handling;
  they must not return success-shaped messages.
- A failed AI request must not create or mutate memories.

## Validation

Add focused tests for:

1. Save, list, delete, and clear behavior.
2. User and guild isolation.
3. List limits and ordering.
4. Memory context inclusion and character bounds.
5. Opt-out behavior.
6. `/forget` not deleting explicit memories.
7. Maintenance no-op and exception paths.

Run the complete existing validation after implementation:

```powershell
.venv\Scripts\python.exe -m pytest
.venv\Scripts\ruff.exe check src tests
.venv\Scripts\ruff.exe format --check src tests
.venv\Scripts\python.exe -m mypy src
```

The implementation is complete when all listed behavior is covered, the full validation commands
pass, and no dashboard or multi-agent files are introduced.
