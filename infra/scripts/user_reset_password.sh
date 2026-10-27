#!/usr/bin/env bash
# Owner recovery (ui-login D-9): set a user's password through the admin-token route.
# Usage: infra/scripts/user_reset_password.sh <email>     (or: make user-reset-password EMAIL=<email>)
# Needs NEWSDOCK_ADMIN_TOKEN in .env and the API running. The new password is read
# without echo, sent only in the request body (stdin), never as an argument, and the
# token goes through a private header file, so neither shows up in `ps` or history.
# RESET_ROOT overrides the repository root (used by tests).

set -euo pipefail

ROOT="${RESET_ROOT:-$(cd "$(dirname "$0")/../.." && pwd)}"
EMAIL="${1:-}"
[ -n "$EMAIL" ] || { echo "usage: make user-reset-password EMAIL=<email>" >&2; exit 2; }
[ -f "$ROOT/.env" ] || { echo "missing .env: cp .env.example .env" >&2; exit 1; }
set -a
# shellcheck disable=SC1091
. "$ROOT/.env"
set +a
[ -n "${NEWSDOCK_ADMIN_TOKEN:-}" ] || {
  echo "set NEWSDOCK_ADMIN_TOKEN in .env first (restart the api after setting it)" >&2
  exit 1
}

read -r -s -p "New password for $EMAIL: " PASSWORD || true
echo >&2
read -r -s -p "Repeat the password: " CONFIRM || true
echo >&2
[ -n "$PASSWORD" ] && [ "$PASSWORD" = "$CONFIRM" ] || {
  echo "the two passwords do not match (or are empty); nothing was changed" >&2
  exit 1
}

# JSON-encode safely: the password goes through stdin, the email is not secret
BODY="$(printf '%s' "$PASSWORD" | python3 -c '
import json, sys
print(json.dumps({"email": sys.argv[1], "password": sys.stdin.read()}))
' "$EMAIL")"

HEADER_FILE="$(mktemp)"
trap 'rm -f "$HEADER_FILE"' EXIT
chmod 600 "$HEADER_FILE"
printf 'Authorization: Bearer %s\n' "$NEWSDOCK_ADMIN_TOKEN" > "$HEADER_FILE"

STATUS="$(printf '%s' "$BODY" | curl -sS -o /dev/null -w '%{http_code}' -X POST \
  "http://127.0.0.1:${API_PORT:-8000}/api/admin/users/reset-password" \
  -H "@$HEADER_FILE" -H 'Content-Type: application/json' --data-binary @-)" || STATUS=000

case "$STATUS" in
  204) echo "password reset for $EMAIL; all of its sessions were ended" ;;
  404) echo "no such user (or NEWSDOCK_ADMIN_TOKEN is not set on the running api)" >&2; exit 1 ;;
  422) echo "the email or the password was rejected by the policy (length 10 to 128)" >&2; exit 1 ;;
  401|403) echo "the admin token was rejected: check NEWSDOCK_ADMIN_TOKEN in .env matches the api's" >&2; exit 1 ;;
  000) echo "cannot reach the api on port ${API_PORT:-8000}: is it running?" >&2; exit 1 ;;
  *) echo "unexpected answer from the api: HTTP $STATUS" >&2; exit 1 ;;
esac
