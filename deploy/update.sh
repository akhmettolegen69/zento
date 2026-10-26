#!/usr/bin/env bash
# Run on the server from /srv/zento to ship a new version
set -euo pipefail
git pull --ff-only
.venv/bin/pip install -r requirements.txt
set -a; . ./.env; set +a
.venv/bin/python manage.py migrate --noinput
.venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart zento
