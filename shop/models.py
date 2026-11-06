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
    PENDING, PAID, IN_TRANSIT, READY, DELIVERED, FAILED = (
        'pending', 'paid', 'in_transit', 'ready', 'delivered', 'failed')
    STATUSES = [(PENDING, 'Awaiting payment'), (PAID, 'Paid'), (IN_TRANSIT, 'In transit'),
                (READY, 'Ready for pickup'), (DELIVERED, 'Delivered'), (FAILED, 'Failed')]
    PAID_STATUSES = (PAID, IN_TRANSIT, READY, DELIVERED)

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name='orders')
    est_delivery_from = models.DateField(null=True, blank=True)
    est_delivery_to = models.DateField(null=True, blank=True)

    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=32)
    address = models.TextField()
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING)
    total_kzt = models.DecimalField(max_digits=14, decimal_places=0)
    total_cny = models.DecimalField(max_digits=14, decimal_places=2)
    rate = models.DecimalField(max_digits=12, decimal_places=6)
    payment_ref = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'Order #{self.pk}'

    @property
    def thumb(self):
        """First product image; prefetch `items__product` to avoid N+1."""
        for it in self.items.all():
            if it.product_id and it.product.image:
                return it.product.image
        return None


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
