"""Logged-in account area: dashboard, orders, receipts, favorites, follows, addresses, settings."""
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .accounts import AccountForm, AddressForm
from .models import Address, Order, Store
from .payments import get_provider


def _orders(user):
    # annotate() drops Meta.ordering, so order explicitly (newest first)
    return (user.orders.prefetch_related('items__product').annotate(pcs=Sum('items__quantity'))
            .order_by('-created_at', '-pk'))


def _initials(user):
    letters = (user.first_name[:1] + user.last_name[:1]) or user.username[:2]
    return letters.upper()


@login_required
def account(request):
    user = request.user
    orders = _orders(user)
    counts = user.orders.aggregate(
        pending=Count('pk', filter=Q(status=Order.PENDING)),
        in_transit=Count('pk', filter=Q(status=Order.IN_TRANSIT)),
        ready=Count('pk', filter=Q(status=Order.READY)))
    return render(request, 'shop/account.html', {
        'initials': _initials(user), 'profile': getattr(user, 'profile', None),
        'counts': counts, 'latest': orders.first()})


@login_required
def account_edit(request):
    form = AccountForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        update_session_auth_hash(request, request.user)
        messages.success(request, 'Saved.')
        return redirect('account_edit')
    return render(request, 'shop/account_edit.html', {'form': form})


@login_required
def account_settings(request):
    return render(request, 'shop/account_settings.html')


@login_required
def orders(request):
    status = request.GET.get('status', '')
    qs = _orders(request.user)
    if status in dict(Order.STATUSES):
        qs = qs.filter(status=status)
    page = Paginator(qs, 10).get_page(request.GET.get('page'))
    return render(request, 'shop/orders.html', {
        'page': page, 'status': status, 'statuses': Order.STATUSES})


@login_required
def order_detail(request, pk):
    order = get_object_or_404(_orders(request.user), pk=pk)
    return render(request, 'shop/order_detail.html', {'order': order})


@login_required
@require_POST
def order_pay(request, pk):
    order = get_object_or_404(request.user.orders, pk=pk, status=Order.PENDING)
    request.session['order_id'] = order.pk
    return redirect(get_provider().create_payment(request, order))


@login_required
def receipt(request, pk):
    order = get_object_or_404(request.user.orders.prefetch_related('items'), pk=pk,
                              status__in=Order.PAID_STATUSES)
    return render(request, 'shop/receipt.html', {'order': order})


@login_required
def payments(request):
    qs = _orders(request.user).filter(status__in=Order.PAID_STATUSES)
    page = Paginator(qs, 10).get_page(request.GET.get('page'))
    return render(request, 'shop/payments.html', {'page': page})


@login_required
def following(request):
    stores = (Store.objects.filter(active=True, follows__user=request.user)
              .annotate(n=Count('products', distinct=True)).order_by('-follows__created_at'))
    return render(request, 'shop/following.html', {'stores': stores})


@login_required
def addresses(request):
    return render(request, 'shop/addresses.html', {'addresses': request.user.addresses.all()})


@login_required
def address_form(request, pk=None):
    obj = get_object_or_404(Address, pk=pk, user=request.user) if pk else None
    form = AddressForm(request.POST or None, instance=obj, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('addresses')
    return render(request, 'shop/address_form.html', {'form': form, 'obj': obj})


@login_required
@require_POST
def address_delete(request, pk):
    obj = get_object_or_404(Address, pk=pk, user=request.user)
    was_default = obj.is_default
    obj.delete()
    if was_default:
        nxt = request.user.addresses.first()
        if nxt:
            nxt.is_default = True
            nxt.save(update_fields=['is_default'])
    return redirect('addresses')
