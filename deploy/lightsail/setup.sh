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

# Prevent Ubuntu's firmware updater from exhausting the smallest Lightsail
# plan. Firmware updates are not useful on a virtual server.
if ! swapon --show=NAME --noheadings | grep -qx '/swapfile'; then
  if [[ ! -f /swapfile ]]; then
    sudo fallocate -l 1G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
  fi
  sudo swapon /swapfile
fi
grep -qF '/swapfile none swap sw 0 0' /etc/fstab || \
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
sudo systemctl disable --now fwupd-refresh.timer fwupd.service 2>/dev/null || true
sudo systemctl mask fwupd-refresh.timer fwupd.service >/dev/null 2>&1 || true

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
