from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.http import Http404, HttpResponseBadRequest
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .cart import Cart
from .models import Category, Order, OrderItem, Product, SiteSettings, Store, Story, kzt_to_cny
from .payments import get_provider


FEED_PAGE = 8
GRID_PAGE = 24


def _page(request, qs, per_page):
    return Paginator(qs, per_page).get_page(request.GET.get('page'))


def _is_fragment(request, target):
    return request.headers.get('HX-Request') and request.headers.get('HX-Target') == target


def _product_qs():
    return Product.objects.select_related('store', 'category').prefetch_related('photos')


def _filtered_products(request):
    qs = _product_qs().filter(store__active=True)
    p = request.GET
    if p.get('available', '1') == '1':
        qs = qs.filter(available=True)
    if p.get('category'):
        qs = qs.filter(category__slug=p['category'])
    if p.get('q'):
        qs = qs.filter(Q(name__icontains=p['q']) | Q(store__name__icontains=p['q']) |
                       Q(store__slug__icontains=p['q']))
    try:
        if p.get('max_price'):
            qs = qs.filter(price_kzt__lte=Decimal(p['max_price']))
    except InvalidOperation:
        pass
    if p.get('delivery', '').isdigit():
        qs = qs.filter(delivery_days_max__lte=int(p['delivery']))
    return qs


def feed_products():
    """Pinned products of active stores; stores with nothing pinned contribute their newest product."""
    latest = Product.objects.filter(store=OuterRef('pk')).order_by('-created_at').values('pk')[:1]
    fallback = (Store.objects.filter(active=True).exclude(products__pinned=True)
                .annotate(latest=Subquery(latest)).values('latest'))
    store_total = (Product.objects.filter(store=OuterRef('store')).order_by().values('store')
                   .annotate(c=Count('pk')).values('c'))
    return (_product_qs().filter(store__active=True).filter(Q(pinned=True) | Q(pk__in=fallback))
            .annotate(store_total=Subquery(store_total)))


def _stories():
    stories = list(Story.visible().filter(Q(store__isnull=True) | Q(store__active=True))
                   .select_related('product', 'store').prefetch_related('slides'))
    data = {}
    for s in stories:
        if s.product_id:
            link = reverse('product', args=[s.product_id])
        elif s.store_id:
            link = reverse('store', args=[s.store.slug])
        else:
            link = ''
        data[s.pk] = {
            'slides': [{'img': sl.image.url, 'caption': sl.caption} for sl in s.slides.all()]
                      or [{'img': s.cover.url, 'caption': s.title}],
            'link': link,
            'name': s.store.slug if s.store_id else s.title,
            'avatar': (s.store.logo.url if s.store_id and s.store.logo else s.cover.url),
        }
    return stories, data


def home(request):
    page = _page(request, feed_products(), FEED_PAGE)
    ctx = {'page': page}
    if _is_fragment(request, 'feed-more'):
        return render(request, 'shop/_posts.html', ctx)
    stories, story_data = _stories()
    ctx.update(stories=stories, story_data=story_data,
               suggested=Store.objects.filter(active=True).annotate(n=Count('products'))[:5])
    return render(request, 'shop/home.html', ctx)


def explore(request):
    q = request.GET.get('q', '').strip()
    ctx = {
        'categories': Category.objects.all(),
        'page': _page(request, _filtered_products(request), GRID_PAGE),
        'filters': request.GET,
        'q': q,
        'active_category': request.GET.get('category', ''),
        'available_only': request.GET.get('available', '1') == '1',
        'stores': (Store.objects.filter(active=True).filter(Q(name__icontains=q) | Q(slug__icontains=q))
                   .annotate(n=Count('products'))[:8] if q else []),
    }
    if _is_fragment(request, 'grid-more'):
        return render(request, 'shop/_grid.html', ctx)
    if _is_fragment(request, 'catalog'):
        return render(request, 'shop/_catalog.html', ctx)
    return render(request, 'shop/explore.html', ctx)


def store_profile(request, slug):
    store = get_object_or_404(Store, slug=slug, active=True)
    products = _product_qs().filter(store=store)
    highlights = Category.objects.filter(products__store=store).distinct()
    active_category = request.GET.get('category', '')
    if active_category:
        products = products.filter(category__slug=active_category)
    products = products.order_by('-pinned', '-created_at')
    ctx = {
        'store': store,
        'page': _page(request, products, GRID_PAGE),
        'highlights': highlights,
        'active_category': active_category,
        'product_count': store.products.count(),
        'available_count': store.products.filter(available=True).count(),
        'show_pins': True,
    }
    if _is_fragment(request, 'grid-more'):
        return render(request, 'shop/_grid.html', ctx)
    return render(request, 'shop/store.html', ctx)


def product_detail(request, pk):
    product = get_object_or_404(_product_qs(), pk=pk, store__active=True)
    more = (_product_qs().filter(store=product.store).exclude(pk=pk)
            .order_by('-pinned', '-created_at')[:6])
    return render(request, 'shop/product.html', {
        'product': product, 'more': more, 'product_count': product.store.products.count()})


def set_language(request, code):
    if code in dict(settings.LANGUAGES):
        request.session['lang'] = code
    return redirect(request.META.get('HTTP_REFERER') or 'home')


def _cart_ctx(request):
    cart = Cart(request)
    rows = cart.items()
    kzt, cny = cart.totals(rows)
    return {'rows': rows, 'total_kzt': kzt, 'total_cny': cny}


def cart_view(request):
    return render(request, 'shop/cart.html', _cart_ctx(request))


@require_POST
def cart_action(request, action, pk):
    cart = Cart(request)
    product = get_object_or_404(Product, pk=pk)
    if action == 'add':
        if not product.available:
            return HttpResponseBadRequest('unavailable')
        cart.add(pk)
    elif action == 'remove':
        cart.remove(pk)
    elif action in ('inc', 'dec'):
        cart.set(pk, cart.data.get(str(pk), 0) + (1 if action == 'inc' else -1))
    else:
        raise Http404
    if request.headers.get('HX-Request') and action != 'add':
        return render(request, 'shop/_cart_body.html', _cart_ctx(request))
    if request.headers.get('HX-Request'):
        resp = render(request, 'shop/_cart_added.html', {'cart_count': len(cart)})
        resp['HX-Trigger'] = 'cart-added'
        return resp
    return redirect(request.META.get('HTTP_REFERER') or 'cart')


def checkout(request):
    ctx = _cart_ctx(request)
    if not ctx['rows']:
        return redirect('cart')
    if request.method == 'POST':
        name, phone, address = (request.POST.get(k, '').strip() for k in ('name', 'phone', 'address'))
        if not (name and phone and address):
            ctx.update(error=True, form=request.POST)
            return render(request, 'shop/checkout.html', ctx)
        rate = SiteSettings.load().kzt_to_cny
        with transaction.atomic():
            order = Order.objects.create(
                name=name, phone=phone, address=address, rate=rate,
                total_kzt=ctx['total_kzt'], total_cny=kzt_to_cny(ctx['total_kzt'], rate))
            OrderItem.objects.bulk_create(
                OrderItem(order=order, product=r['product'], name=r['product'].name,
                          price_kzt=r['product'].price_kzt, quantity=r['qty'])
                for r in ctx['rows'])
        request.session['order_id'] = order.pk
        return redirect(get_provider().create_payment(request, order))
    return render(request, 'shop/checkout.html', ctx)


def mock_pay(request, pk):
    if settings.PAYMENT_PROVIDER != 'mock':
        raise Http404
    order = get_object_or_404(Order, pk=pk, status=Order.PENDING)
    return render(request, 'shop/mock_pay.html', {'order': order})


@require_POST
def payment_callback(request):
    try:
        order_id, paid, ref = get_provider().verify_callback(request)
    except ValueError:
        return HttpResponseBadRequest('bad callback')
    order = get_object_or_404(Order, pk=order_id)
    if order.status == Order.PENDING:
        order.status = Order.PAID if paid else Order.FAILED
        order.payment_ref = ref
        order.save(update_fields=['status', 'payment_ref'])
        if paid:
            Cart(request).clear()
    return redirect('order_done', pk=order.pk)


def order_done(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if request.session.get('order_id') != order.pk:
        raise Http404
    return render(request, 'shop/order_done.html', {'order': order})
