#!/usr/bin/env bash
# Run as ubuntu from a clone at /home/ubuntu/Questbond.
set -euo pipefail
cd "$(dirname "$0")/../.."
if [[ "$PWD" != /home/ubuntu/Questbond || "$(id -un)" != ubuntu ]]; then
  echo 'Run as ubuntu from /home/ubuntu/Questbond on the Lightsail server.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip caddy
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
mkdir -p /home/ubuntu/mendigo-data
chmod 700 /home/ubuntu/mendigo-data
if [[ ! -f .env ]]; then
  cp deploy/lightsail/server.env.example .env
  chmod 600 .env
  echo 'Created .env. Edit its gateway key and staff passwords, then rerun this script.'
  exit 0
fi
chmod 600 .env
.venv/bin/python deploy/lightsail/check_config.py
if [[ ! -f /home/ubuntu/mendigo-data/mendigo.db ]]; then
  .venv/bin/python scripts/init_db.py
fi
sudo install -m 644 deploy/lightsail/mendigo.service /etc/systemd/system/mendigo.service
sudo systemctl daemon-reload
sudo systemctl enable mendigo
sudo systemctl restart mendigo
curl --fail --retry 10 --retry-connrefused --retry-delay 2 http://127.0.0.1:8501/_stcore/health
echo 'Mendigo is running privately. Configure HTTPS following docs/LIGHTSAIL.md.'
