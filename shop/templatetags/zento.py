from decimal import Decimal

from django import template

from ..i18n import translate

register = template.Library()


@register.simple_tag(takes_context=True)
def t(context, text):
    return translate(text, context.get('lang', 'ru'))


@register.filter
def kzt(value):
    return f'{Decimal(value):,.0f}'.replace(',', ' ') + ' ₸'


@register.filter
def cny(value):
    return f'¥{Decimal(value):,.2f}'


_FORMS = {
    'product': {'en': ('product', 'products'), 'ru': ('товар', 'товара', 'товаров'), 'kk': ('тауар',)},
    'category': {'en': ('category', 'categories'), 'ru': ('категория', 'категории', 'категорий'),
                 'kk': ('санат',)},
}


@register.simple_tag(takes_context=True)
def plural(context, n, word):
    """Pluralise a known noun for the active language: {% plural 5 'product' %} -> 'товаров'."""
    forms = _FORMS[word][context.get('lang', 'ru')]
    n = int(n)
    if len(forms) == 1:
        return forms[0]
    if len(forms) == 2:
        return forms[0] if n == 1 else forms[1]
    if n % 10 == 1 and n % 100 != 11:
        return forms[0]
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return forms[1]
    return forms[2]


@register.simple_tag(takes_context=True)
def qs(context, **changes):
    """Current query string with some params replaced; empty values are dropped."""
    params = context['request'].GET.copy()
    for k, v in changes.items():
        params.pop(k, None)
        if v not in ('', None):
            params[k] = v
    return params.urlencode()


@register.simple_tag
def asset(path):
    """Static URL with a ?v=<mtime> suffix so browsers refetch CSS/JS after every change."""
    import os

    from django.contrib.staticfiles import finders
    from django.templatetags.static import static
    try:
        version = int(os.path.getmtime(finders.find(path)))
    except (TypeError, OSError):
        return static(path)
    return f'{static(path)}?v={version}'
