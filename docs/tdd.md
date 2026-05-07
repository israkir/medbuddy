# MedBuddy — Technical Design Document

**Extended specification:** [tdd-extended.md](https://github.com/israkir/medbuddy/tree/main/docs/tdd-extended.md) — API tables, schema, config, and extension details.

This summary is the **architectural story**: **what** we built, **why** it is shaped this way, and **how** major flows connect. Favor **diagrams** over enumeration; the extended TDD is the drill-down.

---

## 1. System context

**Stage framing:**
- **Prototype (current):** Python + FastAPI validates product logic and pilot behavior quickly.
- **MVP/Growth target:** Go + Fiber runtime on the same ports/adapters boundary, so agent/tool/domain behavior stays unchanged while server/runtime adapters are swapped.

**Idea:** One **assistant core** serves **LINE** (primary UX) and an **HTTP API** (integrations, tests, reference app). **Voice** is “audio → text, then the same pipeline as typing” where enabled.

**Why:** Duplicate logic per channel would diverge; one pipeline keeps behavior and safety rules consistent.

```mermaid
flowchart TB
  subgraph clients["Clients"]
    LINE["LINE users"]
    HTTP["HTTP clients"]
  end

  subgraph backend["Backend service"]
    API["HTTP API + LINE webhook"]
    CORE["Assistant core"]
    API --> CORE
  end

  subgraph data["Persistence"]
    DB[("User data & chat history")]
  end

  subgraph asyncQ["Async work"]
    Q["Job queue"]
  end

  subgraph external["External services"]
    LLM["LLM provider"]
    DRUG["Drug reference API"]
    STT["Speech-to-text"]
    LINEpush["LINE push API"]
  end

  LINE --> API
  HTTP --> API
  CORE --> DB
  CORE --> LLM
  CORE --> DRUG
  API --> STT
  Q --> LINEpush
  CORE --> Q
```

---

## 2. Ports & Adapters

**Idea:** **Domain and use-case code** talk only to **interfaces** (ports). **Adapters** implement those interfaces for real vendors, mocks, or channels.

**Why:**

- **Tests** swap mocks without changing business rules.
- **Vendors** (LLM, DB, messaging) change behind one seam.
- **New inbound channel** = new adapter calling the same use-case entry point.

```mermaid
flowchart LR
  subgraph driving["Inbound adapters"]
    CH1["LINE channel"]
    CH2["HTTP channel"]
  end

  subgraph core["Core"]
    UC["Use cases"]
    AG["Agent + tools"]
    UC --> AG
  end

  subgraph ports["Ports (interfaces)"]
    P["Abstract capabilities"]
  end

  subgraph driven["Outbound adapters"]
    A1["LLM"]
    A2["User store"]
    A3["Drug data"]
    A4["LINE outbound"]
    AM["Mocks / fakes"]
  end

  CH1 --> UC
  CH2 --> UC
  AG --> P
  P --> A1
  P --> A2
  P --> A3
  P --> A4
  P -.-> AM
```

---

## 3. One conversation pipeline

**Idea:** Whether the user typed on LINE, spoke (after transcription), or called the HTTP API, the same **turn runner** loads context, applies **fast routing** (`interpret_user_turn`), then **`run_tool_agent_loop`** so the model can call **registered tools** (possibly several per turn), persists turns, and returns **`AgentTurnResult`** (reply + optional metadata).

**Why:** Predictable ordering of safety checks, pending confirmations, and persistence; no “special HTTP path” that bypasses redaction or emergency handling.

```mermaid
sequenceDiagram
  autonumber
  participant U as User
  participant CH as Channel Adapter
  participant PL as Turn Pipeline
  participant CL as Intent hint (routing)
  participant AG as Tool orchestrator + tools
  participant ST as Conversation Store

  U->>CH: Send text or voice transcript
  CH->>PL: Submit normalized message
  PL->>PL: Build model-safe context (redact/narrow)
  PL->>CL: Routing hint (intent label)
  CL-->>PL: TurnInterpretation

  alt Pending state exists (confirm add / clarify dose)
    PL->>AG: Resolve from pending state
    AG-->>PL: Resolution result
  else No pending state
    alt Emergency or boundary intent
      PL->>PL: Use fixed safe response pattern
    else Standard request
      PL->>AG: complete_chat_with_tools loop (tool calls + replies)
      AG-->>PL: Final reply (+ optional metadata)
    end
  end

  PL->>ST: Persist user + assistant turns
  PL-->>CH: Assistant reply
  CH-->>U: Return reply
```

---

## 4. Registered tools instead of a free-form agent loop

**Idea:** The LLM chooses **named tools** from a fixed registry (`complete_chat_with_tools`) — list meds, add, bulk remove, explain drug, confirm dose, summary, … — possibly **multiple calls** before the final natural-language reply. Tools return structured results; many paths use deterministic i18n or **`compose_reply`** inside the tool.

**Why:**

- **Safety and audit:** Each operation has a clear boundary in code.
- **Testing:** Tools are unit-testable without full chat simulation.
- **Flexibility vs chaos:** Multi-step **tool** loops are bounded by the registry and server-side execution — not arbitrary web/search ReAct.

```mermaid
flowchart LR
  RT["Routing hint + user text"] --> OR["Orchestrator loop"]
  OR --> M["Medication CRUD / bulk"]
  OR --> DR["Drug explain / interactions"]
  OR --> AD["Adherence (confirm / miss)"]
  OR --> HS["Health summary / vitals / journal"]
  OR --> PR["Profile patch / notify (simulated)"]
  M & DR & AD & HS & PR --> RES["Tool result(s)"]
  RES --> OR
  OR --> CMP["Final assistant reply"]
```

---

## 5. Reminders: schedule materialization + async delivery

**Idea:** Schedule changes **rewrite future dose rows** in storage, **enqueue** send jobs at local times, **push** via LINE, and use **idempotency** + a **reconcile** path so missed worker ticks do not silently drop reminders.

**Why:** Chat turns stay fast; delivery and retries live in the background. Timezone correctness and “only one real push per due dose” matter for trust.

```mermaid
flowchart TD
  MED["Medication saved or removed"] --> SYNC["Rebuild upcoming dose rows"]
  SYNC --> ENQ["Enqueue jobs at scheduled times"]
  ENQ --> W["Worker at due time"]
  W --> PUSH["Push reminder"]
  PUSH --> MARK["Mark sent / skip if already handled"]
  CRON["Periodic reconcile"] -.-> ENQ
```

---

## 6. Drug grounding vs. generative language

**Idea:** **Reference data** (labels, registry lookups) **grounds** factual answers where possible; the **LLM** handles **language**, intent, and glue. **Caching** reduces duplicate lookups and cost.

**Why:** Reduces “confident hallucination” on dosing facts; separates **what we can cite** from **how we say it**.

```mermaid
flowchart LR
  Q["User question"] --> CHK{"Need registry facts?"}
  CHK -->|yes| LOOKUP["Fetch / cache label data"]
  CHK -->|no| TXT["Conversation-only answer"]
  LOOKUP --> GEN["Model: explain in user language"]
  TXT --> GEN
  GEN --> A["Answer + disclaimers"]
```

---

## 7. Privacy and security at the boundary

**Idea:** **Storage** may keep full messages for product continuity; **model-facing** context is **reduced and redacted** on most paths, with **documented exceptions** (e.g. summaries or profile extraction) where richer text is required.

**Why:** Third-party LLMs and logs remain a **trust boundary**; the architecture makes that boundary **explicit** rather than “everything raw goes to the model.”

```mermaid
flowchart TD
  RAW["Raw user text"] --> STORE["Persist for continuity"]
  RAW --> MASK["Redact / de-identify for model"]
  MASK --> LLM["LLM call"]
  STORE -.->|"exceptions per policy"| LLM
```

Operational complements (tokens, webhook signatures, cron secrets) are **standard edge hygiene** — detail in the extended TDD.

---

## 8. Run modes and deployment shape

**Idea:** **Mock integrations** run core logic in CI and local dev **without** vendor keys. **Production** uses real adapters driven by configuration. **Worker process** optional when a queue is configured (reminders); API can still run for chat.

**Why:** Fast feedback for engineers; safe path from prototype to staged pilot without forking the codebase.

### 8.1 Runtime migration boundary

The server-runtime migration is intentionally scoped: framework and I/O adapters can change (FastAPI prototype to Go/Fiber for MVP/Growth) while the assistant core, tool orchestration model, privacy boundary, and domain contracts remain stable.

```mermaid
flowchart LR
  DEV["Dev / CI — mocks"] --> SAME["Same core code"]
  STG["Staging / pilot — real adapters"] --> SAME
  SAME --> APIPROC["API process"]
  SAME --> WORKER["Worker process optional"]
```

---

## Further reading

[tdd-extended.md](https://github.com/israkir/medbuddy/tree/main/docs/tdd-extended.md) · [reminders.md](https://github.com/israkir/medbuddy/tree/main/docs/reminders.md) · [privacy.md](https://github.com/israkir/medbuddy/tree/main/docs/privacy.md) · [llm-context.md](https://github.com/israkir/medbuddy/tree/main/docs/llm-context.md) · [use-cases.md](https://github.com/israkir/medbuddy/tree/main/docs/use-cases.md)
