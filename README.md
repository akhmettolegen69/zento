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
