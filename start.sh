#!/usr/bin/env bash
# ------------------------------------------------------------------------------------------------
#  AutoApply AI — one command to set up and run everything.
#
#    ./start.sh              local mode: no Docker needed (SQLite; Redis + Celery if installed)
#    ./start.sh --demo       also seed a demo account and serve the demo careers site on :8765
#    ./start.sh --docker     full stack in Docker Compose (PostgreSQL, Redis, worker, beat)
#    ./start.sh --stop       stop the Docker stack
#    ./start.sh --prod       local mode with a production build of the dashboard (faster pages)
#    ./start.sh --reset      wipe the local SQLite database first
#    ./start.sh --help
#
#  First run installs everything it needs (Python venv, Chromium, npm packages) and writes a .env
#  with fresh secrets. Later runs only reinstall when requirements change. Ctrl-C stops it all.
# ------------------------------------------------------------------------------------------------
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

MODE="local"; DEMO=0; PROD=0; RESET=0; OPEN_BROWSER=1
API_PORT="${API_PORT:-8000}"; WEB_PORT="${WEB_PORT:-3000}"; DEMO_PORT="${DEMO_PORT:-8765}"
LOG_DIR="$ROOT/logs"

if [ -t 1 ]; then
  RED=$'\033[38;5;203m'; DIM=$'\033[2m'; BOLD=$'\033[1m'; GREEN=$'\033[32m'; YELLOW=$'\033[33m'; RESET_C=$'\033[0m'
else
  RED=""; DIM=""; BOLD=""; GREEN=""; YELLOW=""; RESET_C=""
fi
say()  { printf '%s\n' "${RED}▌${RESET_C} $*"; }
ok()   { printf '%s\n' "${GREEN}✓${RESET_C} $*"; }
warn() { printf '%s\n' "${YELLOW}!${RESET_C} $*"; }
die()  { printf '%s\n' "${RED}✗ $*${RESET_C}" >&2; exit 1; }

usage() { sed -n '3,15p' "$0" | sed 's/^#  \{0,1\}//'; exit 0; }

for arg in "$@"; do
  case "$arg" in
    --docker) MODE="docker" ;;
    --stop) MODE="stop" ;;
    --demo) DEMO=1 ;;
    --prod) PROD=1 ;;
    --reset) RESET=1 ;;
    --no-open) OPEN_BROWSER=0 ;;
    -h|--help) usage ;;
    *) die "Unknown option: $arg (see ./start.sh --help)" ;;
  esac
done

banner() {
  printf '\n%s\n' "${BOLD}  [▪ AutoApply AI${RESET_C}  ${DIM}— swipe right, we apply${RESET_C}"
  printf '%s\n\n' "${DIM}  ────────────────────────────────────────────${RESET_C}"
}

open_url() {
  [ "$OPEN_BROWSER" = 1 ] || return 0
  if command -v open >/dev/null 2>&1; then open "$1" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$1" >/dev/null 2>&1 || true
  fi
}

wait_for() {  # wait_for <url> <seconds> <name>
  local url="$1" secs="$2" name="$3" i=0
  while [ "$i" -lt "$secs" ]; do
    if curl -fsS -o /dev/null --max-time 3 "$url" 2>/dev/null; then ok "$name is up"; return 0; fi
    sleep 1; i=$((i + 1))
  done
  return 1
}

port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1; }

# ------------------------------------------------------------------------------------------------ .env
PY_BOOT=""
for candidate in python3.13 python3.12 python3.11 python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY_BOOT="$candidate"; break
  fi
done

ensure_env() {
  if [ ! -f .env ]; then
    cp .env.example .env
    say "Created .env from .env.example"
  fi
  local gen="${PY_BOOT:-python3}"
  if grep -qE '^SECRET_KEY=(change-me.*)?$' .env; then
    local secret; secret="$("$gen" -c 'import secrets; print(secrets.token_urlsafe(48))')"
    "$gen" - "$secret" <<'PY'
import re, sys
text = open(".env").read()
text = re.sub(r"(?m)^SECRET_KEY=.*$", "SECRET_KEY=" + sys.argv[1], text)
open(".env", "w").write(text)
PY
    ok "Generated SECRET_KEY"
  fi
  if grep -qE '^ENCRYPTION_KEY=[[:space:]]*(#.*)?$' .env; then
    local key; key="$("$gen" -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
    "$gen" - "$key" <<'PY'
import re, sys
text = open(".env").read()
text = re.sub(r"(?m)^ENCRYPTION_KEY=.*$", "ENCRYPTION_KEY=" + sys.argv[1], text)
open(".env", "w").write(text)
PY
    ok "Generated ENCRYPTION_KEY"
  fi
  if ! grep -qE '^ANTHROPIC_API_KEY=.+' .env; then
    warn "No ANTHROPIC_API_KEY in .env — everything works on built-in heuristics; add a key for much better tailoring."
  fi
}

# ------------------------------------------------------------------------------------------------ docker
if [ "$MODE" = "stop" ]; then
  banner
  docker compose down && ok "Docker stack stopped"
  exit 0
fi

if [ "$MODE" = "docker" ]; then
  banner
  command -v docker >/dev/null 2>&1 || die "Docker is not installed — install Docker Desktop, or run ./start.sh without --docker."
  docker info >/dev/null 2>&1 || die "Docker is installed but not running — start Docker Desktop and try again."
  ensure_env
  say "Building and starting the stack (first build takes a few minutes)…"
  docker compose up --build -d
  if [ "$DEMO" = 1 ]; then
    wait_for "http://127.0.0.1:$API_PORT/health" 180 "API" || die "API did not start — see: docker compose logs api"
    docker compose exec -T api python scripts/seed_db.py || true
  fi
  wait_for "http://127.0.0.1:$WEB_PORT/" 240 "Dashboard" || die "Dashboard did not start — see: docker compose logs frontend"
  printf '\n  %s\n  %s\n  %s\n\n' "${BOLD}Dashboard${RESET_C}  http://localhost:$WEB_PORT" \
    "${BOLD}API docs${RESET_C}   http://localhost:$API_PORT/docs" "${DIM}Stop with ./start.sh --stop · logs: docker compose logs -f${RESET_C}"
  open_url "http://localhost:$WEB_PORT"
  exit 0
fi

# ------------------------------------------------------------------------------------------------ local
banner
[ -n "$PY_BOOT" ] || die "Python 3.11+ is required (https://www.python.org/downloads/). Or run ./start.sh --docker"
command -v node >/dev/null 2>&1 || die "Node.js 20+ is required (https://nodejs.org). Or run ./start.sh --docker"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[ "$NODE_MAJOR" -ge 18 ] || die "Node.js 18.18+ is required (found $(node -v))."
command -v curl >/dev/null 2>&1 || die "curl is required."
ok "Python $("$PY_BOOT" -c 'import platform; print(platform.python_version())') · Node $(node -v)"

ensure_env
mkdir -p "$LOG_DIR" backend/data

hash_of() { "$PY_BOOT" -c 'import hashlib, sys; print(hashlib.sha256(b"".join(open(p, "rb").read() for p in sys.argv[1:])).hexdigest())' "$@"; }

# Python environment
VENV="$ROOT/backend/.venv"
PY="$VENV/bin/python"
if [ ! -x "$PY" ]; then
  say "Creating Python virtualenv (backend/.venv)…"
  "$PY_BOOT" -m venv "$VENV"
fi
REQ_HASH="$(hash_of backend/requirements.txt backend/requirements-dev.txt)"
if [ "$(cat "$VENV/.req-hash" 2>/dev/null || true)" != "$REQ_HASH" ]; then
  say "Installing backend dependencies (first run takes a couple of minutes)…"
  "$PY" -m pip install -q -U pip >/dev/null
  "$PY" -m pip install -q -r backend/requirements-dev.txt
  echo "$REQ_HASH" > "$VENV/.req-hash"
  ok "Backend dependencies installed"
fi
PW_VERSION="$("$PY" -c 'from importlib.metadata import version; print(version("playwright"))')"
if [ "$(cat "$VENV/.chromium-stamp" 2>/dev/null || true)" != "$PW_VERSION" ]; then
  say "Installing Chromium for the form-filling browser…"
  if "$PY" -m playwright install chromium >"$LOG_DIR/playwright-install.log" 2>&1; then
    echo "$PW_VERSION" > "$VENV/.chromium-stamp"; ok "Chromium ready"
  else
    warn "Chromium install failed (see logs/playwright-install.log). Form filling needs it; on Linux try: $PY -m playwright install --with-deps chromium"
  fi
fi

# Dashboard dependencies
LOCK_HASH="$(hash_of frontend/package-lock.json)"
if [ ! -d frontend/node_modules ] || [ "$(cat frontend/node_modules/.lock-hash 2>/dev/null || true)" != "$LOCK_HASH" ]; then
  say "Installing dashboard dependencies (npm ci)…"
  (cd frontend && npm ci --no-audit --no-fund --loglevel=error)
  echo "$LOCK_HASH" > frontend/node_modules/.lock-hash
  ok "Dashboard dependencies installed"
fi

# Runtime configuration for local mode (overrides .env for this run only)
export DATABASE_URL="${LOCAL_DATABASE_URL:-sqlite:///$ROOT/backend/data/autoapply.db}"
export LOCAL_STORAGE_PATH="$ROOT/backend/data/storage"
export FRONTEND_URL="http://localhost:$WEB_PORT"
export PUBLIC_API_URL="http://localhost:$API_PORT"
export CORS_ORIGINS="http://localhost:$WEB_PORT,http://127.0.0.1:$WEB_PORT"
export BACKEND_URL="http://127.0.0.1:$API_PORT"
export NEXT_PUBLIC_WS_URL="ws://localhost:$API_PORT/api/v1/ws"
export NEXT_TELEMETRY_DISABLED=1
export PYTHONUNBUFFERED=1

if [ "$RESET" = 1 ]; then
  rm -f "$ROOT"/backend/data/autoapply.db "$ROOT"/backend/data/autoapply.db-*
  warn "Local database wiped"
fi

USE_REDIS=0
if command -v redis-cli >/dev/null 2>&1 && redis-cli -p 6379 ping >/dev/null 2>&1; then
  USE_REDIS=1
elif command -v redis-server >/dev/null 2>&1; then
  USE_REDIS=2  # we'll start one
fi
if [ "$USE_REDIS" = 0 ]; then
  export REDIS_URL="" CELERY_TASK_ALWAYS_EAGER=true
else
  export REDIS_URL="redis://localhost:6379/0" CELERY_TASK_ALWAYS_EAGER=false
fi

for port in "$API_PORT" "$WEB_PORT"; do
  port_busy "$port" && die "Port $port is already in use — stop whatever runs there (or set API_PORT / WEB_PORT)."
done

PIDS=""
cleanup() {
  trap - INT TERM EXIT
  printf '\n'; say "Stopping AutoApply…"
  # Every service runs in its own process group: stop the whole group (npm → next → next-server, ...).
  for pid in $PIDS; do kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true; done
  sleep 2
  for pid in $PIDS; do kill -KILL -- "-$pid" 2>/dev/null || true; done
  ok "Stopped. See you next scan."
}
trap 'cleanup; exit 130' INT TERM
trap cleanup EXIT
set -m  # background jobs get their own process groups, so cleanup can stop their children too

run_bg() {  # run_bg <name> <dir> <command...>
  local name="$1" dir="$2"; shift 2
  (cd "$dir" && exec "$@") >"$LOG_DIR/$name.log" 2>&1 &
  PIDS="$PIDS $!"
}

if [ "$USE_REDIS" = 2 ]; then
  run_bg redis "$ROOT" redis-server --port 6379 --save "" --appendonly no
  sleep 1
fi

say "Preparing the database…"
"$PY" scripts/migrate.py >"$LOG_DIR/migrate.log" 2>&1 || { cat "$LOG_DIR/migrate.log"; die "Database migration failed"; }
ok "Database ready ($( [ "${DATABASE_URL#sqlite}" != "$DATABASE_URL" ] && echo "SQLite: backend/data/autoapply.db" || echo "$DATABASE_URL"))"

if [ "$DEMO" = 1 ]; then
  "$PY" scripts/seed_db.py >"$LOG_DIR/seed.log" 2>&1 && ok "Demo account: demo@example.com / demo-password-123" || warn "Seeding skipped (see logs/seed.log)"
  run_bg demo-site "$ROOT" "$PY" scripts/demo_site.py --port "$DEMO_PORT"
fi

say "Starting the API…"
run_bg api "$ROOT/backend" "$PY" -m uvicorn app.main:app --host 127.0.0.1 --port "$API_PORT"
if [ "$USE_REDIS" != 0 ]; then
  run_bg worker "$ROOT/backend" "$PY" -m celery -A app.worker.celery_app worker -Q default,browser --concurrency 2 --loglevel INFO
  run_bg beat "$ROOT/backend" "$PY" -m celery -A app.worker.celery_app beat --loglevel INFO --schedule "$ROOT/backend/data/celerybeat-schedule"
  QUEUE_NOTE="Redis + Celery worker + beat"
else
  run_bg scheduler "$ROOT" "$PY" scripts/local_scheduler.py
  QUEUE_NOTE="in-process tasks + local scheduler (install Redis for a separate worker)"
fi
wait_for "http://127.0.0.1:$API_PORT/health" 90 "API" || { tail -n 40 "$LOG_DIR/api.log"; die "API did not start (logs/api.log)"; }

if [ "$PROD" = 1 ]; then
  say "Building the dashboard (production)…"
  (cd frontend && npm run build >"$LOG_DIR/web-build.log" 2>&1) || { tail -n 40 "$LOG_DIR/web-build.log"; die "Dashboard build failed"; }
  run_bg web "$ROOT/frontend" node_modules/.bin/next start -p "$WEB_PORT"
else
  say "Starting the dashboard…"
  run_bg web "$ROOT/frontend" node_modules/.bin/next dev -p "$WEB_PORT"
fi
wait_for "http://127.0.0.1:$WEB_PORT/api/health" 180 "Dashboard" || { tail -n 40 "$LOG_DIR/web.log"; die "Dashboard did not start (logs/web.log)"; }

printf '\n'
printf '  %s  %s\n' "${BOLD}Dashboard${RESET_C}" "http://localhost:$WEB_PORT"
printf '  %s   %s\n' "${BOLD}API docs${RESET_C}" "http://localhost:$API_PORT/docs"
[ "$DEMO" = 1 ] && printf '  %s  %s\n' "${BOLD}Demo site${RESET_C}" "http://localhost:$DEMO_PORT/careers"
printf '  %s     %s\n' "${BOLD}Queue${RESET_C}" "$QUEUE_NOTE"
printf '  %s      %s\n\n' "${BOLD}Logs${RESET_C}" "logs/*.log"
printf '%s\n' "${DIM}  First time? Create your account → upload your resume → Settings › Mass apply › Internships"
printf '%s\n\n' "  preset → save your visa / work-authorization answers → Scan → swipe. Ctrl-C stops everything.${RESET_C}"
open_url "http://localhost:$WEB_PORT"

# Stream the logs until Ctrl-C (or a service dies).
tail -n 0 -F "$LOG_DIR"/api.log "$LOG_DIR"/web.log 2>/dev/null &
PIDS="$PIDS $!"
while true; do
  for pid in $PIDS; do
    if ! kill -0 "$pid" 2>/dev/null; then
      warn "A service stopped unexpectedly — check logs/ for details."
      exit 1
    fi
  done
  sleep 3
done
