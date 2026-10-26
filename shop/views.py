from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.http import Http404, HttpResponseBadRequest
from django.urls import reverse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .cart import Cart
from .models import Category, Order, OrderItem, Product, SiteSettings, Story, kzt_to_cny
from .payments import get_provider


def _filtered_products(request):
    qs = Product.objects.select_related('category')
    p = request.GET
    if p.get('available', '1') == '1':
        qs = qs.filter(available=True)
    if p.get('category'):
        qs = qs.filter(category__slug=p['category'])
    if p.get('q'):
        qs = qs.filter(name__icontains=p['q'])
    try:
        if p.get('max_price'):
            qs = qs.filter(price_kzt__lte=Decimal(p['max_price']))
    except InvalidOperation:
        pass
    if p.get('delivery', '').isdigit():
        qs = qs.filter(delivery_days_max__lte=int(p['delivery']))
    return qs


def home(request):
    stories = list(Story.visible().select_related('product').prefetch_related('slides'))
    story_data = {s.pk: {
        'slides': [{'img': sl.image.url, 'caption': sl.caption} for sl in s.slides.all()]
                  or [{'img': s.cover.url, 'caption': s.title}],
        'link': reverse('product', args=[s.product_id]) if s.product_id else '',
    } for s in stories}
    ctx = {
        'stories': stories,
        'story_data': story_data,
        'categories': Category.objects.all(),
        'products': _filtered_products(request),
        'filters': request.GET,
        'active_category': request.GET.get('category', ''),
        'available_only': request.GET.get('available', '1') == '1',
    }
    if request.headers.get('HX-Request') and request.headers.get('HX-Target') == 'catalog':
        return render(request, 'shop/_catalog.html', ctx)
    return render(request, 'shop/home.html', ctx)


def product_detail(request, pk):
    return render(request, 'shop/product.html', {'product': get_object_or_404(Product, pk=pk)})


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
        return render(request, 'shop/_cart_badge.html', {'cart_count': len(cart)})
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
