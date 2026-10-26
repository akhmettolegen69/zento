class PaymentProvider:
    """Interface for payment gateways."""

    def create_payment(self, request, order):
        """Return a URL to redirect the customer to for paying `order`."""
        raise NotImplementedError

    def verify_callback(self, request):
        """Return (order_id, paid: bool, reference) from a gateway callback, or raise ValueError."""
        raise NotImplementedError
