<p align="center">
  <img src="frontend/public/icon.svg" width="84" alt="AutoApply AI logo" />
</p>

<h1 align="center">AutoApply AI</h1>

<p align="center"><b>Swipe right. We apply. Internships on autopilot.</b></p>

An autonomous job-application agent that you run yourself, built for mass-applying to internships
and startup roles. It scans thousands of openings, puts every one that passes your filters into a
**Swipe Review** deck, and for each job you keep it tailors your resume, writes a cover letter, fills
in the application form in a real browser and submits it. After you apply, it watches your Gmail for
replies, updates each application's status, puts interviews on your Google Calendar with prep notes,
and shows you what is working.

```bash
./start.sh          # one command: installs what's missing and runs everything → http://localhost:3000
```

> **Nothing is sent for a job you didn't keep, and eligibility is never guessed.** Scans never skip a
> job for a low score; you decide in Swipe Review. Keeping a job is your approval to apply. If the
> form asks something only you can answer (visa sponsorship, work authorization, background checks)
> and you haven't saved an answer, the filled form stops in **Needs approval** instead. Turn off
> **Apply automatically** to review every filled form before it's submitted.

| Landing | Swipe Review |
|---|---|
| ![Landing](docs/screenshots/landing.png) | ![Swipe Review](docs/screenshots/swipe-review.png) |
| **Overview** | **Review a filled application** |
| ![Overview](docs/screenshots/overview.png) | ![Review](docs/screenshots/review.png) |
| **Mass-apply settings** | **Analytics** |
| ![Mass apply](docs/screenshots/mass-apply.png) | ![Analytics](docs/screenshots/analytics.png) |

---

## Contents

- [One-command start](#one-command-start)
- [What it does](#what-it-does)
- [Swipe Review and mass applying](#swipe-review-and-mass-applying)
- [How it works](#how-it-works)
- [Quick start (Docker)](#quick-start-docker)
- [Try the whole loop safely with the demo careers site](#try-the-whole-loop-safely-with-the-demo-careers-site)
- [Using it for real](#using-it-for-real)
- [Configuration](#configuration)
- [Connect Gmail and Google Calendar](#connect-gmail-and-google-calendar)
- [LinkedIn and the Chrome extension](#linkedin-and-the-chrome-extension)
- [Local development without Docker](#local-development-without-docker)
- [Deployment](#deployment)
- [Testing and CI](#testing-and-ci)
- [Project structure](#project-structure)
- [Security and privacy](#security-and-privacy)
- [Responsible use](#responsible-use)
- [Troubleshooting](#troubleshooting)

---

## One-command start

```bash
git clone https://github.com/saksham-eng560/autoapply-ai.git && cd autoapply-ai
./start.sh                 # macOS / Linux / WSL — needs Python 3.11+ and Node 20+
```

The first run creates `.env` with fresh secrets, a Python virtualenv, installs Chromium and the npm
packages, and prepares a local SQLite database. Later runs start in seconds and only reinstall when
requirements change. It then runs the API (:8000), the dashboard (:3000) and the task queue, opens
your browser and streams the logs. **Ctrl-C stops everything.**

| Command | What it does |
|---|---|
| `./start.sh` | Local mode, no Docker. Uses Redis + a Celery worker + beat if `redis-server` is installed, otherwise runs tasks in-process with a built-in scheduler (scheduled scans still happen). |
| `./start.sh --demo` | Also seeds a demo account (`demo@example.com` / `demo-password-123`) with a swipe deck, and serves the demo careers site on :8765. |
| `./start.sh --prod` | Production build of the dashboard (faster pages). |
| `./start.sh --docker` | The full Docker Compose stack (PostgreSQL + pgvector, Redis, worker, beat). `./start.sh --stop` stops it. |
| `./start.sh --reset` | Wipes the local database first. |
| `start.bat` | Windows: the Docker path (`start.bat stop` to stop). Or use WSL and `./start.sh`. |

Your first ten minutes:

1. **Create your account** at http://localhost:3000/register.
2. **Upload your resume** in Resume Lab (PDF, DOCX or pasted text) and check the parsed result.
3. **Settings › Mass apply › Internships**: one click adds the internship lists and startup boards.
4. **Settings › Saved answers**: save work authorization and visa sponsorship. Without them, kept jobs
   stop in Needs approval instead of being submitted.
5. **Scan for jobs now**, then open **Swipe Review** and start swiping.

Add `ANTHROPIC_API_KEY=...` to `.env` for much better scoring, tailoring and answers (everything also
works without it on built-in heuristics). `make start` does the same as `./start.sh`.

## What it does

**Discovery.** Scans Greenhouse, Lever, Ashby and Workday boards through their public APIs, reads
company careers pages (schema.org `JobPosting` markup, and embedded ATS boards it detects), and
searches LinkedIn, Indeed, Glassdoor and Wellfound with a real browser. It removes duplicates across
sources, and scans run on a schedule (every 6 hours by default) or when you click **Scan for jobs now**.
You can also paste any job URL.

**Matching.** Each job gets a 0–100 score across five parts: skills, experience, industry, location
and compensation. The score also explains which of your skills are strong matches and which the job
wants that you don't have. Only your hard filters remove a job automatically (companies to avoid,
excluded title keywords, job types, expired deadlines and, optionally, postings that don't sponsor
visas). Everything else — even a low score — goes to **Swipe Review**, best matches first, with
heads-ups such as "not a remote role". (The original automatic mode, which skips jobs under a
threshold and prepares the rest, is still available in Settings.)

**Your resume, your way.** By default the agent sends **your original resume file, unchanged**.
Switch to *light tweaks* (every word kept, relevant items moved to the top) or *full AI tailoring*
in Settings › Mass apply. With full tailoring, your master resume is rewritten for each job: the summary, bullet order,
emphasis and wording (for example, using the job's name for a skill you really have). A guard checks
the result against your master resume and reverts anything that adds an employer, title, date,
degree, skill or number that isn't in the original. You get an ATS-friendly PDF (classic or modern
template) and a cover letter that references the actual role.

**Form filling.** Dedicated submitters for Greenhouse, Lever, Workday and LinkedIn Easy Apply, and a
generic engine that handles any other HTML form: text, selects, radios, checkboxes, file uploads and
multi-step flows. Answers come from your saved answers, your resume and deterministic rules first,
then from the AI for open-ended questions. Eligibility questions such as visa sponsorship and work
authorization are **never guessed**. If you haven't saved an answer, the question stays blank and
flagged until you answer it, and the agent remembers your answer for next time. EEO questions default
to "decline to self-identify". Browsing uses human-like typing, mouse paths and pacing, and supports
proxy rotation and CAPTCHA solving (2Captcha / Anti-Captcha). Per-platform rate limits are enforced.

**Swipe, then submission.** Keep a job and it's prepared and — with **Apply automatically** on —
submitted as soon as the form is filled, provided every eligibility question has your saved answer.
Anything else waits in **Needs approval** with the filled-form screenshot, tailored resume, cover
letter, answers and match analysis. Submission happens
in a fresh browser session that re-fills the form with what you approved. The agent checks for a
confirmation page, saves a screenshot, and records the confirmation number when there is one.
`SUBMISSION_DRY_RUN=true` disables the final click entirely.

**Inbox and calendar.** With Google connected, the agent reads job-related e-mail (Pub/Sub push or
polling every 5 minutes) and classifies each message: rejection, interview invite, assessment, offer,
information request, or acknowledgement. It links the message to the right application and updates
its status. Messages are filed under `AutoApply AI/…` Gmail labels, and reply drafts are prepared
(never sent) for invites and requests. Interviews are added to Google Calendar with a prep document
covering the company, likely questions, STAR stories drawn from your resume, and questions to ask.
Reminders go out before each interview.

**Dashboard.** Next.js dashboard with a landing page, an overview, **Swipe Review**, an applications
pipeline, a job browser, an e-mail feed, interviews, analytics (response, interview and offer rates,
time to response, platform effectiveness, keywords that get callbacks), a resume editor, agent logs,
and settings. Live updates arrive over WebSocket. It works on phones, can be installed as a PWA, and
sends browser notifications.

**Design.** An editorial "ink" theme (charcoal, warm cream type and one signal red) with a "paper"
light theme: Dela Gothic One display type, Space Grotesk for the interface, hairline grid lines,
square controls and outlined pill tags. It's built from [shadcn/ui](https://ui.shadcn.com) (Radix)
components restyled through the design tokens in `frontend/src/app/globals.css`, with framer-motion
for the swipe deck. The logo, favicon, PWA and extension icons all use the same bracket-and-red-block
mark (`frontend/public/icon.svg`).

**Notifications.** In-app, e-mail (SMTP or your own Gmail), Discord and Slack. You choose which
events go to which channel, and there's a weekly summary.

**Your data.** Export everything as JSON, or delete your account with all files and tokens (GDPR/CCPA).
OAuth tokens and cookies are encrypted with AES-256-GCM, and closed applications older than the retention period are
cleaned up automatically.

## Swipe Review and mass applying

**Swipe Review** (`/dashboard/review`) is a deck of every job that passed your filters, best matches
first. Each card shows the role, company, location, term, salary, visa sponsorship, the score
breakdown, the skills you have and the ones they want.

- **Drag right** or press **→** to keep: the agent tailors, fills and applies.
- **Drag left** or press **←** to skip.
- **Z** undoes the last swipe (until preparation has started).
- **Keep in bulk**: keep every card at or above a score in one click (with the current filters).
- Filters: search, internship / full-time, remote only. A counter shows how many are left.

**Presets** (Settings › Mass apply) set everything up in one click and keep your own lists:

| Preset | What it adds |
|---|---|
| **Internships** | Intern versions of your target roles, internship-only job types, the SimplifyJobs and vanshb03 internship lists (4,000+ live postings, refreshed daily), ~110 startup Greenhouse / Ashby / Lever boards, 100 applications a day, 300 jobs per source per scan. |
| **Startups** | The ~110 startup boards, keeping your roles and job types. |
| **New grad** | Entry-level full-time roles from the SimplifyJobs new-grad list plus the startup boards. |

Mass-apply settings (all in Settings › Mass apply):

| Preference | Default | Meaning |
|---|---|---|
| `resume_strategy` | `original` | Which resume is sent. `original`: your uploaded file, byte for byte (your design and words). `light`: every word kept, only the most relevant bullets, projects and skills moved to the top per job. `full`: AI rewrite, guarded against invented facts. |
| `review_mode` | `swipe` | `swipe`: nothing is skipped for a low score. `auto`: the original threshold mode. |
| `auto_submit_kept` | on | Submit kept jobs as soon as the form is filled. Off: every kept job waits for approval. |
| `trust_generated_answers` | on | The agent's answers to open questions ("Why this company?") don't hold a kept job back. Eligibility questions are never guessed either way. |
| `auto_keep_min_score` | off | Keep jobs scoring at least this without swiping. |
| `exclude_no_sponsorship` | off | Skip postings that say they don't sponsor visas or require citizenship. |
| `max_jobs_per_source` | 50 | How many postings each source may return per scan (10–1000). |
| `sources.internship_lists` | SimplifyJobs + vanshb03 | Curated lists: `simplify-internships`, `vanshb03-internships`, `simplify-new-grad`, or any `listings.json` URL in the same format. |

Daily and per-platform caps (e.g. 40 Greenhouse, 10 Workday applications a day, with randomized
cool-downs) still apply to every submission.

## How it works

```
                 ┌──────────────────────────── Next.js dashboard (:3000) ─────────────────────────────┐
  you ──────────▶│ overview · swipe review · applications · jobs · e-mail · interviews · analytics ·… │
                 └──────────────┬───────────────────────────────────────────────▲─────────────────────┘
                   /api/v1/* (same-origin proxy)                                │ WebSocket (live updates)
                 ┌──────────────▼───────────────────────────────────────────────┴─────────────────────┐
                 │ FastAPI (:8000)  auth · resumes · jobs · applications · agent · e-mail · analytics │
                 └──────┬──────────────────────────┬───────────────────────────────┬──────────────────┘
                        │ PostgreSQL 16 + pgvector │ Redis (queue, rate limits,    │ Local disk / S3 / R2
                        │                          │ pub-sub for live updates)     │ (PDFs, screenshots)
                 ┌──────▼──────────────────────────▼───────────────────────────────▼──────────────────┐
                 │ Celery worker + beat   scan → match → ⏸ swipe → tailor → fill (Playwright) → submit │
                 │                        → Gmail monitor → calendar → reminders → analytics          │
                 └─────────────┬───────────────────────────┬──────────────────────────┬───────────────┘
                   Claude (Anthropic API, structured        Job boards & ATS          Gmail · Calendar
                   outputs; offline heuristics fallback)    (APIs + Chromium)         (Google OAuth)
```

The application lifecycle is `discovered → matched (waiting for your swipe) → preparing → approved →
applied → acknowledged → interview → offer / rejected`, with `pending approval` in between whenever a
question needs you (or you turned off **Apply automatically**). Every change is recorded in the
application's history.

**AI.** Claude is the primary model (`ANTHROPIC_MODEL`, default `claude-opus-5-5`), using JSON-schema
structured outputs, prompt caching and a refusal fallback. OpenAI is an optional secondary provider.
**Without any API key, every step still works** on built-in heuristics: keyword-based resume parsing,
rule-based scoring, template tailoring and cover letters, and rule-based e-mail classification. The
quality is lower but it's fully functional. All prompts are plain text files in [`prompts/`](prompts).

## Quick start (Docker)

Requirements: Docker with Compose v2, about 4 GB RAM free.

```bash
git clone https://github.com/saksham-eng560/autoapply-ai.git
cd autoapply-ai
cp .env.example .env
```

Edit `.env` and set at least:

```bash
SECRET_KEY=<python -c "import secrets; print(secrets.token_urlsafe(48))">
ENCRYPTION_KEY=<python -c "import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())">
ANTHROPIC_API_KEY=sk-ant-...        # optional but strongly recommended
```

Then start everything:

```bash
docker compose up --build -d        # or: make up
```

| | |
|---|---|
| Dashboard | http://localhost:3000 |
| API docs (OpenAPI) | http://localhost:8000/docs |
| Health | http://localhost:8000/health/ready |

This starts PostgreSQL + pgvector, Redis, the API (which runs database migrations on start), a Celery
worker with Chromium, Celery beat, and the dashboard. Open the dashboard, create your account, and
follow the **Get your agent ready** checklist.

Optional: `docker compose exec api python scripts/seed_db.py` creates a demo account
(`demo@example.com` / `demo-password-123`) with sample data, so every page has something to show.

## Try the whole loop safely with the demo careers site

`scripts/demo_site.py` is a fake company, "Acme Robotics". It has a careers page with three job postings
and real application forms that record submissions locally. Use it to watch the complete loop before
pointing the agent at real employers.

```bash
./start.sh --demo                               # starts it on :8765 along with everything else
python3 scripts/demo_site.py --host 0.0.0.0     # or on its own (no dependencies)
```

1. In the dashboard, upload your resume in **Resume Lab** (PDF, DOCX or TXT), or paste it as text.
2. In **Settings → Saved answers**, save your work authorization and sponsorship answers.
3. In **Settings → Preferences**, set a target role such as `Software Engineer`.
4. In **Settings → Job sources**, add a careers page and enable **Career pages** under platforms:
   - Docker: `http://host.docker.internal:8765/careers`
   - Local (non-Docker) setup: `http://127.0.0.1:8765/careers`
5. Click **Scan for jobs now**. The postings appear in **Swipe Review**.
6. Keep one (drag right or press →). It's tailored, filled in Chromium and submitted. Turn off
   **Apply automatically** first if you'd rather check the form screenshot, resume, cover letter and
   answers and click **Review & approve** yourself.
7. Open http://localhost:8765/submissions to see exactly what was submitted, including your resume PDF.

## Using it for real

1. **Upload your master resume** in Resume Lab and check the parsed result. Everything the agent writes
   is derived from it, so make it complete and accurate.
2. **Saved answers** (Settings): fill in work authorization, sponsorship, notice period, salary
   expectation, address, EEO preferences and so on. These answer most form questions directly.
3. **Mass apply** (Settings): apply the **Internships**, **Startups** or **New grad** preset, then check
   **Preferences**: target roles and locations, remote preference, salary range, job types, companies
   to target or avoid, excluded keywords and the daily application limit.
4. **Job sources**: add the companies you care about:
   - Greenhouse board tokens (`stripe` from `job-boards.greenhouse.io/stripe`)
   - Lever slugs (`jobs.lever.co/<company>`)
   - Ashby boards (`jobs.ashbyhq.com/<board>`)
   - Workday site URLs (`https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite`)
   - any careers page URL

   LinkedIn, Indeed, Glassdoor and Wellfound searches use your target roles and locations.
5. Optionally **connect Google** (Gmail + Calendar) and **sync LinkedIn** with the Chrome extension.
6. Start with `SUBMISSION_DRY_RUN=true` for a day. You get everything except the final click. Then
   turn it off.

Use **Scan for jobs now**, or let the scheduler scan every `scan_interval_hours`. New jobs land in
**Swipe Review**; kept jobs are applied to, and anything that needs you arrives in **Needs approval**
with a notification.

## Configuration

All settings are environment variables. [`.env.example`](.env.example) documents every one. The
important ones:

| Variable | Default | Purpose |
|---|---|---|
| `SECRET_KEY` | *(dev value)* | JWT signing. **Required in production.** |
| `ENCRYPTION_KEY` | derived from `SECRET_KEY` | AES-256-GCM key for OAuth tokens and cookies. Set it explicitly in production. |
| `ANTHROPIC_API_KEY` | — | Claude for parsing, matching, tailoring, cover letters, answers, e-mail, interview prep |
| `ANTHROPIC_MODEL` / `ANTHROPIC_EFFORT` | `claude-opus-5-5` / `medium` | Model and reasoning effort |
| `OPENAI_API_KEY` | — | Optional secondary provider (automatic failover) and embeddings |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | — | Gmail + Calendar + "Sign in with Google" |
| `FRONTEND_URL` | `http://localhost:3000` | Public dashboard URL (OAuth redirects, links in e-mails) |
| `ALLOW_REGISTRATION` | `true` | Set to `false` after creating your account |
| `AUTO_STAGE_APPLICATIONS` | `true` | Fill forms automatically after tailoring (always pauses for approval) |
| `SUBMISSION_DRY_RUN` | `false` | `true` = never click the final submit button |
| `BROWSER_HEADLESS` / `HUMAN_EMULATION` | `true` / `true` | Browser behaviour |
| `PROXY_URLS` | — | Comma-separated proxies (`http://user:pass@host:port`), rotated per session |
| `CAPTCHA_PROVIDER` / `CAPTCHA_API_KEY` | `2captcha` / — | CAPTCHA solving |
| `STORAGE_BACKEND` | `local` | `s3` for AWS S3, Cloudflare R2 or MinIO (`S3_*` variables) |
| `SMTP_*`, `DISCORD_WEBHOOK_URL`, `SLACK_WEBHOOK_URL` | — | Notification channels (Discord and Slack can also be set per user in Settings) |
| `CELERY_TASK_ALWAYS_EAGER` | `false` | Run background jobs in-process (no Redis or worker needed; for development) |
| `SENTRY_DSN` | — | Error tracking |
| `DATA_RETENTION_DAYS` | `730` | Automatic clean-up of closed applications (and their files) older than this |

## Connect Gmail and Google Calendar

1. In the [Google Cloud console](https://console.cloud.google.com/), create a project and enable the
   **Gmail API** and the **Google Calendar API**.
2. **OAuth consent screen**: choose External, add your e-mail as a test user, and add the scopes
   `gmail.readonly`, `gmail.modify`, `gmail.labels`, `calendar.events` and `calendar.readonly`.
   > While the app's publishing status is **Testing**, Google expires refresh tokens after 7 days and
   > you'll have to reconnect weekly. For personal use you can set the status to **In production**
   > without verification. You'll see an "unverified app" warning when connecting, and tokens stop
   > expiring.
3. **Credentials → Create credentials → OAuth client ID**: choose type **Web application**, and add
   this authorized redirect URI:
   ```
   {FRONTEND_URL}/api/v1/auth/google/callback      e.g. http://localhost:3000/api/v1/auth/google/callback
   ```
4. Put `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`, restart (`docker compose up -d`), then
   go to **Settings → Google → Connect**.

**Optional: real-time Gmail push** (otherwise the inbox is polled every `EMAIL_POLL_MINUTES`). This
needs a public HTTPS URL.

1. Create a Pub/Sub topic.
2. Grant `gmail-api-push@system.gserviceaccount.com` the **Pub/Sub Publisher** role on the topic.
3. Create a push subscription to `https://<your-domain>/api/v1/webhooks/gmail?token=<GMAIL_PUBSUB_VERIFICATION_TOKEN>`.
4. Set `GMAIL_PUBSUB_TOPIC=projects/<project>/topics/<topic>` and `GMAIL_PUBSUB_VERIFICATION_TOKEN`.

The watch is renewed daily.

## LinkedIn and the Chrome extension

LinkedIn search and Easy Apply run under your own LinkedIn session. The extension in
[`extension/`](extension) copies your session cookie to your AutoApply server. The cookie is stored
encrypted and re-synced every 12 hours and whenever it changes.

1. Open `chrome://extensions`, enable **Developer mode**, click **Load unpacked**, and select the
   `extension/` folder. CI also builds a zip artifact of it.
2. In the dashboard, go to **Settings → LinkedIn → Generate extension token**.
3. Open the extension popup and enter your dashboard URL (for example `http://localhost:3000`) and the
   token. Allow access to that origin when Chrome asks, then click **Sync LinkedIn session** while
   logged in to LinkedIn.

The extension only reads the LinkedIn `li_at` cookie and only sends it to the dashboard URL you entered.

## Local development without Docker

`./start.sh` does all of the following for you; the individual steps are here if you prefer them.

Requirements: Python 3.11+, Node 20+, PostgreSQL 16 with the `pgvector` extension (or SQLite for a
quick try), and Redis (optional with `CELERY_TASK_ALWAYS_EAGER=true`).

```bash
make setup          # backend venv + deps + Chromium, dashboard deps, .env
make migrate        # alembic upgrade head (or create tables on SQLite)
make api            # FastAPI on :8000 (reload)
make worker         # Celery worker        ┐ or set CELERY_TASK_ALWAYS_EAGER=true
make beat           # Celery beat schedule ┘ and skip both
make web            # Next.js dev server on :3000
make demo           # demo careers site on :8765
```

Simplest possible setup, with no Postgres or Redis: set `DATABASE_URL=sqlite:///./data/autoapply.db`,
`CELERY_TASK_ALWAYS_EAGER=true` and `REDIS_URL=` in `.env`, then run `make api` and `make web`.
Scheduled scans need beat and Redis.

Other useful commands:

```bash
make help                                                   # everything available
backend/.venv/bin/python scripts/test_scraper.py greenhouse --source stripe -k "Software Engineer"
backend/.venv/bin/python scripts/test_scraper.py url https://job-boards.greenhouse.io/stripe/jobs/123
backend/.venv/bin/python scripts/migrate.py --reembed       # after changing EMBEDDING_PROVIDER
```

## Deployment

### Single server with automatic HTTPS (simplest)

This works on any VPS with 2+ vCPU and 4+ GB RAM, with Docker installed.

```bash
# DNS: point your domain at the server, then:
cp .env.example .env     # set DOMAIN, SECRET_KEY, ENCRYPTION_KEY, POSTGRES_PASSWORD, API keys
docker compose -f docker-compose.prod.yml up -d --build      # or: make prod-up
```

Caddy obtains a Let's Encrypt certificate for `DOMAIN` automatically. It routes `/api/v1/*`, `/docs`
and `/health*` to the API and everything else to the dashboard. Set `ALLOW_REGISTRATION=false` once
your account exists. Set the Google redirect URI to `https://<DOMAIN>/api/v1/auth/google/callback`.
Back up the `pgdata` and `storage` volumes.

### AWS ECS Fargate + Vercel (the plan's production architecture)

- **Backend**: [`deploy-backend.yml`](.github/workflows/deploy-backend.yml) builds the backend image,
  pushes it to ECR, and rolls out new task definitions for the API, worker and beat ECS services.
  - It runs after CI passes on `main`, or manually.
  - Setup: create RDS PostgreSQL 16 (run `CREATE EXTENSION vector;`), ElastiCache Redis, an S3 or R2
    bucket, an ECR repository `autoapply-backend`, and three ECS services running the same image with
    commands `api`, `worker` and `beat`.
  - Suggested sizing: API 2 vCPU / 4 GB behind an ALB, worker 4 vCPU / 8 GB, beat 0.25 vCPU / 0.5 GB,
    with exactly **one** beat task.
  - Repository variables: `AWS_REGION`, `AWS_ROLE_ARN` (a GitHub OIDC role), `ECS_CLUSTER`, and
    optionally `ECR_REPOSITORY` and `ECS_SERVICES`.
  - Migrations run when the API starts, serialized with a Postgres advisory lock so replicas can start
    together.
- **Dashboard**: [`deploy-frontend.yml`](.github/workflows/deploy-frontend.yml) deploys to Vercel.
  - Create a Vercel project with Root Directory `frontend`.
  - Set its environment variables: `BACKEND_URL=https://api.<domain>` and
    `NEXT_PUBLIC_WS_URL=wss://api.<domain>/api/v1/ws`.
  - Add repository variables `VERCEL_ORG_ID` and `VERCEL_PROJECT_ID`, and the secret `VERCEL_TOKEN`.
  - Set `FRONTEND_URL` on the backend to the Vercel URL.

Both workflows skip themselves until their variables are set.

## Testing and CI

```bash
make test           # 90 backend tests on SQLite, incl. real-Chromium end-to-end tests (swipe → submit)
make test-pg        # the same suite on PostgreSQL + pgvector (TEST_DATABASE_URL)
make e2e            # only the browser end-to-end test
make lint           # ruff (backend + scripts), ESLint + TypeScript (dashboard)
```

The end-to-end test starts a mock company site with a careers page and an ATS form, then runs the real
pipeline: scan, match, tailor, fill in Chromium, pause, approve, submit. It asserts the exact fields the
employer received, and that nothing was sent before approval.

[`ci.yml`](.github/workflows/ci.yml) runs on every push and PR:

- **Backend**: ruff, bandit, a migration round trip (`upgrade`, then `check` for drift, then
  `downgrade`, then `upgrade`), and the test suite on both SQLite and PostgreSQL with coverage.
- **Dashboard**: lint, typecheck and production build.
- **Extension**: validation and packaging.
- **Docker**: builds both images, then smoke-tests the backend image by launching Chromium.

## Project structure

```
backend/
  app/
    api/            FastAPI routers (auth, users, resumes, jobs, applications, agent, communications,
                    interviews, analytics, files/webhooks/WebSocket)
    automation/     Playwright browser sessions, stealth, human emulation, proxies, CAPTCHA
    core/           database, security (JWT, bcrypt, AES-GCM), storage, Redis, WebSocket hub, logging
    models/         SQLAlchemy models (users, resumes, jobs, applications, communications, interviews, runs)
    schemas/        Pydantic request/response and resume-content schemas
    scrapers/       Greenhouse, Lever, Ashby, Workday, LinkedIn, Indeed, Glassdoor, Wellfound, curated
                    internship lists (SimplifyJobs, vanshb03), generic careers pages
    services/       orchestrator, LLM client, matcher, tailor + truthfulness guard, cover letters, question
                    answerer, resume parser, PDF generator, Gmail, e-mail parser, calendar, notifier,
                    analytics, rate limiter, LinkedIn sync, privacy
    submitters/     Greenhouse, Lever, Workday, LinkedIn Easy Apply, generic form engine
    worker/         Celery app, beat schedule and tasks
  alembic/          migrations (pgvector, enums, indexes)
  tests/            unit, API, scraper-fixture and browser end-to-end tests
frontend/           Next.js 14 dashboard (app router, Tailwind, shadcn/ui + Radix, framer-motion, SWR, Recharts, PWA)
extension/          Chrome MV3 extension (LinkedIn session sync)
prompts/            all LLM prompts as editable text files
scripts/            demo careers site, migrations, seed data, scraper CLI, local scheduler
start.sh, start.bat one-command launchers
docs/screenshots/   dashboard screenshots
docker-compose.yml, docker-compose.prod.yml, Caddyfile, Makefile, .github/workflows/
PLAN.md             the full design this implementation follows
```

## Security and privacy

- **Passwords**: bcrypt.
- **Sessions**: httpOnly SameSite cookies, with `COOKIE_SECURE` in production. Short-lived scoped
  tokens for the WebSocket and the extension.
- **Credentials**: OAuth refresh tokens and the LinkedIn cookie are encrypted at rest (AES-256-GCM).
- **Isolation**: every query is scoped to the signed-in user, and file downloads are checked against
  the owner.
- **LLM prompts** never include passwords or tokens. Resume content is sent to the configured model
  provider only.
- **Your data**: **Settings → Export your data** gives you everything as JSON. **Delete my account**
  removes the database rows, stored files and tokens. Closed applications are purged after `DATA_RETENTION_DAYS`.
- **Rate limits**: per-platform application limits and randomized pacing protect your accounts.
- **Production checklist**: set `SECRET_KEY`, `ENCRYPTION_KEY`, `COOKIE_SECURE=true` and
  `ALLOW_REGISTRATION=false`, and use HTTPS. The production Compose file requires the keys and sets up
  HTTPS and secure cookies; you set `ALLOW_REGISTRATION=false` after signing up.

## Responsible use

AutoApply AI is a personal tool. It applies **as you**, with **your real information**, to jobs **you
approved**.

- **Truthfulness is enforced.** The agent can reword and reorder your experience, but it cannot invent
  it. Review every application anyway: you are the one submitting it.
- **Respect site terms.** Some job sites, notably LinkedIn, Indeed and Glassdoor, restrict automated
  access in their terms of service, and automated use can get an account restricted.
  - The public ATS APIs (Greenhouse, Lever, Ashby, Workday) and company careers pages are the most
    reliable sources.
  - Use browser-based sources sparingly and keep the default rate limits.
  - You are responsible for how you use this tool.
- **Volume with care.** Mass applying works best when you keep the jobs you'd genuinely take, keep
  your saved answers accurate, and stay within the default rate limits.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard shows "degraded" at `/api/health` | The API isn't reachable from the dashboard. Check `docker compose logs api` and that `BACKEND_URL` points to it. |
| Nothing gets prepared after a scan | In swipe mode nothing is prepared until you keep it: open **Swipe Review**. Upload a master resume first. **All jobs** shows each job's score and why it was skipped, and **Agent Logs** shows each run step by step. |
| Kept jobs stop in "Needs approval" | A question needs you (usually visa sponsorship or work authorization). Save the answer in **Settings › Saved answers** once and future forms are filled automatically. |
| `./start.sh` says a port is in use | Something else runs on :3000 or :8000. Stop it, or run `API_PORT=8010 WEB_PORT=3010 ./start.sh`. |
| "Required answer(s) are empty" at approval | Eligibility questions are never guessed. Answer them once and they're remembered (also editable in **Settings → Saved answers**). |
| Application fails with a CAPTCHA or bot block | Set `CAPTCHA_API_KEY` and residential `PROXY_URLS`, or use **Mark as applied** after applying manually through the form link. |
| LinkedIn session invalid | Log in to LinkedIn in Chrome and click **Sync LinkedIn session** in the extension. |
| Google disconnects every 7 days | Your OAuth consent screen is in Testing mode (see [Connect Gmail and Google Calendar](#connect-gmail-and-google-calendar)). |
| Chromium crashes in Docker | Give the worker more shared memory (`shm_size`, 1–2 GB is already set) and RAM. |
| Change the AI's behaviour | Edit the prompt files in `prompts/`, then restart the API and worker. |

## License

[MIT](LICENSE)
