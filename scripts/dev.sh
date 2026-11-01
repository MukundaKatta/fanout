#!/usr/bin/env bash
# One-command local dev for Fanout: Postgres (Docker) + backend + web.
#
#   scripts/dev.sh             # bootstrap anything missing, then run everything
#   scripts/dev.sh --no-db     # don't touch Docker; use whatever DATABASE_URL points at
#   scripts/dev.sh --setup     # bootstrap only (venv, npm deps, env files, db), then exit
#
# Env overrides: BACKEND_PORT (default 8000), WEB_PORT (default 3000).
# Ctrl-C stops the backend and web; Postgres keeps running
# (`docker compose stop db` to stop it, `docker compose down -v` to wipe it).
#
# Idempotent: re-running only reinstalls deps when requirements*.txt or
# package-lock.json changed, and never overwrites existing .env files.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
WEB="$ROOT/web"
BACKEND_PORT="${BACKEND_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

USE_DB=1
SETUP_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --no-db) USE_DB=0 ;;
    --setup) SETUP_ONLY=1 ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown argument: $arg (try --help)" >&2; exit 2 ;;
  esac
done

log()  { printf '\033[1;36m[dev]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[dev]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[dev]\033[0m %s\n' "$*" >&2; exit 1; }

need() { command -v "$1" >/dev/null 2>&1 || die "missing prerequisite: $1 ($2)"; }

# Portable across Linux and macOS (stock bash 3.2, BSD userland).
if command -v sha256sum >/dev/null 2>&1; then
  hash_files() { cat "$@" | sha256sum | cut -d' ' -f1; }
else
  hash_files() { cat "$@" | shasum -a 256 | cut -d' ' -f1; }
fi
# Line-by-line in pure bash: awk/sed block-buffer piped output (mawk, BSD sed).
prefix() { while IFS= read -r line || [ -n "$line" ]; do printf '%s%s\n' "$1" "$line"; done; }

# ---------------------------------------------------------------- prereqs
need python3 "Python 3.11+"
need node "Node 22+"
need npm "ships with Node"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' \
  || die "Python 3.11+ required (found $(python3 --version))"
node_major="$(node -p 'process.versions.node.split(".")[0]')"
[ "$node_major" -ge 22 ] || warn "Node 22+ is what CI uses (found $(node --version))"

# ---------------------------------------------------------------- env files
if [ ! -f "$BACKEND/.env" ]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  log "created backend/.env from .env.example — set GROQ_API_KEY to generate drafts"
fi
if [ ! -f "$WEB/.env.local" ]; then
  cp "$WEB/.env.local.example" "$WEB/.env.local"
  log "created web/.env.local from .env.local.example (dev mode, no Supabase auth)"
fi
if grep -Eq '^GROQ_API_KEY=(your_key_here)?$' "$BACKEND/.env"; then
  warn "GROQ_API_KEY is not set in backend/.env — the app runs, but /generate, /variations"
  warn "and /operator/run will fail until you add a key (https://console.groq.com/keys)"
fi

# ---------------------------------------------------------------- backend deps
VENV="$BACKEND/.venv"
if [ ! -x "$VENV/bin/python" ]; then
  log "creating backend/.venv"
  python3 -m venv "$VENV"
fi
req_hash="$(hash_files "$BACKEND/requirements.txt" "$BACKEND/requirements-dev.txt")"
if [ "$(cat "$VENV/.fanout-req-hash" 2>/dev/null || true)" != "$req_hash" ]; then
  log "installing backend deps (requirements-dev.txt)"
  "$VENV/bin/pip" install -q --upgrade pip
  "$VENV/bin/pip" install -q -r "$BACKEND/requirements-dev.txt"
  echo "$req_hash" > "$VENV/.fanout-req-hash"
fi

# ---------------------------------------------------------------- web deps
lock_hash="$(hash_files "$WEB/package-lock.json")"
if [ "$(cat "$WEB/node_modules/.fanout-lock-hash" 2>/dev/null || true)" != "$lock_hash" ]; then
  log "installing web deps (npm ci)"
  (cd "$WEB" && npm ci --no-audit --no-fund)
  echo "$lock_hash" > "$WEB/node_modules/.fanout-lock-hash"
fi

# ---------------------------------------------------------------- postgres
if [ "$USE_DB" = 1 ]; then
  need docker "or pass --no-db and point DATABASE_URL in backend/.env at your own Postgres"
  docker info >/dev/null 2>&1 || die "Docker daemon not reachable — start Docker, or use --no-db"
  log "starting Postgres (docker compose up -d --wait db)"
  (cd "$ROOT" && docker compose up -d --wait db)
fi

if [ "$SETUP_ONLY" = 1 ]; then
  log "setup complete"
  exit 0
fi

# ---------------------------------------------------------------- run
# Kill every child (uvicorn reloader, next dev workers) when we exit.
trap 'trap - INT TERM EXIT; kill 0 2>/dev/null || true' INT TERM EXIT

log "backend → http://localhost:$BACKEND_PORT  (docs at /docs)"
# Non-default ports: real env vars beat .env files for both apps, so override
# the cross-wiring here instead of making you edit them.
backend_env=(); web_env=()
if [ "$WEB_PORT" != 3000 ]; then backend_env+=("CORS_ORIGINS=http://localhost:$WEB_PORT"); fi
if [ "$BACKEND_PORT" != 8000 ]; then web_env+=("NEXT_PUBLIC_API_URL=http://localhost:$BACKEND_PORT"); fi

(cd "$BACKEND" && exec env ${backend_env[@]+"${backend_env[@]}"} "$VENV/bin/uvicorn" app.main:app --reload --port "$BACKEND_PORT") \
  2>&1 | prefix "[backend] " &
backend_pid=$!

log "web     → http://localhost:$WEB_PORT"
(cd "$WEB" && exec env ${web_env[@]+"${web_env[@]}"} npx next dev --port "$WEB_PORT") \
  2>&1 | prefix "[web]     " &
web_pid=$!

if [ "$BACKEND_PORT" != 8000 ]; then
  warn "the extension only has host permission for localhost:8000 (extension/manifest.json)"
fi

# Exit as soon as either process dies so a crash isn't hidden.
# (Polling instead of `wait -n` so this works on macOS's bash 3.2.)
while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$web_pid" 2>/dev/null; do
  sleep 1
done
warn "a dev process exited — shutting down"
exit 1
