from .cart import Cart
from .models import Category, SiteSettings


def site(request):
    return {
        'cart_count': len(Cart(request)),
        'lang': getattr(request, 'lang', 'ru'),
        'nav_categories': Category.objects.all(),
        'rate': SiteSettings.load().kzt_to_cny,
    }
