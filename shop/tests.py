import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Order, Product, ProductImage, SiteSettings, Store, Story, kzt_to_cny

GIF = (b'GIF87a\x01\x00\x01\x00\x80\x00\x00\x00\x00\x00\xff\xff\xff,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;')


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class ShopTests(TestCase):
    def setUp(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={'kzt_to_cny': Decimal('0.0145')})
        self.img = img = lambda: SimpleUploadedFile('a.gif', GIF, content_type='image/gif')
        self.store = Store.objects.create(name='Home Goods', slug='homegoods')
        self.p = Product.objects.create(store=self.store, name='Lamp', image=img(), price_kzt=10000, pinned=True)
        self.hidden = Product.objects.create(store=self.store, name='Gone', image=img(), price_kzt=500,
                                             available=False)

    def test_conversion(self):
        self.assertEqual(kzt_to_cny(10000), Decimal('145.00'))
        self.assertEqual(self.p.price_cny, Decimal('145.00'))

    def test_rate_change_updates_price(self):
        SiteSettings.objects.filter(pk=1).update(kzt_to_cny=Decimal('0.02'))
        self.assertEqual(Product.objects.get(pk=self.p.pk).price_cny, Decimal('200.00'))

    def test_explore_hides_unavailable(self):
        r = self.client.get(reverse('explore'))
        self.assertContains(r, 'Lamp')
        self.assertNotContains(r, 'Gone')
        self.assertContains(self.client.get(reverse('explore') + '?available=0'), 'Gone')

    def test_explore_search_finds_store(self):
        r = self.client.get(reverse('explore') + '?q=home')
        self.assertContains(r, reverse('store', args=['homegoods']))
        self.assertContains(r, 'Lamp')  # products of a matching store are found too

    def test_feed_shows_pinned_only(self):
        Product.objects.create(store=self.store, name='Chair', image=self.img(), price_kzt=1)
        r = self.client.get(reverse('home'))
        self.assertContains(r, 'Lamp')
        self.assertNotContains(r, 'Chair')
        self.assertContains(r, 'Все товары магазина (3)')

    def test_feed_falls_back_to_latest_when_nothing_pinned(self):
        other = Store.objects.create(name='Shoes', slug='shoes')
        Product.objects.create(store=other, name='Old boot', image=self.img(), price_kzt=1)
        Product.objects.create(store=other, name='New boot', image=self.img(), price_kzt=1)
        r = self.client.get(reverse('home'))
        self.assertContains(r, 'New boot')
        self.assertNotContains(r, 'Old boot')

    def test_feed_hides_inactive_stores(self):
        self.store.active = False
        self.store.save()
        self.assertNotContains(self.client.get(reverse('home')), 'Lamp')
        self.assertEqual(self.client.get(reverse('store', args=['homegoods'])).status_code, 404)
        self.assertEqual(self.client.get(reverse('product', args=[self.p.pk])).status_code, 404)

    def test_store_profile_lists_all_products_pinned_first(self):
        Product.objects.create(store=self.store, name='Chair', image=self.img(), price_kzt=1)
        r = self.client.get(reverse('store', args=['homegoods']))
        self.assertEqual([p.name for p in r.context['page']], ['Lamp', 'Chair', 'Gone'])
        self.assertContains(r, '<b>3</b> товара')

    def test_feed_infinite_scroll_fragment(self):
        for i in range(10):
            Product.objects.create(store=self.store, name=f'Pin {i}', image=self.img(), price_kzt=1, pinned=True)
        r = self.client.get(reverse('home'))
        self.assertContains(r, 'id="feed-more"')
        r = self.client.get(reverse('home') + '?page=2', HTTP_HX_REQUEST='true', HTTP_HX_TARGET='feed-more')
        self.assertTemplateUsed(r, 'shop/_posts.html')
        self.assertTemplateNotUsed(r, 'shop/base.html')

    def test_product_carousel_and_more_from_store(self):
        ProductImage.objects.create(product=self.p, image=self.img())
        Product.objects.create(store=self.store, name='Chair', image=self.img(), price_kzt=1)
        r = self.client.get(reverse('product', args=[self.p.pk]))
        self.assertEqual(len(r.context['product'].gallery), 2)
        self.assertContains(r, 'class="dots"')
        self.assertEqual([p.name for p in r.context['more']], ['Chair', 'Gone'])

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
        self.assertContains(self.client.get(reverse('product', args=[self.p.pk])), 'Add to cart')
