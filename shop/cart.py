from decimal import Decimal

from .models import Product, kzt_to_cny, SiteSettings

SESSION_KEY = 'cart'


class Cart:
    """Session cart: {product_id: quantity}."""

    def __init__(self, request):
        self.session = request.session
        self.data = self.session.setdefault(SESSION_KEY, {})

    def _save(self):
        self.session.modified = True

    def add(self, product_id, qty=1):
        k = str(product_id)
        self.data[k] = min(self.data.get(k, 0) + qty, 99)
        self._save()

    def set(self, product_id, qty):
        k = str(product_id)
        if qty <= 0:
            self.data.pop(k, None)
        else:
            self.data[k] = min(qty, 99)
        self._save()

    def remove(self, product_id):
        self.data.pop(str(product_id), None)
        self._save()

    def clear(self):
        self.session[SESSION_KEY] = {}
        self._save()

    def __len__(self):
        return sum(self.data.values())

    def items(self):
        products = Product.objects.filter(pk__in=self.data.keys(), available=True)
        rows = []
        for p in products:
            qty = self.data[str(p.pk)]
            rows.append({'product': p, 'qty': qty, 'subtotal_kzt': p.price_kzt * qty,
                         'subtotal_cny': kzt_to_cny(p.price_kzt * qty)})
        return rows

    def totals(self, rows=None):
        rows = self.items() if rows is None else rows
        kzt = sum((r['subtotal_kzt'] for r in rows), Decimal(0))
        return kzt, kzt_to_cny(kzt)
