# AutoApply AI

An autonomous job-application agent that you run yourself. It finds jobs that fit you, tailors your
resume and writes a cover letter for each one, fills in the application form in a real browser, and
then **stops and waits for your approval** before anything is submitted. After you apply, it watches
your Gmail for replies, updates each application's status, puts interviews on your Google Calendar
with prep notes, and shows you what is working.

> **Nothing is ever submitted without your explicit approval.** The agent fills the form, takes a
> screenshot and pauses. You review the tailored resume, cover letter and every answer, edit what you
> like, and click **Approve & submit**. Only then does it re-open the form and submit exactly what
> you reviewed.

| Overview | Review a filled application |
|---|---|
| ![Overview](docs/screenshots/overview.png) | ![Review](docs/screenshots/review.png) |
| **Approval gate** | **Analytics** |
| ![Approval](docs/screenshots/approval.png) | ![Analytics](docs/screenshots/analytics.png) |

---

## Contents

- [What it does](#what-it-does)
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

## What it does

**Discovery.** Scans Greenhouse, Lever, Ashby and Workday boards through their public APIs, reads
company careers pages (schema.org `JobPosting` markup, and embedded ATS boards it detects), and
searches LinkedIn, Indeed, Glassdoor and Wellfound with a real browser. It removes duplicates across
sources, and scans run on a schedule (every 6 hours by default) or when you click **Scan for jobs now**.
You can also paste any job URL.

**Matching.** Each job gets a 0–100 score across five parts: skills, experience, industry, location
and compensation. The score also explains which of your skills are strong matches and which the job
wants that you don't have. Jobs you've excluded (companies to avoid, keywords, seniority, location,
salary floor) are filtered out before any AI call. Only jobs above your threshold (80 by default) are
prepared, highest score and freshest first, up to your daily limit.

**Truthful tailoring.** Your master resume is rewritten for each job: the summary, bullet order,
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

**Approval, then submission.** Every prepared application waits in **Needs approval** with the
filled-form screenshot, tailored resume, cover letter, answers and match analysis. Submission happens
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

**Dashboard.** Next.js dashboard with an overview, applications pipeline, job browser, e-mail feed,
interviews, analytics (response, interview and offer rates, time to response, platform effectiveness,
keywords that get callbacks), a resume editor, agent logs, and settings. Live updates arrive over
WebSocket. It has light and dark themes, can be installed as a PWA, and sends browser notifications.

**Notifications.** In-app, e-mail (SMTP or your own Gmail), Discord and Slack. You choose which
events go to which channel, and there's a weekly summary.

**Your data.** Export everything as JSON, or delete your account with all files and tokens (GDPR/CCPA).
OAuth tokens and cookies are encrypted with AES-256-GCM, and closed applications older than the retention period are
cleaned up automatically.

## How it works

```
                 ┌──────────────────────────── Next.js dashboard (:3000) ─────────────────────────────┐
  you ──────────▶│ overview · applications · approval · jobs · e-mail · interviews · analytics · ...  │
                 └──────────────┬───────────────────────────────────────────────▲─────────────────────┘
                   /api/v1/* (same-origin proxy)                                │ WebSocket (live updates)
                 ┌──────────────▼───────────────────────────────────────────────┴─────────────────────┐
                 │ FastAPI (:8000)  auth · resumes · jobs · applications · agent · e-mail · analytics │
                 └──────┬──────────────────────────┬───────────────────────────────┬──────────────────┘
                        │ PostgreSQL 16 + pgvector │ Redis (queue, rate limits,    │ Local disk / S3 / R2
                        │                          │ pub-sub for live updates)     │ (PDFs, screenshots)
                 ┌──────▼──────────────────────────▼───────────────────────────────▼──────────────────┐
                 │ Celery worker + beat   scan → match → tailor → fill (Playwright) → ⏸ approval       │
                 │                        → submit → Gmail monitor → calendar → reminders → analytics │
                 └─────────────┬───────────────────────────┬──────────────────────────┬───────────────┘
                   Claude (Anthropic API, structured        Job boards & ATS          Gmail · Calendar
                   outputs; offline heuristics fallback)    (APIs + Chromium)         (Google OAuth)
```

The application lifecycle is `discovered → matched → preparing → pending approval → approved → applied
→ acknowledged → interview → offer / rejected`. Every change is recorded in the application's history.

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
python3 scripts/demo_site.py --host 0.0.0.0     # no dependencies; serves :8765
```

1. In the dashboard, upload your resume in **Resume Lab** (PDF, DOCX or TXT), or paste it as text.
2. In **Settings → Search preferences**, set a target role such as `Software Engineer` and a threshold
   such as `50`.
3. In **Settings → Job sources**, add a careers page and enable **Career pages** under platforms:
   - Docker: `http://host.docker.internal:8765/careers`
   - Local (non-Docker) setup: `http://127.0.0.1:8765/careers`
4. Click **Scan for jobs now**. Matching jobs are tailored, filled in Chromium, and appear under **Needs approval**.
5. Open one, check the form screenshot, resume, cover letter and answers, then click **Review & approve**.
6. Open http://localhost:8765/submissions to see exactly what was submitted, including your resume PDF.

## Using it for real

1. **Upload your master resume** in Resume Lab and check the parsed result. Everything the agent writes
   is derived from it, so make it complete and accurate.
2. **Saved answers** (Settings): fill in work authorization, sponsorship, notice period, salary
   expectation, address, EEO preferences and so on. These answer most form questions directly.
3. **Search preferences**: target roles and locations, remote preference, salary range, experience
   levels, job types, companies to target or avoid, excluded keywords, the match threshold and the
   daily application limit.
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

Use **Scan for jobs now**, or let the scheduler scan every `scan_interval_hours`. Prepared
applications arrive in **Needs approval**, and you get a notification for each one.

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
make test           # 74 backend tests on SQLite, incl. a real-Chromium end-to-end test
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
    scrapers/       Greenhouse, Lever, Ashby, Workday, LinkedIn, Indeed, Glassdoor, Wellfound, generic
    services/       orchestrator, LLM client, matcher, tailor + truthfulness guard, cover letters, question
                    answerer, resume parser, PDF generator, Gmail, e-mail parser, calendar, notifier,
                    analytics, rate limiter, LinkedIn sync, privacy
    submitters/     Greenhouse, Lever, Workday, LinkedIn Easy Apply, generic form engine
    worker/         Celery app, beat schedule and tasks
  alembic/          migrations (pgvector, enums, indexes)
  tests/            unit, API, scraper-fixture and browser end-to-end tests
frontend/           Next.js 14 dashboard (app router, Tailwind, SWR, Recharts, PWA)
extension/          Chrome MV3 extension (LinkedIn session sync)
prompts/            all LLM prompts as editable text files
scripts/            demo careers site, migrations, seed data, scraper CLI
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
- **Quality over volume.** A higher match threshold and a lower daily limit get better results than
  mass-applying.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Dashboard shows "degraded" at `/api/health` | The API isn't reachable from the dashboard. Check `docker compose logs api` and that `BACKEND_URL` points to it. |
| Nothing gets prepared after a scan | Upload a master resume and check your threshold. The **Jobs** page shows each job's score and why it was skipped, and **Agent Logs** shows each run step by step. |
| "Required answer(s) are empty" at approval | Eligibility questions are never guessed. Answer them once and they're remembered (also editable in **Settings → Saved answers**). |
| Application fails with a CAPTCHA or bot block | Set `CAPTCHA_API_KEY` and residential `PROXY_URLS`, or use **Mark as applied** after applying manually through the form link. |
| LinkedIn session invalid | Log in to LinkedIn in Chrome and click **Sync LinkedIn session** in the extension. |
| Google disconnects every 7 days | Your OAuth consent screen is in Testing mode (see [Connect Gmail and Google Calendar](#connect-gmail-and-google-calendar)). |
| Chromium crashes in Docker | Give the worker more shared memory (`shm_size`, 1–2 GB is already set) and RAM. |
| Change the AI's behaviour | Edit the prompt files in `prompts/`, then restart the API and worker. |

## License

[MIT](LICENSE)
