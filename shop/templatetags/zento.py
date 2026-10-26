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
