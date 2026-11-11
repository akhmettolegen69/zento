from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.db import models
from django.utils import timezone


class SiteSettings(models.Model):
    """Singleton holding the KZT -> CNY exchange rate."""
    kzt_to_cny = models.DecimalField(
        'KZT → CNY rate', max_digits=12, decimal_places=6, default=Decimal('0.0145'),
        help_text='How many CNY one KZT is worth, e.g. 0.0145')
    support_url = models.URLField(
        'Support chat link', blank=True, help_text='WhatsApp / Telegram link, e.g. https://wa.me/77001234567')

    class Meta:
        verbose_name = 'Site settings'
        verbose_name_plural = 'Site settings'

    def __str__(self):
        return f'1 KZT = {self.kzt_to_cny} CNY'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


def kzt_to_cny(amount_kzt, rate=None):
    rate = rate if rate is not None else SiteSettings.load().kzt_to_cny
    return (Decimal(amount_kzt) * Decimal(rate)).quantize(Decimal('0.01'), ROUND_HALF_UP)


class Category(models.Model):
    name = models.CharField(max_length=80)
    slug = models.SlugField(unique=True)
    image = models.ImageField(upload_to='categories/', blank=True)
    color = models.CharField(max_length=7, default='#4C5BF5', help_text='Card colour, hex like #4C5BF5')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'name']
        verbose_name_plural = 'categories'

    def __str__(self):
        return self.name


class Store(models.Model):
    name = models.CharField(max_length=60)
    slug = models.SlugField(unique=True, help_text='Username shown as @username, e.g. zento')
    logo = models.ImageField(upload_to='stores/', blank=True)
    bio = models.TextField(blank=True)
    city = models.CharField(max_length=60, blank=True)
    verified = models.BooleanField(default=False, help_text='Show the blue check next to the username')
    position = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['position', 'name']

    def __str__(self):
        return self.name

    @property
    def initial(self):
        return (self.name[:1] or self.slug[:1]).upper()


class Product(models.Model):
    BADGES = [('', 'None'), ('new', 'New'), ('popular', 'Popular'), ('sale', 'Sale')]

    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name='products')
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    image = models.ImageField(upload_to='products/')
    category = models.ForeignKey(Category, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='products')
    price_kzt = models.DecimalField('price (KZT)', max_digits=12, decimal_places=0)
    available = models.BooleanField(default=True)
    delivery_days_min = models.PositiveSmallIntegerField('delivery from (days)', default=7)
    delivery_days_max = models.PositiveSmallIntegerField('delivery to (days)', default=14)
    badge = models.CharField(max_length=10, choices=BADGES, blank=True, default='')
    pinned = models.BooleanField(default=False, help_text='Pinned products appear in the main feed and first on the store page')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def price_cny(self):
        return kzt_to_cny(self.price_kzt)

    @property
    def delivery_range(self):
        if self.delivery_days_min == self.delivery_days_max:
            return str(self.delivery_days_min)
        return f'{self.delivery_days_min}–{self.delivery_days_max}'

    @property
    def gallery(self):
        """Main image followed by extra photos (uses prefetched `photos` when available)."""
        return [self.image] + [ph.image for ph in self.photos.all()]


class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='products/')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']


class Story(models.Model):
    title = models.CharField(max_length=40, help_text='Label under the circle')
    cover = models.ImageField(upload_to='stories/')
    store = models.ForeignKey(Store, null=True, blank=True, on_delete=models.CASCADE, related_name='stories',
                              help_text='Store whose avatar and name are shown on the story ring')
    product = models.ForeignKey(Product, null=True, blank=True, on_delete=models.SET_NULL,
                                help_text='Optional product this story links to')
    active = models.BooleanField(default=True)
    expires_at = models.DateTimeField(null=True, blank=True, help_text='Leave empty to never expire')
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', '-id']
        verbose_name_plural = 'stories'

    def __str__(self):
        return self.title

    @classmethod
    def visible(cls):
        now = timezone.now()
        return cls.objects.filter(active=True).filter(
            models.Q(expires_at__isnull=True) | models.Q(expires_at__gt=now))


class StorySlide(models.Model):
    story = models.ForeignKey(Story, on_delete=models.CASCADE, related_name='slides')
    image = models.ImageField(upload_to='stories/')
    caption = models.CharField(max_length=120, blank=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['position', 'id']


class Order(models.Model):
    PENDING, PAID, PURCHASED, CHINA_WH, IN_TRANSIT, LOCAL_WH, READY, DELIVERED, FAILED = (
        'pending', 'paid', 'purchased', 'china_warehouse', 'in_transit', 'local_warehouse',
        'ready', 'delivered', 'failed')
    # Tracking pipeline, in order. `paid` is shown to customers as "Order Confirmed".
    TRACK_STEPS = [(PAID, 'Order Confirmed'), (PURCHASED, 'Purchased from Supplier'),
                   (CHINA_WH, 'Arrived at China Warehouse'), (IN_TRANSIT, 'On the Way'),
                   (LOCAL_WH, 'Arrived at Local Warehouse'), (READY, 'Ready for Pickup'),
                   (DELIVERED, 'Delivered to Customer')]
    STATUSES = [(PENDING, 'Awaiting payment')] + TRACK_STEPS + [(FAILED, 'Failed')]
    PAID_STATUSES = tuple(k for k, _ in TRACK_STEPS)
    DONE_STATUSES = (DELIVERED, FAILED)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name='orders')
    est_delivery_from = models.DateField(null=True, blank=True)
    est_delivery_to = models.DateField(null=True, blank=True)

    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=32)
    address = models.TextField()
    status = models.CharField(max_length=20, choices=STATUSES, default=PENDING)
    total_kzt = models.DecimalField(max_digits=14, decimal_places=0)
    total_cny = models.DecimalField(max_digits=14, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=6)
    payment_ref = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Order #{self.pk}'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._orig_status = None if self._state.adding else self.status

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.status != self._orig_status:  # new order or status changed -> log it for the tracker
            OrderEvent.objects.create(order=self, status=self.status)
            self._orig_status = self.status

    @property
    def is_active(self):
        return self.status not in self.DONE_STATUSES

    @property
    def timeline(self):
        """Tracking steps with state done/current/todo and the date each was reached."""
        reached = {}
        for e in self.events.all():  # ordered oldest first; last one wins if a status was repeated
            reached[e.status] = e.created_at
        idx = next((i for i, (k, _) in enumerate(self.TRACK_STEPS) if k == self.status), -1)
        rows = []
        for i, (key, label) in enumerate(self.TRACK_STEPS):
            state = 'todo' if idx < 0 or i > idx else 'current' if i == idx else 'done'
            if state == 'current' and key == self.DELIVERED:
                state = 'done'
            rows.append({'key': key, 'label': label, 'state': state, 'date': reached.get(key) if state != 'todo' else None})
        return rows

    @property
    def thumb(self):
        """First product image; prefetch `items__product` to avoid N+1."""
        for it in self.items.all():
            if it.product_id and it.product.image:
                return it.product.image
        return None


class OrderEvent(models.Model):
    """When an order reached a status; shown as dates in the customer's tracking timeline."""
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='events')
    status = models.CharField(max_length=20, choices=Order.STATUSES)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['created_at', 'pk']

    def __str__(self):
        return f'{self.order} → {self.status}'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, null=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=150)
    price_kzt = models.DecimalField(max_digits=12, decimal_places=0)
    quantity = models.PositiveIntegerField()

    @property
    def subtotal_kzt(self):
        return self.price_kzt * self.quantity


class Profile(models.Model):
    """Phone number for a Django user. `phone` is normalized to +7XXXXXXXXXX."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    phone = models.CharField(max_length=12, unique=True)
    company = models.CharField(max_length=80, blank=True)
    city = models.CharField(max_length=60, blank=True)

    def __str__(self):
        return self.phone


class Follow(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='follows')
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name='follows')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'store'], name='unique_follow')]

    def __str__(self):
        return f'{self.user} → {self.store}'


class Like(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='likes')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='likes')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['user', 'product'], name='unique_like')]

    def __str__(self):
        return f'{self.user} ♥ {self.product}'


class Address(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='addresses')
    label = models.CharField(max_length=40, help_text='e.g. Home, Office')
    city = models.CharField(max_length=60)
    address = models.TextField()
    is_default = models.BooleanField(default=False)

    class Meta:
        ordering = ['-is_default', 'id']
        verbose_name_plural = 'addresses'

    def __str__(self):
        return f'{self.label}: {self.city}, {self.address}'

    @property
    def full(self):
        return f'{self.city}, {self.address}'
