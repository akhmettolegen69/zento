import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Order, Product, SiteSettings, Story, kzt_to_cny

GIF = (b'GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ShopTests(TestCase):
    def setUp(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={'kzt_to_cny': Decimal('0.0145')})
        img = lambda: SimpleUploadedFile('a.gif', GIF, content_type='image/gif')
        self.p = Product.objects.create(name='Lamp', image=img(), price_kzt=10000)
        self.hidden = Product.objects.create(name='Gone', image=img(), price_kzt=500, available=False)

    def test_conversion(self):
        self.assertEqual(kzt_to_cny(10000), Decimal('145.00'))
        self.assertEqual(self.p.price_cny, Decimal('145.00'))

    def test_rate_change_updates_price(self):
        SiteSettings.objects.filter(pk=1).update(kzt_to_cny=Decimal('0.02'))
        self.assertEqual(Product.objects.get(pk=self.p.pk).price_cny, Decimal('200.00'))

    def test_catalog_hides_unavailable(self):
        r = self.client.get(reverse('home'))
        self.assertContains(r, 'Lamp')
        self.assertNotContains(r, 'Gone')
        self.assertContains(self.client.get(reverse('home') + '?available=0'), 'Gone')

    def test_cart_rejects_unavailable(self):
        r = self.client.post(reverse('cart_action', args=['add', self.hidden.pk]))
        self.assertEqual(r.status_code, 400)

    def test_story_expired_hidden(self):
        from datetime import timedelta
        from django.utils import timezone
        Story.objects.create(title='Old', cover=SimpleUploadedFile('s.gif', GIF), expires_at=timezone.now() - timedelta(hours=1))
        Story.objects.create(title='Fresh', cover=SimpleUploadedFile('s.gif', GIF))
        self.assertEqual([s.title for s in Story.visible()], ['Fresh'])

    def test_full_checkout_flow(self):
        self.client.post(reverse('cart_action', args=['add', self.p.pk]))
        self.client.post(reverse('cart_action', args=['inc', self.p.pk]))
        r = self.client.post(reverse('checkout'), {'name': 'A', 'phone': '1', 'address': 'X'})
        order = Order.objects.get()
        self.assertEqual(order.total_kzt, 20000)
        self.assertEqual(order.total_cny, Decimal('290.00'))
        self.assertEqual(order.status, Order.PENDING)
        self.assertRedirects(r, reverse('mock_pay', args=[order.pk]))
        self.client.post(reverse('payment_callback'), {'order': order.pk, 'result': 'paid'})
        order.refresh_from_db()
        self.assertEqual(order.status, Order.PAID)
        self.assertContains(self.client.get(reverse('order_done', args=[order.pk])), 'Заказ')
        self.assertContains(self.client.get(reverse('cart')), 'Корзина пуста')

    def test_checkout_validation(self):
        self.client.post(reverse('cart_action', args=['add', self.p.pk]))
        r = self.client.post(reverse('checkout'), {'name': 'A'})
        self.assertContains(r, 'Заполните')
        self.assertEqual(Order.objects.count(), 0)

    def test_language_switch(self):
        self.client.get(reverse('set_language', args=['en']))
        self.assertContains(self.client.get(reverse('home')), 'Add to cart')
