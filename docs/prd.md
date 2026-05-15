# MedBuddy — Product Requirements

**Extended Version:** [prd-extended.md](https://github.com/israkir/medbuddy/blob/main/docs/prd-extended.md)

## What MedBuddy is

MedBuddy helps patients and caregivers manage medications inside LINE, the chat app people in Taiwan already use every day. They can build a med list, ask questions in everyday language, get dose reminders, and confirm doses—without installing another app.

A web API exposes the same assistant for partners, tests, and future clients.

## The problem

- Chronic-care elderly patients juggle many daily meds — yet real-world adherence sits around 50%, and missed doses drive avoidable hospitalizations and worse outcomes.
- Most tools optimize for pings, not understanding — the gap is often a comprehension problem (what to take, why, and how to talk about it), not just another reminder channel.
- Clinical communication is squeezed — visit time is short; patients and families rarely have a clear, current picture of medications and vitals to share with a doctor.

## Who it’s for

- **Primary:** Adults and caregivers on 2–6 chronic meds, LINE-first, Traditional Chinese preferred.
- **Secondary:** Doctors, health care institutions, teams integrating via the HTTP API.
- **Out of scope:** Emergency diagnosis, prescribing, dose changes, or replacing a clinician. Those cases get safety routing, not assistant medical judgment.

## Market wedge

We win where **daily chat**, **Taiwan**, and **medication comprehension** intersect:

- **Zero new app** — People already live in LINE; a separate reminder app is another thing to install, learn, and trust.
- **Understanding, not just pings** — One thread holds the list, plain-language Q&A (including interactions and side-effect questions framed safely), and adherence—most alternatives optimize alerts without a durable med picture or follow-up questions in Traditional Chinese.
- **Language fit** — Strong **Traditional Chinese** plus **English**, with clinical-grade references often still English-only elsewhere.
- **One core, two surfaces** — The same assistant on LINE and the **HTTP API** lets partners and tests reuse the product without a fork; B2B-style delivery stays credible because behavior matches the patient channel.

Privacy posture (redacted model inputs, documented context—see [privacy.md](https://github.com/israkir/medbuddy/blob/main/docs/privacy.md)) matters for trust versus a generic consumer chatbot pasted onto health data.

## Go-to-market

- **Primary beachhead:** Taiwan; **LINE** as the main acquisition and retention channel (official account / bot). The **API** supports integrations, QA, and future **B2B2C** paths but is not the first consumer distribution lever.
- **Who we recruit first:** The same **primary user** as above—adults and caregivers on a small chronic-med set, comfortable in Traditional Chinese—via a **small, controlled pilot** (specific recruitment channels and partners remain open; see [prd-extended.md](https://github.com/israkir/medbuddy/blob/main/docs/prd-extended.md) open decisions).
- **Positioning:** Medication companion and adherence support with clear **disclaimers**—not a certified device, not diagnosis or prescribing. Marketing and trial language stay inside that boundary.
- **What unlocks Growth:** Pilot passes the success table, **OD-1**-class regulatory clarity for Taiwan, and appetite to harden voice (**OD-3**) and API identity before broader reach.

## Goals

| Goal | How we’ll judge the pilot |
|------|---------------------------|
| **G1** Reliable medication list | Add, change, and remove meds work end-to-end; no lost data for participants. |
| **G2** Understandable answers | Plain-language, non-diagnostic replies, grounded in a drug reference where we can. |
| **G3** Adherence on LINE | Reminders arrive on time; people can confirm or say they missed a dose in chat (typed or voice on LINE). |
| **G4** Bilingual | Strong Traditional Chinese and English, including switching language mid-chat. |
| **G5** Privacy-conscious AI | Sensitive personal details are not sent raw into the AI; sampling proves it. |
| **Emergencies** | Life‑threatening signals get a fixed safety message and escalation to professionals—not creative AI triage. |
| **Voice** | Supported in deployment; not held to formal accuracy or cost targets in this pilot round. |

## Privacy & data

Health and chat data are sensitive. We limit what goes to third‑party LLMs: a **narrowed, mostly de-identified** patient context (age band — not exact age — no raw notes), **redacted** user text on most assistant calls, and a **capped redacted tail** of recent user/assistant lines for the tool orchestrator so short follow-ups stay coherent. Redaction today is pattern-based (emails, phone numbers, long digit runs); full NER-based clinical de-identification is a Growth-phase investment — see [`privacy.md`](privacy.md). Stored messages may stay verbatim for the product while the model sees narrower slices; a few flows (e.g. profile extraction, health summaries) can send more raw text — see [llm-context.md](https://github.com/israkir/medbuddy/blob/main/docs/llm-context.md). Operators still need safe logging and provider agreements.

## Core journeys

- **Onboard** — Preferred name, language, timezone, disclaimer; on LINE, a fixed welcome in the user’s language when LINE’s profile **`language`** maps to a supported app locale (`en` / `zh-TW`), otherwise default Traditional Chinese (then people can send a one-line intro: contact, allergies, conditions—same as “profile in chat” below, or use the HTTP onboarding form for app clients). The reference app sends device locale on **`GET /v1/app/me`** until onboarding is saved.
- **Profile in chat** — Update how you’re called, demographics, emergency contact, allergies/conditions, language, or timezone with ordinary sentences (without redoing full onboarding).
- **Build the list** — Add a med in natural language; yes/no or corrections when the assistant needs confirmation; sometimes answer how many days ahead to schedule reminders after a save (chronic / lifelong meds — *"long-term"*, *"終身"*, *"慢性病用藥"* — are recognised automatically and skip that follow-up: the rolling reminder window is kept full forever by a daily background refill plus a delivery-time safety net). When someone already has other meds on file, the assistant reply can include an extra **cross-check** for possible interactions (reference-grounded, disclaimer-heavy — not a substitute for a clinician or pharmacist).
- **Adjust the list** — Edit dose, schedule, or notes, or remove a med; reminders resync when the backend is configured for them.
- **See what’s on** — Inventory of saved meds vs what’s due next (clock-based upcoming doses from reminders—different from the static list).
- **Ask & log** — What a drug is for, interaction questions, side effects you’re having now, vitals, and other medication-related Q&A—plain language; type or speak on LINE/API where enabled.
- **Dose day** — Reminder arrives; reply to confirm, add a short note, or pick which dose if several could match; say you missed a dose when that’s true.
- **Visit prep** — Ask in chat for a recap or use the summary API for a structured, doctor-oriented export (same underlying idea as chat “summary for my doctor”).
- **Safety & boundaries** — Emergency-type messages get a fixed safety reply, not improvisational medical advice; clearly off-topic chat gets a consistent polite redirect.

## Prototype Scope

**In the live prototype:** LINE text and voice (Google STT/TTS), dose reminders, and an HTTP API for text and voice uploads. Voice is live for users who opt in and shares the same understanding pipeline as typed chat.

**Voice metrics are not pilot pass/fail targets:** formal voice metrics (WER, TTS quality, cost/turn) are not in the success table for this pilot — see NG-1 / OD-3 in [`prd-extended.md`](prd-extended.md).

## Success Metrics

| Area | What good looks like | Notes |
|------|----------------------|--------|
| **Data** | No med-list data loss; critical paths covered by tests | CI green on main; zero incidents in the cohort. |
| **Answers** | Human review: no diagnosing/prescribing; most explain/interaction answers tied to the reference data set | Method and sample agreed before the pilot. |
| **Reminders** | High delivery in staging; at least one real add → remind → confirm | Staging window and denominator agreed with ops. |
| **Languages** | Native review of both languages + language switch works. | |
| **Privacy** | Sample audit: model inputs match our privacy rules | e.g. 20 turns; details in [privacy.md](https://github.com/israkir/medbuddy/blob/main/docs/privacy.md). |

## Risks we’re watching

| Risk | What we do about it |
|------|---------------------|
| AI sounds diagnostic or unsafe | Strict assistant persona; emergencies use fixed copy; review before pilot. |
| Drug database has no match | Honest answer anyway; we track gaps. |
| Reminders don’t fire | Recovery process to catch missed sends; idempotent “already sent” handling. |
| Personal data leaks into the model | Redaction and context rules before every AI call. |
| LINE feels slow or flaky | Acknowledge fast; send the reply when ready. |
| People think we’re a certified medical device | Disclaimers everywhere; trial policy; no “medical device” marketing. |

Residual privacy limits are spelled out in [privacy.md](https://github.com/israkir/medbuddy/blob/main/docs/privacy.md).

## Roadmap

| Phase | Rough timing | Intent |
|-------|----------------|--------|
| **Prototype** | Completed (Apr 2026) | Proved the riskiest slice and unlocked MVP funding. |
| **MVP + Taiwan Pilot** | In flight (targeting ~Q3 2026 exit) | Controlled pilot on real infra: list, chat (text + voice), reminders, governance, and success table above. |
| **Growth (Japan-first)** | Post-pilot gate (after OD-1 clarity + economics proof) | Harden voice, retention, API security, and multi-market operations without forking the assistant core. |
| **Regional / Global** | Post-growth, gate-based | Expand only after legal/clinical and data-sovereignty readiness; sequencing is signal-driven, not calendar-driven. |

**Economics gate (from roadmap):** target server+LLM efficiency of **< US$0.05 / MAU / month at MVP** and **< US$0.02 at Growth** as caching and routing maturity improve.

**China boundary:** Mainland China is **not** in this expansion roadmap. It requires a separate product/JV posture (WeChat channel, approved domestic LLMs, and on-shore compliance stack), not a straight market rollout.

### Future feature directions (post-Pilot)

Once pilot exit criteria are met (≥95% reminder delivery, ≥80% grounded Q&A, 0 data-loss / 0 privacy violations), adjacent features unlock in three tiers gated by market signals — not by calendar.

**Tier 1 — Adjacent depth (same surface, same buyer, post-Pilot):** caregiver read-only circle, blister-pack photo recognition, refill horizon & shortage radar, food/herbal/TCM interaction layer, missed-dose pattern reflection, vitals trend deltas in chat. Each has a named pilot trigger signal; none auto-graduates without it.

**Tier 2 — Platform & B2B2C (first paying LOI):** clinician summary handoff (OD-4 product), pharma-sponsored patient support program overlay, hardened public API for integrators (resolves OD-2), polypharmacy / Beers-Criteria flags with pharmacist routing, wearable & home-device passive vitals ingest. Requires OD-1 and OD-2 resolved.

**Tier 3 — Frontier bets (Series A+, regulatory clarity):** NHI PharmaCloud / My Health Bank import (Taiwan structural moat), insurer / NHI value-based adherence contracts, KakaoTalk and WhatsApp channel expansion, psychiatric medication adherence specialty, voice-first elderly mode + smart-speaker bridge, de-identified RWD aggregates (ethics board required). None starts engineering before OD-1 and OD-5 are resolved.

**Consciously excluded (not a backlog, not deferred):** pharmacy referral fees or ad-supported answers; AI symptom-checker / triage; autonomous dose changes by AI; generic chronic-care coaching; open-ended ReAct agent expansion. Each exclusion is explicit in the [deck](presentation/index.html) and the companion feature-directions document.

## Decisions still open

- **OD-1** — Taiwan regulatory posture (wellness vs. regulated software). Blocks T2 B2B contracts and all T3 features.
- **OD-2** — Long-term identities for API users (beyond a shared pilot token). Blocks T2.3 API hardening.
- **OD-3** — When voice gets formal targets (accuracy, fallbacks, cost) and updates to success criteria.
- **OD-4** — Clinician-facing summary formats for institutional partners. T2.1 builds on this decision.
- **OD-5** — Data residency requirements for Taiwan regulations and future markets. Blocks T3 global expansion and NHI PharmaCloud (T3.1).

## Further reading

[prd-extended.md](https://github.com/israkir/medbuddy/blob/main/docs/prd-extended.md) · [features.md](https://github.com/israkir/medbuddy/blob/main/docs/features.md) · [use-cases.md](https://github.com/israkir/medbuddy/blob/main/docs/use-cases.md) · [tdd.md](https://github.com/israkir/medbuddy/blob/main/docs/tdd.md) · [reminders.md](https://github.com/israkir/medbuddy/blob/main/docs/reminders.md) · [privacy.md](https://github.com/israkir/medbuddy/blob/main/docs/privacy.md) · [llm-context.md](https://github.com/israkir/medbuddy/blob/main/docs/llm-context.md) · [frontend-expo.md](https://github.com/israkir/medbuddy/blob/main/docs/frontend-expo.md)
