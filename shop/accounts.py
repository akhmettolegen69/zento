"""Username + password login on top of Django's default User.

Registration also collects a Kazakhstan phone (normalized to +7XXXXXXXXXX), stored on `Profile`.
"""
import re

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.validators import UnicodeUsernameValidator
from django.db import transaction

from .models import Profile

User = get_user_model()
BAD_PHONE = 'Enter a valid Kazakhstan phone number (+7 XXX XXX XX XX).'
PW_SHORT = {'min_length': 'Password must be at least 8 characters.'}


def normalize_phone(raw):
    """Return '+7XXXXXXXXXX' or None. Accepts 8…, 7…, +7… or bare 10 digits."""
    digits = re.sub(r'\D', '', raw or '')
    if len(digits) == 11 and digits[0] in '78':
        digits = digits[1:]
    if len(digits) != 10 or digits[0] != '7':  # KZ mobile/landline codes start with 7
        return None
    return '+7' + digits


class PhoneField(forms.CharField):
    def clean(self, value):
        value = super().clean(value)
        phone = normalize_phone(value)
        if not phone:
            raise forms.ValidationError(BAD_PHONE)
        return phone


class LoginForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(strip=False)

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request, self.user = request, None

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        self.user = authenticate(self.request, username=data['username'], password=data['password'])
        if self.user is None:
            raise forms.ValidationError('Invalid username or password.')
        return data


class RegisterForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150, validators=[UnicodeUsernameValidator()])
    phone = PhoneField()
    password = forms.CharField(strip=False, min_length=8, error_messages=PW_SHORT)
    password2 = forms.CharField(strip=False)

    def clean_username(self):
        username = self.cleaned_data['username']
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('This username is already taken.')
        return username

    def clean_phone(self):
        phone = self.cleaned_data['phone']
        if Profile.objects.filter(phone=phone).exists():
            raise forms.ValidationError('This phone number is already registered.')
        return phone

    def clean(self):
        data = super().clean()
        if data.get('password') and data.get('password') != data.get('password2'):
            self.add_error('password2', 'Passwords do not match.')
        return data

    def save(self):
        d = self.cleaned_data
        with transaction.atomic():
            user = User.objects.create_user(
                username=d['username'], password=d['password'],
                first_name=d['first_name'], last_name=d['last_name'])
            Profile.objects.create(user=user, phone=d['phone'])
        return user


class AccountForm(forms.Form):
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150)
    current_password = forms.CharField(strip=False, required=False)
    new_password = forms.CharField(strip=False, required=False, min_length=8, error_messages=PW_SHORT)

    def __init__(self, *args, user, **kwargs):
        self.user = user
        kwargs.setdefault('initial', {'first_name': user.first_name, 'last_name': user.last_name})
        super().__init__(*args, **kwargs)

    def clean(self):
        data = super().clean()
        if data.get('new_password') and not self.user.check_password(data.get('current_password') or ''):
            self.add_error('current_password', 'Current password is incorrect.')
        return data

    def save(self):
        d = self.cleaned_data
        self.user.first_name, self.user.last_name = d['first_name'], d['last_name']
        if d.get('new_password'):
            self.user.set_password(d['new_password'])
        self.user.save()
