from django.contrib.auth.models import User
import tempfile
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Follow, Like, Order, OrderItem, Product, ProductImage, SiteSettings, Store, Story, kzt_to_cny

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
        r = self.client.post(reverse('account_edit'), {'first_name': 'Aidana', 'last_name': 'N',
                                                  'current_password': 'wrong', 'new_password': 'newpass123'})
        self.assertEqual(r.status_code, 200)
        r = self.client.post(reverse('account_edit'), {'first_name': 'Aidana', 'last_name': 'N',
                                                  'current_password': 'secret123', 'new_password': 'newpass123'})
        self.assertRedirects(r, reverse('account_edit'))
        u = User.objects.get()
        self.assertEqual(u.first_name, 'Aidana')
        self.assertTrue(u.check_password('newpass123'))
        self.assertEqual(self.client.get(reverse('account_edit')).status_code, 200)  # still logged in

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

    def titles(self, tab=''):
        url = reverse('home') + (f'?tab={tab}' if tab else '')
        return {s.title for s in self.client.get(url).context['stories']}

    def test_anonymous_sees_all_stories(self):
        self.assertEqual(self.titles(), {'story-a', 'story-b', 'sitewide'})

    def test_logged_in_for_you_all_following_only_followed(self):
        self.client.force_login(self.u)
        self.assertEqual(self.titles(), {'story-a', 'story-b', 'sitewide'})
        self.assertEqual(self.titles('following'), set())
        self.client.post(reverse('follow', args=['a']), HTTP_HX_REQUEST='true')
        self.assertEqual(self.titles('following'), {'story-a'})
        self.assertEqual(self.titles(), {'story-a', 'story-b', 'sitewide'})

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


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class LikeTests(TestCase):
    def setUp(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={'kzt_to_cny': Decimal('0.0145')})
        img = lambda: SimpleUploadedFile('a.gif', GIF, content_type='image/gif')
        self.store = Store.objects.create(name='A', slug='a')
        self.p = Product.objects.create(store=self.store, name='Lamp', image=img(), price_kzt=100, pinned=True)
        self.q = Product.objects.create(store=self.store, name='Mug', image=img(), price_kzt=50, pinned=True)
        self.u = User.objects.create_user('bob', password='pw12345678')
        self.u2 = User.objects.create_user('amy', password='pw12345678')

    def like(self, pk, **kw):
        return self.client.post(reverse('like', args=[pk]), HTTP_HX_REQUEST='true', **kw)

    def test_toggle_and_count(self):
        self.client.force_login(self.u)
        r = self.like(self.p.pk)
        self.assertContains(r, 'like-n')
        self.assertEqual(Like.objects.count(), 1)
        self.like(self.p.pk)
        self.assertEqual(Like.objects.count(), 0)

    def test_anonymous_redirected_to_login(self):
        r = self.like(self.p.pk, HTTP_HX_CURRENT_URL='http://testserver/')
        self.assertEqual(r.status_code, 204)
        self.assertIn('/login/?next=', r['HX-Redirect'])
        self.assertEqual(Like.objects.count(), 0)

    def test_count_is_total_across_users(self):
        Like.objects.create(user=self.u2, product=self.p)
        self.client.force_login(self.u)
        self.like(self.p.pk)
        r = self.client.get(reverse('home'))
        counts = {x.pk: x.like_count for x in r.context['page']}
        self.assertEqual(counts[self.p.pk], 2)
        self.assertEqual(counts[self.q.pk], 0)

    def test_liked_page_lists_only_own_likes(self):
        Like.objects.create(user=self.u, product=self.p)
        Like.objects.create(user=self.u2, product=self.q)
        self.client.force_login(self.u)
        names = [x.name for x in self.client.get(reverse('liked')).context['page']]
        self.assertEqual(names, ['Lamp'])

    def test_liked_page_requires_login_and_like_requires_post(self):
        self.assertEqual(self.client.get(reverse('liked')).status_code, 302)
        self.assertEqual(self.client.get(reverse('like', args=[self.p.pk])).status_code, 405)

    def test_product_page_renders(self):
        self.assertEqual(self.client.get(reverse('product', args=[self.p.pk])).status_code, 200)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class AccountAreaTests(TestCase):
    def setUp(self):
        SiteSettings.objects.update_or_create(pk=1, defaults={'kzt_to_cny': Decimal('0.0145'),
                                                              'support_url': 'https://wa.me/77001234567'})
        img = lambda: SimpleUploadedFile('a.gif', GIF, content_type='image/gif')
        self.store = Store.objects.create(name='A', slug='a')
        self.p = Product.objects.create(store=self.store, name='Lamp', image=img(), price_kzt=100, pinned=True)
        self.u = User.objects.create_user('bob', password='pw12345678', first_name='Bob', last_name='Lee')
        self.u2 = User.objects.create_user('amy', password='pw12345678')
        from .models import Profile
        Profile.objects.create(user=self.u, phone='+77010000001', company='Panda', city='Almaty')
        Profile.objects.create(user=self.u2, phone='+77010000002')

    def order(self, user, status=Order.PENDING, **kw):
        o = Order.objects.create(user=user, name='n', phone='1', address='x', status=status,
                                 total_kzt=200, total_cny=2, rate=Decimal('0.01'), **kw)
        OrderItem.objects.create(order=o, product=self.p, name='Lamp', price_kzt=100, quantity=2)
        return o

    def test_dashboard_counts_and_header(self):
        self.order(self.u); self.order(self.u); self.order(self.u, Order.IN_TRANSIT)
        self.order(self.u, Order.READY); self.order(self.u2, Order.READY)
        self.client.force_login(self.u)
        r = self.client.get(reverse('account'))
        self.assertEqual(dict(r.context['counts']), {'pending': 2, 'in_transit': 1, 'ready': 1})
        self.assertEqual(r.context['initials'], 'BL')
        self.assertContains(r, 'Panda')
        self.assertContains(r, 'wa.me/77001234567')
        self.assertEqual(r.context['latest'].pcs, 2)
        self.assertEqual(r.context['latest'].status, Order.READY)  # newest order, not oldest

    def test_dashboard_requires_login_and_works_without_profile(self):
        self.assertEqual(self.client.get(reverse('account')).status_code, 302)
        admin = User.objects.create_superuser('root', password='pw12345678')
        self.client.force_login(admin)
        self.assertEqual(self.client.get(reverse('account')).status_code, 200)
        self.assertEqual(self.client.get(reverse('account_edit')).status_code, 200)

    def test_orders_filter_and_isolation(self):
        a = self.order(self.u); self.order(self.u, Order.PAID); other = self.order(self.u2)
        self.client.force_login(self.u)
        self.assertEqual(len(self.client.get(reverse('orders')).context['page']), 2)
        r = self.client.get(reverse('orders') + '?status=pending')
        self.assertEqual([o.pk for o in r.context['page']], [a.pk])
        self.assertEqual(self.client.get(reverse('order_detail', args=[a.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('order_detail', args=[other.pk])).status_code, 404)

    def test_receipt_only_for_paid_own_orders(self):
        pend = self.order(self.u); paid = self.order(self.u, Order.PAID); other = self.order(self.u2, Order.PAID)
        self.client.force_login(self.u)
        self.assertEqual(self.client.get(reverse('receipt', args=[paid.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse('receipt', args=[pend.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('receipt', args=[other.pk])).status_code, 404)
        self.assertEqual([o.pk for o in self.client.get(reverse('payments')).context['page']], [paid.pk])

    def test_pay_pending_order(self):
        o = self.order(self.u)
        self.client.force_login(self.u)
        r = self.client.post(reverse('order_pay', args=[o.pk]))
        self.assertRedirects(r, reverse('mock_pay', args=[o.pk]), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse('order_pay', args=[o.pk])).status_code, 405)

    def test_checkout_links_order_to_user_and_prefills(self):
        from .models import Address
        Address.objects.create(user=self.u, label='Home', city='Almaty', address='Abay 1', is_default=True)
        self.client.force_login(self.u)
        self.client.post(reverse('cart_action', args=['add', self.p.pk]))
        r = self.client.get(reverse('checkout'))
        self.assertEqual(r.context['form']['address'], 'Almaty, Abay 1')
        self.client.post(reverse('checkout'), {'name': 'Bob', 'phone': '1', 'address': 'x'})
        self.assertEqual(Order.objects.get().user, self.u)

    def test_edit_profile_saves_company_city(self):
        self.client.force_login(self.u)
        self.client.post(reverse('account_edit'), {'first_name': 'Bob', 'last_name': 'Lee',
                                                   'company': 'New', 'city': 'Astana'})
        self.u.profile.refresh_from_db()
        self.assertEqual((self.u.profile.company, self.u.profile.city), ('New', 'Astana'))

    def test_register_stores_company_city(self):
        self.client.post(reverse('register'), {
            'first_name': 'A', 'last_name': 'B', 'username': 'zed', 'phone': '87019998877',
            'company': 'Co', 'city': 'Oral', 'password': 'secret123', 'password2': 'secret123'})
        self.assertEqual(User.objects.get(username='zed').profile.city, 'Oral')

    def test_addresses_crud_default_and_isolation(self):
        from .models import Address
        self.client.force_login(self.u)
        for label in ('Home', 'Office'):
            self.client.post(reverse('address_new'), {'label': label, 'city': 'Almaty', 'address': 'x'})
        a1, a2 = Address.objects.order_by('id')
        self.assertTrue(a1.is_default and not a2.is_default)  # first one becomes default
        self.client.post(reverse('address_edit', args=[a2.pk]),
                         {'label': 'Office', 'city': 'Almaty', 'address': 'y', 'is_default': 'on'})
        a1.refresh_from_db(); a2.refresh_from_db()
        self.assertTrue(a2.is_default and not a1.is_default)
        self.client.post(reverse('address_delete', args=[a2.pk]))  # deleting default promotes another
        a1.refresh_from_db()
        self.assertTrue(a1.is_default)
        foreign = Address.objects.create(user=self.u2, label='x', city='c', address='a')
        self.assertEqual(self.client.post(reverse('address_delete', args=[foreign.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse('address_edit', args=[foreign.pk])).status_code, 404)

    def test_following_and_other_pages_render(self):
        Follow.objects.create(user=self.u, store=self.store)
        self.client.force_login(self.u)
        self.assertEqual(list(self.client.get(reverse('following')).context['stores']), [self.store])
        for name in ('account_settings', 'addresses', 'address_new', 'liked'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class OrderTrackingTests(TestCase):
    def setUp(self):
        img = lambda: SimpleUploadedFile('a.gif', GIF, content_type='image/gif')
        self.store = Store.objects.create(name='A', slug='a')
        self.p = Product.objects.create(store=self.store, name='Lamp', image=img(), price_kzt=100)
        self.u = User.objects.create_user('bob', password='pw12345678')
        self.o = Order.objects.create(user=self.u, name='n', phone='1', address='x', status=Order.PAID,
                                      total_kzt=200, total_cny=2, rate=Decimal('0.01'))
        OrderItem.objects.create(order=self.o, product=self.p, name='Lamp', price_kzt=100, quantity=2)

    def test_status_changes_are_logged_once(self):
        self.assertEqual(list(self.o.events.values_list('status', flat=True)), ['paid'])
        self.o.save()  # no change -> no new event
        self.o.status = Order.IN_TRANSIT
        self.o.save()
        self.assertEqual(list(self.o.events.values_list('status', flat=True)), ['paid', 'in_transit'])

    def test_timeline_states(self):
        self.o.status = Order.IN_TRANSIT
        self.o.save()
        states = {s['key']: s['state'] for s in Order.objects.get(pk=self.o.pk).timeline}
        self.assertEqual(states['paid'], 'done')
        self.assertEqual(states['in_transit'], 'current')
        self.assertEqual(states['ready'], 'todo')

    def test_admin_action_and_detail_page(self):
        admin = User.objects.create_superuser('root', password='pw12345678')
        self.client.force_login(admin)
        r = self.client.post('/admin/shop/order/', {'action': 'mark_ready', '_selected_action': [self.o.pk]})
        self.assertEqual(r.status_code, 302)
        self.o.refresh_from_db()
        self.assertEqual(self.o.status, Order.READY)
        self.assertEqual(self.client.get(f'/admin/shop/order/{self.o.pk}/change/').status_code, 200)
        self.client.force_login(self.u)
        self.assertContains(self.client.get(reverse('order_detail', args=[self.o.pk])), 'st-ready')
        self.assertEqual(self.client.get(reverse('orders')).status_code, 200)

    def test_reorder_fills_cart(self):
        self.client.force_login(self.u)
        r = self.client.post(reverse('order_reorder', args=[self.o.pk]))
        self.assertRedirects(r, reverse('cart'))
        self.assertEqual(self.client.session['cart'][str(self.p.pk)], 2)
