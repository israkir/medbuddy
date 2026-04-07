# MedBuddy — Product Requirements

**Extended Version:** [prd-extended.md](prd-extended.md)

## What MedBuddy is

MedBuddy helps patients and caregivers manage medications inside LINE, the chat app people in Taiwan already use every day. They can build a med list, ask questions in everyday language, get dose reminders, and confirm doses—without installing another app.

A web API exposes the same assistant for partners, tests, and future clients.

## The problem

- Chronic-care elderly patients juggle many daily meds — yet real-world adherence sits around 50%, and missed doses drive avoidable hospitalizations and worse outcomes.
- Most tools optimize for pings, not understanding — the gap is often a comprehension problem (what to take, why, and how to talk about it), not just another reminder channel.
- Clinical communication is squeezed — visit time is short; patients and families rarely have a clear, current picture of medications and vitals to share with a doctor.

## Who it’s for

- **Primary:** Adults and caregivers on 2–6 chronic meds, LINE-first, Traditional Chinese preferred.
- **Secondary:** Teams integrating via the HTTP API.
- **Out of scope:** Emergency diagnosis, prescribing, dose changes, or replacing a clinician. Those cases get safety routing, not assistant medical judgment.

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

Health and chat data are sensitive. We limit what goes to third‑party LLMs: a de‑identified patient context and redacted user text on most assistant calls (pattern-based masking—not full clinical de-ID). Stored messages may stay verbatim for the product while the model sees narrower slices; a few flows (e.g. profile extraction, health summaries) can send more raw text —see [llm-context.md](llm-context.md). Operators still need safe logging and provider agreements.

## Core journeys

- **Onboard** — Preferred name, language, timezone, disclaimer; on LINE, a fixed welcome (then people can send a one-line intro: contact, allergies, conditions—same as “profile in chat” below, or use the HTTP onboarding form for app clients).
- **Profile in chat** — Update how you’re called, demographics, emergency contact, health notes, language, or timezone with ordinary sentences (without redoing full onboarding).
- **Build the list** — Add a med in natural language; yes/no or corrections when the assistant needs confirmation; sometimes answer how many days ahead to schedule reminders after a save.
- **Adjust the list** — Edit dose, schedule, or notes, or remove a med; reminders resync when the backend is configured for them.
- **See what’s on** — Inventory of saved meds vs what’s due next (clock-based upcoming doses from reminders—different from the static list).
- **Ask & log** — What a drug is for, interaction questions, side effects you’re having now, vitals, and other medication-related Q&A—plain language; type or speak on LINE/API where enabled.
- **Dose day** — Reminder arrives; reply to confirm, add a short note, or pick which dose if several could match; say you missed a dose when that’s true.
- **Visit prep** — Ask in chat for a recap or use the summary API for a structured, doctor-oriented export (same underlying idea as chat “summary for my doctor”).
- **Safety & boundaries** — Emergency-type messages get a fixed safety reply, not improvisational medical advice; clearly off-topic chat gets a consistent polite redirect.

## Prototype Scope

**In the live prototype:** LINE text and voice, dose reminders, and an API for text and voice uploads.

**What we’re not using to pass or fail this pilot:** formal targets for transcription quality, synthetic voice quality, or cost per voice message—those wait until we deliberately define them.

## Success Metrics

| Area | What good looks like | Notes |
|------|----------------------|--------|
| **Data** | No med-list data loss; critical paths covered by tests | CI green on main; zero incidents in the cohort. |
| **Answers** | Human review: no diagnosing/prescribing; most explain/interaction answers tied to the reference data set | Method and sample agreed before the pilot. |
| **Reminders** | High delivery in staging; at least one real add → remind → confirm | Staging window and denominator agreed with ops. |
| **Languages** | Native review of both languages + language switch works. | |
| **Privacy** | Sample audit: model inputs match our privacy rules | e.g. 20 turns; details in [privacy.md](privacy.md). |

## Risks we’re watching

| Risk | What we do about it |
|------|---------------------|
| AI sounds diagnostic or unsafe | Strict assistant persona; emergencies use fixed copy; review before pilot. |
| Drug database has no match | Honest answer anyway; we track gaps. |
| Reminders don’t fire | Recovery process to catch missed sends; idempotent “already sent” handling. |
| Personal data leaks into the model | Redaction and context rules before every AI call. |
| LINE feels slow or flaky | Acknowledge fast; send the reply when ready. |
| People think we’re a certified medical device | Disclaimers everywhere; trial policy; no “medical device” marketing. |

Residual privacy limits are spelled out in [privacy.md](privacy.md).

## Roadmap

| Phase | Rough timing | Intent |
|-------|----------------|--------|
| **Prototype** | ~2 days | Prove the riskiest slice; go / no-go on funding MVP work. |
| **MVP** | ~3 months | Small controlled pilot on real infra: list, chat (text + voice), reminders, governance, success table above. |
| **Growth** | ~3–12 months | Harder voice standards, retention, security for API users, cost/latency discipline, regional data. |
| **Global** | 1+ year | Only after law/clinical input: regions, residency, hospital-friendly exports. |

## Decisions still open

- Taiwan regulatory posture (wellness vs. regulated software).
- Long-term identities for API users (beyond a shared pilot token).
- When voice gets formal targets (accuracy, fallbacks, cost)—and updates to success criteria.
- Clinician-facing export formats for partners.
- Data residency if we leave Taiwan.

## Further reading

[prd-extended.md](prd-extended.md) · [features.md](features.md) · [use-cases.md](use-cases.md) · [tdd.md](tdd.md) · [reminders.md](reminders.md) · [privacy.md](privacy.md) · [llm-context.md](llm-context.md) · [frontend-expo.md](frontend-expo.md)
