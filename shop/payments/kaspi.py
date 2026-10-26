from .base import PaymentProvider


class KaspiProvider(PaymentProvider):
    """Placeholder for the real Kaspi Pay (or other KZ gateway) integration.

    Fill in once merchant credentials are available: create the payment on the gateway
    in create_payment() and verify the signature of the webhook in verify_callback().
    """

    def create_payment(self, request, order):
        raise NotImplementedError('Kaspi Pay is not configured yet')

    def verify_callback(self, request):
        raise NotImplementedError('Kaspi Pay is not configured yet')
