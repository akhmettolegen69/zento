from django.contrib.auth.models import User
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Follow, Order, Product, ProductImage, SiteSettings, Store, Story, kzt_to_cny

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


class AuthTests(TestCase):
    def reg(self, **kw):
        data = {'first_name': 'Aida', 'last_name': 'N', 'username': 'aida', 'phone': '8 701 123 45 67',
                'password': 'secret123', 'password2': 'secret123'}
        data.update(kw)
        return self.client.post(reverse('register'), data)

    def test_phone_normalization(self):
        from .accounts import normalize_phone
        for raw in ('87011234567', '+7 (701) 123-45-67', '7011234567', '77011234567'):
            self.assertEqual(normalize_phone(raw), '+77011234567')
        for raw in ('', '123', '+1 555 123 4567', '+77011234'):
            self.assertIsNone(normalize_phone(raw))

    def test_register_logs_in_and_stores_names(self):
        r = self.reg()
        self.assertRedirects(r, reverse('home'))
        u = User.objects.get(profile__phone='+77011234567')
        self.assertEqual((u.first_name, u.last_name), ('Aida', 'N'))
        self.assertEqual(self.client.get(reverse('account')).status_code, 200)

    def test_register_validation(self):
        self.reg()
        self.assertEqual(User.objects.count(), 1)
        self.reg(username='other', phone='+7 701 123 45 67')  # duplicate phone, different format
        self.reg(username='AIDA', phone='+77012223344')       # duplicate username (case-insensitive)
        self.reg(username='bad name', phone='+77012223344')   # invalid username
        self.reg(username='b', phone='123')                         # bad phone
        self.reg(username='c', phone='+77011111111', password2='x')  # mismatch
        self.reg(username='d', phone='+77011111111', first_name='')  # missing name
        self.assertEqual(User.objects.count(), 1)

    def test_login_logout(self):
        self.reg()
        self.client.post(reverse('logout'))
        self.assertEqual(self.client.get(reverse('account')).status_code, 302)
        bad = self.client.post(reverse('login'), {'username': 'aida', 'password': 'nope'})
        self.assertEqual(bad.status_code, 200)
        ok = self.client.post(reverse('login'), {'username': 'aida', 'password': 'secret123'})
        self.assertRedirects(ok, reverse('home'))

    def test_login_ignores_offsite_next(self):
        self.reg()
        self.client.post(reverse('logout'))
        r = self.client.post(reverse('login'), {'username': 'aida', 'password': 'secret123',
                                                'next': 'https://evil.example/'})
        self.assertRedirects(r, reverse('home'))

    def test_account_update_and_password_change(self):
        self.reg()
        r = self.client.post(reverse('account'), {'first_name': 'Aidana', 'last_name': 'N',
                                                  'current_password': 'wrong', 'new_password': 'newpass123'})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse('account'), {'first_name': 'Aidana', 'last_name': 'N',
                                                  'current_password': 'secret123', 'new_password': 'newpass123'})
        self.assertRedirects(r, reverse('account'))
        u = User.objects.get()
        self.assertEqual(u.first_name, 'Aidana')
        self.assertTrue(u.check_password('newpass123'))
        self.assertEqual(self.client.get(reverse('account')).status_code, 200)  # still logged in

    def test_logout_requires_post(self):
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class FollowTests(TestCase):
    def setUp(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={'kzt_to_cny': Decimal('0.0145')})
        img = lambda: SimpleUploadedFile('a.gif', GIF, content_type='image/gif')
        self.a = Store.objects.create(name='A', slug='a')
        self.b = Store.objects.create(name='B', slug='b')
        for st in (self.a, self.b):
            Story.objects.create(title=f'story-{st.slug}', cover=img(), store=st)
        Story.objects.create(title='sitewide', cover=img())
        self.u = User.objects.create_user('bob', password='pw12345678')

    def titles(self):
        return {s.title for s in self.client.get(reverse('home')).context['stories']}

    def test_anonymous_sees_all_stories(self):
        self.assertEqual(self.titles(), {'story-a', 'story-b', 'sitewide'})

    def test_logged_in_sees_only_followed(self):
        self.client.force_login(self.u)
        self.assertEqual(self.titles(), set())
        self.client.post(reverse('follow', args=['a']), HTTP_HX_REQUEST='true')
        self.assertEqual(self.titles(), {'story-a'})

    def test_toggle_follow_unfollow(self):
        self.client.force_login(self.u)
        r = self.client.post(reverse('follow', args=['a']), HTTP_HX_REQUEST='true')
        self.assertContains(r, ' on"')
        self.assertEqual(Follow.objects.count(), 1)
        r = self.client.post(reverse('follow', args=['a']), HTTP_HX_REQUEST='true')
        self.assertNotContains(r, ' on"')
        self.assertEqual(Follow.objects.count(), 0)

    def test_anonymous_follow_redirects_to_login(self):
        r = self.client.post(reverse('follow', args=['a']), HTTP_HX_REQUEST='true',
                             HTTP_HX_CURRENT_URL='http://testserver/s/a/')
        self.assertEqual(r.status_code, 204)
        self.assertIn('/login/?next=', r['HX-Redirect'])
        self.assertEqual(Follow.objects.count(), 0)

    def test_follow_requires_post_and_active_store(self):
        self.assertEqual(self.client.get(reverse('follow', args=['a'])).status_code, 405)
        Store.objects.filter(slug='b').update(active=False)
        self.client.force_login(self.u)
        self.assertEqual(self.client.post(reverse('follow', args=['b'])).status_code, 404)

    def test_follower_count_on_profile(self):
        Follow.objects.create(user=self.u, store=self.a)
        r = self.client.get(reverse('store', args=['a']))
        self.assertEqual(r.context['follower_count'], 1)
