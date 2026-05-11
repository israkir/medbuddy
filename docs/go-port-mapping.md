# MedBuddy — Go Port Mapping

This document maps every Python module that carries business logic to its Go/Fiber equivalent.
The mapping is designed to be as mechanical as possible: one Python file → one Go file, one Python `Protocol` → one Go `interface`.

**Python paths:** Module paths in the tables below are relative to **`apps/backend/src/medbuddy/`** (the `medbuddy` installable package). Top-level files such as `config.py`, `main.py`, and `container.py` sit at the root of that tree.

---

## Naming conventions


| Python                    | Go                                                    |
| ------------------------- | ----------------------------------------------------- |
| `snake_case` module       | `snake_case` package or `camelCase` file in a package |
| `Protocol` class          | `interface` in `ports/` package                       |
| `@dataclass`              | `struct`                                              |
| `@dataclass(frozen=True)` | struct with only value receivers                      |
| `lru_cache` singleton     | `sync.Once` or package-level `var`                    |
| `async def`               | `func ... (ctx context.Context) error`                |
| `ConfigError`             | `errors.New` / sentinel error value                   |


---

## Package mapping

### Config


| Python                                                 | Go                                                                    |
| ------------------------------------------------------ | --------------------------------------------------------------------- |
| `config.py` → `load_settings(env)`                     | `config/config.go` → `Load(env map[string]string) (*Settings, error)` |
| `Settings` frozen dataclass                            | `Settings` struct                                                     |
| `IntegrationMode` / `LlmProvider` / `Locale` str enums | `type IntegrationMode string` etc. with `const` block                 |
| `get_settings()` lru_cache                             | `config.Get()` backed by `sync.Once`                                  |
| `ConfigError`                                          | `var ErrConfig = errors.New("config")` or typed sentinel              |


### Core utilities


| Python (`core/`)                                      | Go (`internal/core/`)                           |
| ----------------------------------------------------- | ----------------------------------------------- |
| `errors.py` — `Error`, `ConfigError`, `LLMParseError` | `core/errors.go` — typed error structs          |
| `i18n.py` — `t(key, locale)`                          | `core/i18n.go` — `T(key, locale string) string` |
| `locale.py` — `effective_user_locale()`               | `core/locale.go`                                |
| `timezone.py` — `effective_user_timezone()`           | `core/timezone.go`                              |
| `logging.py` — `configure_logging()`                  | `core/logging.go` — `slog`-based setup          |


### Ports (interfaces)

Each Python file in `protocols/` maps 1:1 to a Go interface file in `ports/`.


| Python (`protocols/`)                                     | Go (`ports/`)                               |
| --------------------------------------------------------- | ------------------------------------------- |
| `llm.py` → `LLMPort`                                      | `ports/llm.go` → `LLM interface`            |
| `user_data.py` → `UserDataPort`                           | `ports/user_data.go` → `UserData interface` |
| `line.py` → `LineMessagingPort`, `LineAudioBlobStorePort` | `ports/line.go`                             |
| `speech.py` → `SpeechToTextPort`, `TextToSpeechPort`      | `ports/speech.go`                           |
| `drugs.py` → `DrugDataPort`                               | `ports/drugs.go`                            |
| `conversation.py` → `ConversationStorePort`               | `ports/conversation.go`                     |
| `drug_caches.py` → `DrugCachesPort`                       | `ports/drug_caches.go`                      |


### Dependency injection container


| Python                                          | Go                                                                    |
| ----------------------------------------------- | --------------------------------------------------------------------- |
| `services.py` → `AppServices` dataclass         | `app/services.go` → `Services` struct                                 |
| `container.py` → `build_app_services(settings)` | `app/container.go` → `Build(cfg *config.Settings) (*Services, error)` |


### Channels (inbound adapters)


| Python (`channels/`)   | Go (`handler/`)                                         |
| ---------------------- | ------------------------------------------------------- |
| `line/routes.py`       | `handler/line/webhook.go`                               |
| `line/orchestrator.py` | `handler/line/orchestrator.go`                          |
| `line/signature.py`    | `handler/line/signature.go`                             |
| `api/routes.py`        | `handler/api/routes.go`                                 |
| `api/auth.py`          | `handler/api/auth.go`                                   |
| `api/schemas.py`       | `handler/api/schemas.go` (or Fiber bind structs inline) |
| `internal/routes.py`   | `handler/internal/routes.go`                            |


### Application layer

The Python package mixes top-level modules with subpackages (`pending/`, `health_events/`, `profile/`); the Go target mirrors that layout under `application/`.

| Python (`application/`)                              | Go (`application/`)                              |
| ---------------------------------------------------- | ------------------------------------------------ |
| `assistant_turn.py`                                  | `application/assistant_turn.go`                  |
| `patient_llm_context.py`                             | `application/patient_llm_context.go`             |
| `drug_grounding.py`                                  | `application/drug_grounding.go`                  |
| `drug_grounding_query.py`                            | `application/drug_grounding_query.go`            |
| `vital_log_build.py`                                 | `application/vital_log_build.go`                 |
| `pending/locale_intents.py`                          | `application/pending/locale_intents.go`          |
| `pending/medication_add_confirm_resolve.py`          | `application/pending/medication_add_confirm.go`  |
| `pending/dose_clarification_resolve.py`              | `application/pending/dose_clarification.go`      |
| `pending/reminder_horizon_resolve.py`                | `application/pending/reminder_horizon.go`        |
| `health_events/health_issue_event_log.py`            | `application/health_events/log.go`               |
| `health_events/health_issue_events_format.py`        | `application/health_events/format.go`            |
| `profile/profile_intents.py`                         | `application/profile/profile_intents.go`         |
| `profile/emergency_contact_resolve.py`               | `application/profile/emergency_contact.go`       |
| `profile/emergency_contacts.py`                      | `application/profile/emergency_contacts.go`      |
| `profile/profile_completion_nudge.py`                | `application/profile/completion_nudge.go`        |
| `post_add_medication_reply.py`                       | `application/post_add_medication_reply.go`       |


### Domain / agents


| Python                                       | Go                                                      |
| -------------------------------------------- | ------------------------------------------------------- |
| `agents/medication_agent.py`                 | `agent/medication_agent.go`                             |
| `agents/orchestrator.py`                     | `agent/orchestrator.go` — `RunToolAgentLoop`            |
| `agents/base.py` — `AgentTool`, `ToolResult` | `agent/tool.go` — `Tool interface`, `ToolResult struct` |
| `agents/tools/*.py`                          | `agent/tools/*.go`                                      |


### Integrations — LLM


| Python (`integrations/llm/`) | Go (`adapter/llm/`)     |
| ---------------------------- | ----------------------- |
| `_common.py`                 | `adapter/llm/common.go` |
| `gemini_llm.py`              | `adapter/llm/gemini.go` |
| `openai_llm.py`              | `adapter/llm/openai.go` |


### Integrations — Persistence


| Python (`integrations/persistence/`) | Go (`adapter/persistence/`)            |
| ------------------------------------ | -------------------------------------- |
| `supabase_client.py`                 | `adapter/persistence/client.go`        |
| `supabase_profile.py`                | `adapter/persistence/profile.go`       |
| `supabase_medications.py`            | `adapter/persistence/medications.go`   |
| `supabase_dose_events.py`            | `adapter/persistence/dose_events.go`   |
| `supabase_conversations.py`          | `adapter/persistence/conversations.go` |
| `supabase_drug_caches.py`            | `adapter/persistence/drug_caches.go`   |


### Integrations — Mocks


| Python (`integrations/mocks/`) | Go (`adapter/mocks/`)          |
| ------------------------------ | ------------------------------ |
| `users.py`                     | `adapter/mocks/users.go`       |
| `profile.py`                   | `adapter/mocks/profile.go`     |
| `medications.py`               | `adapter/mocks/medications.go` |
| `dose_events.py`               | `adapter/mocks/dose_events.go` |
| `llm.py`                       | `adapter/mocks/llm.go`         |
| `line.py`                      | `adapter/mocks/line.go`        |
| `stt.py` / `tts.py`            | `adapter/mocks/speech.go`      |


### Reminders


| Python (`reminders/`) | Go (`reminder/`)                        |
| --------------------- | --------------------------------------- |
| `deliver.py`          | `reminder/deliver.go`                   |
| `enqueue.py`          | `reminder/enqueue.go`                   |
| `dose_schedule.py`    | `reminder/schedule.go`                  |
| `upcoming_display.py` | `reminder/display.go`                   |
| `prefs.py`            | `reminder/prefs.go`                     |
| `lifecycle.py`        | `reminder/lifecycle.go`                 |
| `worker.py` (arq)     | `reminder/worker.go` (asynq or similar) |


### LLM schemas and prompts


| Python                                | Go                                        |
| ------------------------------------- | ----------------------------------------- |
| `llm/schemas.py`                      | `llm/schemas.go` — structs with JSON tags |
| `llm/prompts/persona.py`              | `llm/prompts/persona.go`                  |
| `llm/intent_classification_prompt.py` | `llm/prompts/intent.go`                   |
| `llm/intent_map.py`                   | `llm/intent_map.go`                       |
| `llm/medication_draft_build.py`       | `llm/medication_draft.go`                 |
| `llm/turn_interpretation.py`          | `llm/turn_interpretation.go`              |


### Other


| Python                          | Go                       |
| ------------------------------- | ------------------------ |
| `models/domain.py`              | `model/domain.go`        |
| `privacy/redact.py`             | `privacy/redact.go`      |
| `extensibility/intent_hooks.py` | `extensibility/hooks.go` |


---

## Key translation notes

1. **`async def` → goroutines**: Python async methods on ports map to synchronous Go interface methods; callers use `context.Context` for cancellation. Worker concurrency is managed by the Go HTTP server and asynq worker pool, not `asyncio`.
2. **`Protocol` → `interface`**: Python Protocols have no inheritance; Go interfaces are satisfied implicitly. No `@runtime_checkable` — Go type assertions replace `isinstance`.
3. `**@dataclass(frozen=True)**`: Use Go structs with value receivers. Settings, domain models, and ToolResult are value types.
4. `**lru_cache**`: `sync.Once` for `get_settings()`-style singletons; `sync.Map` or per-key mutexes for drug caches.
5. **`Enum`**: `type T string` + `const` block. Validation in `Load()` mirrors `ConfigError` raises in Python.
6. **Pydantic models** (LLM schemas, API request/response): Go structs with `json:"..."` tags. Validation with `go-playground/validator` or custom checks.
7. **Mixin pattern** (`SupabaseProfileMixin` etc.): Go uses struct embedding. `SupabaseUserData` embeds the four sub-structs.
8. **`t(key, locale)`**: Load locale JSON files at startup into `map[string]map[string]string`; `T(key, locale)` does a two-level lookup with zh-TW fallback.
