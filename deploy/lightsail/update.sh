#!/usr/bin/env bash
# Pull, validate, test and restart Mendigo on the Lightsail instance.
set -Eeuo pipefail

readonly APP_DIR="/home/ubuntu/Questbond"
readonly HEALTH_URL="http://127.0.0.1:8501/_stcore/health"
readonly PUBLIC_HEALTH_URL="https://mendigo.54-251-220-102.sslip.io/_stcore/health"

fail() {
  echo "Deployment stopped: $*" >&2
  exit 1
}

if [[ "$(id -un)" != "ubuntu" ]]; then
  fail "run this script as the ubuntu user"
fi

cd "$APP_DIR" || fail "cannot open $APP_DIR"

if [[ -n "$(git status --porcelain --untracked-files=normal)" ]]; then
  fail "the server checkout has local changes; review them before deploying"
fi

current_branch="$(git branch --show-current)"
[[ "$current_branch" == "main" ]] || fail "expected branch main, found ${current_branch:-detached HEAD}"

previous_commit="$(git rev-parse --short HEAD)"
echo "Fetching origin/main (currently $previous_commit)..."
git fetch origin main

if [[ "$(git rev-parse HEAD)" == "$(git rev-parse origin/main)" ]]; then
  echo "Code is already up to date. Checking the running service..."
  sudo systemctl is-active --quiet mendigo || fail "mendigo.service is not running"
  curl --fail --silent --show-error "$HEALTH_URL"
  echo
  echo "Mendigo is healthy; no deployment was needed."
  exit 0
fi

git merge --ff-only origin/main
new_commit="$(git rev-parse --short HEAD)"
echo "Updating Mendigo from $previous_commit to $new_commit..."

[[ -x .venv/bin/python ]] || fail "the server virtual environment is missing; run deploy/lightsail/setup.sh"
[[ -f .env ]] || fail "the server .env file is missing; run deploy/lightsail/setup.sh"

.venv/bin/python -m pip install --disable-pip-version-check -r requirements.txt
.venv/bin/python deploy/lightsail/check_config.py

echo "Running offline tests with the mock model..."
APP_ENV=test LLM_BACKEND=mock .venv/bin/python -m pytest -q

sudo install -m 644 deploy/lightsail/mendigo.service /etc/systemd/system/mendigo.service
sudo systemctl daemon-reload
sudo systemctl restart mendigo

echo "Waiting for Mendigo to become healthy..."
curl --fail --silent --show-error --retry 15 --retry-connrefused --retry-delay 2 "$HEALTH_URL"
echo

if curl --fail --silent --show-error --max-time 15 "$PUBLIC_HEALTH_URL" >/dev/null; then
  echo "Public HTTPS health check passed."
else
  echo "Warning: the private app is healthy, but the public HTTPS health check failed." >&2
  echo "Check Caddy and the Lightsail ports 80/443." >&2
fi

echo "Mendigo $new_commit deployed successfully."
