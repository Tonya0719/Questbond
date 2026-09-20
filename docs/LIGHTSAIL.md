# Deploy Mendigo using the organizers' starter kit

Reference: https://github.com/kenken64/ShowMeYourAgent-Starter-Kit at commit bffda0d15c494abef9202cab8feb13e067a40d1d.

The kit specifies Lightsail in Singapore (ap-southeast-1), Ubuntu 24.04, and browser SSH. Its example plan has 4 GB RAM; confirm current price, eligibility and credit coverage in your account. Lightsail browser SSH avoids manually creating an EC2 key pair, but still requires Lightsail permissions. If access is denied, the organizer must enable it.

Mendigo already has its own agents and UI. OpenClaw, Hermes and their local proxies are optional examples in the starter kit, not prerequisites for this app. The kit's Copilot section documents the /v1 OpenAI-compatible gateway route used by Mendigo. The older /api/chat examples use X-API-Key and describe differing tool behavior; do not mix those protocols. Our /v1 Bearer connection has passed a live tool-calling workflow.

## 1. Create and connect

In Lightsail, create a Linux Ubuntu 24.04 instance in Singapore named mendigo-demo, with public IPv4. When running, select **Connect using SSH**. Use the ubuntu account. Attach a static IP in Networking. Permit TCP 80 and 443 for the website; keep port 8501 private. Preserve the SSH rule needed for Lightsail browser SSH.

## 2. Install

In browser SSH:

```bash
sudo apt-get update
sudo apt-get install -y git
git clone https://github.com/Tonya0719/Questbond.git /home/ubuntu/Questbond
cd /home/ubuntu/Questbond
bash deploy/lightsail/setup.sh
nano .env
```

The first setup creates a server-specific .env and stops. Fill in the gateway key and two different private staff passwords. Keep the production and database-path values. Save and rerun:

```bash
bash deploy/lightsail/setup.sh
.venv/bin/python scripts/test_agent_connection.py
```

The live test sends synthetic data and may consume gateway credits. The setup creates a seeded demo database only if no database exists; existing schedules are preserved. systemd keeps the app running after SSH closes and starts it at boot. The service loads .env through the app; no secret is stored in its unit file.

## 3. Publish over HTTPS

Point a domain/subdomain you control at the Lightsail static IPv4 using an A record. Only add an AAAA record if IPv6 is also configured correctly. Request an organizer-provided hostname if you have no domain.

```bash
sudo cp deploy/lightsail/Caddyfile.example /etc/caddy/Caddyfile
sudo nano /etc/caddy/Caddyfile
```

Replace mendigo.example.com with your actual hostname, then:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl enable caddy
sudo systemctl restart caddy
```

Open https://YOUR-HOSTNAME. Caddy handles certificates and proxies Streamlit WebSockets. DNS must resolve to this instance and ports 80/443 must be reachable. This configuration assumes a dedicated new instance; do not overwrite an existing site's Caddyfile.

## Updates and data

After committing and pushing changes to `main`, update the running server with one command:

```bash
cd /home/ubuntu/Questbond
bash deploy/lightsail/update.sh
```

The update script refuses a dirty server checkout, fetches and fast-forwards to `origin/main`, installs requirements, validates the production configuration, and runs the test suite with the mock model so deployment does not consume gateway credits. It restarts `mendigo.service` only after those checks pass, then verifies the private health endpoint and reports the public HTTPS result. If the service configuration or initial server packages need to be installed, use `bash deploy/lightsail/setup.sh` instead.

Data is stored at /home/ubuntu/mendigo-data/mendigo.db, outside the code checkout. Never run reset_db.py on a deployed database. Before updates, take a Lightsail snapshot while the app is stopped for a consistent database copy; retain backups separately before deleting an instance. Stop/start preserves disk data, but deleting the instance requires a retained backup to recover it. Gateway usage and Lightsail charges are separate; confirm which credits apply.

Check health with `curl --fail http://127.0.0.1:8501/_stcore/health` and service status with `sudo systemctl status mendigo --no-pager`. Review errors with `sudo journalctl -u mendigo -n 50 --no-pager`; do not share secrets or customer records from logs. The starter kit mentions WAF body-size failures: if small calls pass but full agent calls return 403, report the request-size behavior to the gateway administrator. Do not disable gateway security controls yourself.

This remains a hackathon demo with shared staff passwords and public request intake, not per-user production authentication. Use synthetic data and a limited demo audience.

Sources: [starter kit](https://github.com/kenken64/ShowMeYourAgent-Starter-Kit), [Lightsail browser SSH](https://docs.aws.amazon.com/lightsail/latest/userguide/lightsail-how-to-connect-to-your-instance-virtual-private-server.html), [static IP](https://docs.aws.amazon.com/lightsail/latest/userguide/lightsail-create-static-ip.html), [Caddy HTTPS](https://caddyserver.com/docs/automatic-https).
