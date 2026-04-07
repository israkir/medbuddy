# MedBuddy — Documentation index

Navigation guide for the `docs/` folder. For project overview and quick start, see [`README.md`](../README.md).

---

## Document index

| Document | Audience | What you'll find |
|----------|----------|-----------------|
| [`tdd.md`](tdd.md) | Engineers, security reviewers | System design, component map, data model, API reference, LLM integration, caching, privacy, deployment, configuration (15 sections) |
| [`prd.md`](prd.md) | Product managers, engineers | Vision, goals, user personas, prototype scope, functional/non-functional requirements |
| [`features.md`](features.md) | Product managers, engineers | Feature catalog — LINE channel, HTTP API, agent intents, reminders, caching; spec-style with capabilities, implementation, and limitations |
| [`use-cases.md`](use-cases.md) | Engineers, product managers | Narrated scenarios — entry points, every implemented intent, example utterances, step-by-step assistant pipeline |
| [`reminders.md`](reminders.md) | Engineers, operators | LINE dose reminders — data model, arq/Redis job queue, Compose setup, Render deploy, reconcile cron |
| [`privacy.md`](privacy.md) | Engineers, compliance, operators | PII goals, redaction coverage, what goes to the LLM and what doesn't, compliance notes |
| [`llm-context.md`](llm-context.md) | Developers, compliance reviewers | Per-call LLM input reference — every `LLMPort` method with the data sent, redaction applied, and privacy exceptions |
| [`frontend-expo.md`](frontend-expo.md) | Mobile engineers, product | Reference Expo app — **future product** kept separate from the primary LINE + backend documentation |

---

## Reading paths

### New backend engineer
1. [`../README.md`](../README.md) — project overview and quick start
2. [`tdd.md`](tdd.md) — system design and component map
3. [`../apps/backend/README.md`](../apps/backend/README.md) — package layout, env vars, mock vs real
4. [`features.md`](features.md) — what the product does
5. [`use-cases.md`](use-cases.md) — how flows actually run

### Product manager
1. [`../README.md`](../README.md) — project overview
2. [`prd.md`](prd.md) — vision, goals, personas, prototype scope
3. [`features.md`](features.md) — capability catalog
4. [`use-cases.md`](use-cases.md) — user journeys with example utterances

### Security / compliance reviewer
1. [`privacy.md`](privacy.md) — PII boundaries, redaction, compliance notes
2. [`llm-context.md`](llm-context.md) — per-call LLM input map with exceptions
3. [`tdd.md`](tdd.md) §10 (Privacy and security) and §13 (Configuration)

### Operator deploying MedBuddy
1. [`../apps/backend/README.md`](../apps/backend/README.md) — env vars, deploy, mock vs real
2. [`reminders.md`](reminders.md) — Redis/arq setup for dose reminders
3. [`../TODO.md`](../TODO.md) — production readiness checklist
4. [`tdd.md`](tdd.md) §12 (Deployment topology) and §13 (Configuration)

### Mobile engineer (Expo app)
1. [`frontend-expo.md`](frontend-expo.md) — product positioning, screens, API integration, limitations
2. [`../apps/frontend/README.md`](../apps/frontend/README.md) — install, scripts, mock vs API, native builds

---

## Quick lookup

| Question | Go to |
|----------|-------|
| What data does each LLM call send? | [`llm-context.md`](llm-context.md) |
| What is the Intent enum / tool list? | [`features.md`](features.md) §2 Agent layer |
| How is a LINE voice message handled? | [`use-cases.md`](use-cases.md) §1.1 |
| How are dose events scheduled? | [`reminders.md`](reminders.md) |
| What env vars do I need? | [`../apps/backend/README.md`](../apps/backend/README.md) — Key environment variables |
| What is the Supabase schema? | [`tdd.md`](tdd.md) §6 Data model |
| Is the Expo app the primary product? | No — see [`frontend-expo.md`](frontend-expo.md) |
| What does PII redaction cover? | [`privacy.md`](privacy.md) — Redaction behavior |
| What's left before production? | [`../TODO.md`](../TODO.md) |
| How do I add a new LLM adapter? | [`tdd.md`](tdd.md) §14 Extension points |
| How do I add a new intent / tool? | [`tdd.md`](tdd.md) §14, [`../apps/backend/README.md`](../apps/backend/README.md) |
