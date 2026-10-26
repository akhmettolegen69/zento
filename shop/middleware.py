from django.conf import settings
from django.utils import translation


class LanguageMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        codes = [c for c, _ in settings.LANGUAGES]
        lang = request.session.get('lang')
        request.lang = lang if lang in codes else settings.LANGUAGE_CODE
        translation.activate(request.lang)
        return self.get_response(request)
