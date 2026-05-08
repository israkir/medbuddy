# MedBuddy — Documentation index

Navigation guide for the `docs/` folder. For project overview and quick start, see [`README.md`](../README.md).

---

## Document index

| Document | Audience | What you'll find |
|----------|----------|-----------------|
| [`tdd.md`](tdd.md) | Engineers, security reviewers | **Primary TDD** (~2–3 pages): architecture concepts and diagrams; extended doc for API/schema |
| [`tdd-extended.md`](tdd-extended.md) | Engineers, operators | **Full TDD** (18 sections): request flows, full API reference, schema, config, extension points |
| [`prd.md`](prd.md) | Product managers, executives | **Primary PRD** (~2–3 pages): vision, goals, scope, how we measure success |
| [`prd-extended.md`](prd-extended.md) | Product, legal, engineering leads | **Full PRD**: numbered sections, complete requirement tables, risks, assumptions, roadmap |
| [`features.md`](features.md) | Product managers, engineers | Feature catalog — LINE channel, HTTP API, agent intents, reminders, caching; spec-style with capabilities, implementation, and limitations |
| [`use-cases.md`](use-cases.md) | Engineers, product managers | Narrated scenarios — entry points, every implemented intent, example utterances, step-by-step assistant pipeline |
| [`reminders.md`](reminders.md) | Engineers, operators | LINE dose reminders — data model, arq/Redis job queue, Compose setup, Render deploy, reconcile cron |
| [`privacy.md`](privacy.md) | Engineers, compliance, operators | PII goals, redaction coverage, what goes to the LLM and what doesn't, compliance notes |
| [`llm-context.md`](llm-context.md) | Developers, compliance reviewers | Per-call LLM input reference — every `LLMPort` method with the data sent, redaction applied, and privacy exceptions |
| [`frontend-expo.md`](frontend-expo.md) | Mobile engineers, product | Reference Expo app — **future product** kept separate from the primary LINE + backend documentation |
| [`go-port-mapping.md`](go-port-mapping.md) | Engineers, platform leads | Python-to-Go/Fiber migration map — module/interface/package equivalence and translation notes |

---

## Reading paths

### New backend engineer
1. [`../README.md`](../README.md) — project overview and quick start
2. [`tdd.md`](tdd.md) — architecture overview (diagrams); then [`tdd-extended.md`](tdd-extended.md) for full API, schema, and ops detail
3. [`../apps/backend/README.md`](../apps/backend/README.md) — package layout, env vars, mock vs real
4. [`features.md`](features.md) — what the product does
5. [`use-cases.md`](use-cases.md) — how flows actually run

### Product manager
1. [`../README.md`](../README.md) — project overview
2. [`prd.md`](prd.md) — vision, goals, personas, scope (start here)
3. [`prd-extended.md`](prd-extended.md) — full requirement IDs, tables, legal-adjacent detail
4. [`features.md`](features.md) — capability catalog
5. [`use-cases.md`](use-cases.md) — user journeys with example utterances

### Security / compliance reviewer
1. [`privacy.md`](privacy.md) — PII boundaries, redaction, compliance notes
2. [`llm-context.md`](llm-context.md) — per-call LLM input map with exceptions
3. [`tdd-extended.md`](tdd-extended.md) §10 (Privacy and security) and §15 (Configuration)

### Operator deploying MedBuddy
1. [`../apps/backend/README.md`](../apps/backend/README.md) — env vars, deploy, mock vs real
2. [`reminders.md`](reminders.md) — Redis/arq setup for dose reminders
3. [`../TODO.md`](../TODO.md) — production readiness checklist
4. [`tdd-extended.md`](tdd-extended.md) §14 (Deployment topology) and §15 (Configuration)

### Mobile engineer (Expo app)
1. [`frontend-expo.md`](frontend-expo.md) — product positioning, screens, API integration, limitations
2. [`../apps/frontend/README.md`](../apps/frontend/README.md) — install, scripts, mock vs API, native builds

---

## Quick lookup

| Question | Go to |
|----------|-------|
| What data does each LLM call send? | [`llm-context.md`](llm-context.md) |
| Does the tool orchestrator see earlier chat turns? | Yes — **redacted** prior user/assistant tail (cap **`MEDBUDDY_AGENT_ORCHESTRATOR_HISTORY_TURNS`**) — [`llm-context.md`](llm-context.md) (`complete_chat_with_tools`), [`features.md`](features.md) §3 |
| Does the assistant nudge users to complete onboarding fields? | Yes — optional footer every **`MEDBUDDY_PROFILE_COMPLETION_NUDGE_EVERY_N_USER_TURNS`** user messages on the orchestrator path — [`features.md`](features.md) §3.3, [`tdd-extended.md`](tdd-extended.md) §5.1 step 11 |
| What happens on emergency intent if a contact is already saved? | Same fixed safety reply **plus** the simulated outreach line and **`metadata.simulated_emergency_notification`** — [`features.md`](features.md) §4.10, [`use-cases.md`](use-cases.md) §3.14 |
| What tools does the orchestrator expose? | [`features.md`](features.md) §2 Agent layer · [`llm/agent_tool_definitions.py`](../apps/backend/src/medbuddy/llm/agent_tool_definitions.py) |
| How is a LINE voice message handled? | [`use-cases.md`](use-cases.md) §1.1 |
| How are dose events scheduled? | [`reminders.md`](reminders.md) |
| What env vars do I need? | [`../apps/backend/README.md`](../apps/backend/README.md) — Key environment variables |
| What is the Supabase schema? | [`tdd-extended.md`](tdd-extended.md) §6 Data model |
| Is the Expo app the primary product? | No — see [`frontend-expo.md`](frontend-expo.md) |
| What does PII redaction cover? | [`privacy.md`](privacy.md) — Redaction behavior |
| What do OD-1/OD-5/T1/T2/T3 codes mean? | [`prd-extended.md` §13 Open decisions](prd-extended.md#13-open-decisions) — codes &amp; abbreviations |
| What's left before production? | [`../TODO.md`](../TODO.md) |
| How do I add a new LLM adapter? | [`tdd-extended.md`](tdd-extended.md) §16 Extension points |
| How do I add a new orchestrator tool? | [`tdd-extended.md`](tdd-extended.md) §16.4, [`llm/agent_tool_definitions.py`](../apps/backend/src/medbuddy/llm/agent_tool_definitions.py) |
| How does Python map to Go/Fiber modules? | [`go-port-mapping.md`](go-port-mapping.md) |
