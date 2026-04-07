<p align="center">
  <a href="https://github.com/israkir/medbuddy">
    <img src="assets/medbuddy-logo.png" alt="MedBuddy logo featuring a cute pill mascot wearing a headset" height="60">
  </a>
</p>

<h1 align="center">MedBuddy</h1>

<h3 align="center">Patient-facing medication companion — LINE messaging, voice, dose reminders, and HTTP API</h3>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="https://github.com/psf/black"><img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/lint-ruff-d261ff.svg" alt="Lint: Ruff"></a>
  <a href="https://github.com/israkir/medbuddy/actions/workflows/ci.yml"><img src="https://github.com/israkir/medbuddy/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
</p>

---

**MedBuddy** is a medication companion monorepo: a **FastAPI** backend (LINE + HTTP API) and an optional **Expo** app for future mobile work.

> **Disclaimer:** This is a software prototype. It is **not** a substitute for professional medical advice, diagnosis, or treatment.

## Prerequisites

- [GNU Make](https://www.gnu.org/software/make/) — `make` / `make help` at the repo root
- **Backend:** Python **3.11+**
- **Frontend (optional):** Node.js 18+ and npm

---

## Quick start

**Backend** (mock mode — no API keys):

```bash
make be-install
make be-dev-mock
make be-test
```

**Frontend** (Expo):

```bash
make fe-install
make fe-dev
```

**Docker** (mock API): `make be-compose` → http://localhost:8000

For real LINE, LLM, Supabase, and other services, use [`apps/backend/.env.example`](apps/backend/.env.example) and **[`apps/backend/README.md`](apps/backend/README.md#mock-vs-real-integrations)**.

---

## Where to read next

Start with **[`docs/index.md`](docs/index.md)** — it lists every major doc, **reading paths by role** (backend, product, security, ops, mobile), and a **quick lookup** (API, env vars, reminders, privacy, and more).

| If you want… | Open |
|--------------|------|
| System design, API reference, deployment | [`docs/tdd.md`](docs/tdd.md) |
| Backend env, package layout, deploy | [`apps/backend/README.md`](apps/backend/README.md) |
| Expo app (reference / future client) | [`docs/frontend-expo.md`](docs/frontend-expo.md) → [`apps/frontend/README.md`](apps/frontend/README.md) |
| Production checklist | [`TODO.md`](TODO.md) |
| Change history | [`CHANGELOG.md`](CHANGELOG.md) |

---

### LINE messaging

Today’s patient-facing experience is built around **LINE**: chat with the medication helper, voice notes, and dose reminders delivered on the channel. The image below is a view of that flow.

<p align="center">
  <img src="assets/line.jpg" alt="Illustration: MedBuddy medication helper chat in LINE" width="320">
</p>

### Standalone mobile app (concept)

The repo today centers on LINE and the HTTP API; a **dedicated mobile client** is a product direction, not a shipped guarantee. The screens below are **concept-only** mockups to illustrate that idea—not screenshots of a production app.

<p align="center">
  <img src="assets/mobile-1.png" alt="Concept: standalone app home or main screen" width="260">
  &nbsp;
  <img src="assets/mobile-2.png" alt="Concept: standalone app secondary flow" width="260">
  &nbsp;
  <img src="assets/mobile-3.png" alt="Concept: standalone app detail or settings" width="260">
</p>

---

## Contributing

1. **`make pre-commit-install`** after backend setup
2. **`make be-check`** (backend) or **`make fe-check`** (frontend)
3. Document behavior changes in [`CHANGELOG.md`](CHANGELOG.md) and keep secrets in `.env` (see each app’s `.env.example`)

Pull requests are welcome.
