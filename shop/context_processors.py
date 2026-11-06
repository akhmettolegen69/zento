from .cart import Cart
from .models import Follow, Like, SiteSettings


def site(request):
    user = getattr(request, 'user', None)
    followed = (set(Follow.objects.filter(user=user).values_list('store_id', flat=True))
                if user is not None and user.is_authenticated else set())
    liked = (set(Like.objects.filter(user=user).values_list('product_id', flat=True))
             if user is not None and user.is_authenticated else set())
    return {
        'cart_count': len(Cart(request)),
        'lang': getattr(request, 'lang', 'ru'),
        'rate': SiteSettings.load().kzt_to_cny,
        'followed_ids': followed,
        'liked_ids': liked,
    }
