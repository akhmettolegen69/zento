from django.urls import reverse

from .base import PaymentProvider


class MockProvider(PaymentProvider):
    """Fake gateway: redirects to a local page with Pay / Fail buttons."""

    def create_payment(self, request, order):
        return reverse('mock_pay', args=[order.pk])

    def verify_callback(self, request):
        try:
            return int(request.POST['order']), request.POST['result'] == 'paid', 'mock-%s' % request.POST['order']
        except (KeyError, ValueError):
            raise ValueError('bad callback')
