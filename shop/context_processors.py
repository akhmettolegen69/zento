from .cart import Cart
from .models import SiteSettings


def site(request):
    return {
        'cart_count': len(Cart(request)),
        'lang': getattr(request, 'lang', 'ru'),
        'rate': SiteSettings.load().kzt_to_cny,
    }
