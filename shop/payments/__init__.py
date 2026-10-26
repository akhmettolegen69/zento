from django.conf import settings


def get_provider():
    if settings.PAYMENT_PROVIDER == 'kaspi':
        from .kaspi import KaspiProvider
        return KaspiProvider()
    from .mock import MockProvider
    return MockProvider()
