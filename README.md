# Zento

Simple online store: Django + HTMX. Prices are stored in KZT; CNY is computed from a manual rate (Admin → Site settings).

```
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python manage.py migrate
.venv/bin/python manage.py createsuperuser
.venv/bin/python manage.py seed_demo      # optional placeholder data
.venv/bin/python manage.py runserver
```

- Storefront: http://127.0.0.1:8000/  ·  Admin: http://127.0.0.1:8000/admin/
- Products, categories, stories (with slides) and the exchange rate are managed in the admin.
- Languages: ru / kk / en (dictionary in `shop/i18n.py`, switcher in the header).
- Payments: `ZENTO_PAYMENT_PROVIDER=mock` (default, test page). Implement `shop/payments/kaspi.py` and set `kaspi` for a real gateway.
- Tests: `.venv/bin/python manage.py test`

## Deploy (Hostinger VPS, Ubuntu)

Config lives in `deploy/` (`env.example`, `zento.service`, `nginx.conf`, `update.sh`).

```
apt update && apt install -y python3-venv nginx git certbot python3-certbot-nginx
git clone https://github.com/akhmettolegen69/zento.git /srv/zento && cd /srv/zento
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
mkdir -p /srv/zento-data/media && chown -R www-data:www-data /srv/zento-data
cp deploy/env.example .env      # edit: secret key (python3 -c "import secrets;print(secrets.token_urlsafe(50))"), domain
set -a; . ./.env; set +a
.venv/bin/python manage.py migrate && .venv/bin/python manage.py collectstatic --noinput
.venv/bin/python manage.py createsuperuser
cp deploy/zento.service /etc/systemd/system/ && systemctl enable --now zento
cp deploy/nginx.conf /etc/nginx/sites-available/zento && ln -s /etc/nginx/sites-available/zento /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d example.com -d www.example.com
```

Updates: `cd /srv/zento && ./deploy/update.sh`. Back up `/srv/zento-data` (database + uploaded images).
