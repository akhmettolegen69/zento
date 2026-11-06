from django.urls import path

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('explore/', views.explore, name='explore'),
    path('s/<slug:slug>/', views.store_profile, name='store'),
    path('s/<slug:slug>/follow/', views.follow_toggle, name='follow'),
    path('product/<int:pk>/', views.product_detail, name='product'),
    path('lang/<str:code>/', views.set_language, name='set_language'),
    path('cart/', views.cart_view, name='cart'),
    path('cart/<str:action>/<int:pk>/', views.cart_action, name='cart_action'),
    path('checkout/', views.checkout, name='checkout'),
    path('pay/mock/<int:pk>/', views.mock_pay, name='mock_pay'),
    path('pay/callback/', views.payment_callback, name='payment_callback'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('account/', views.account, name='account'),
    path('order/<int:pk>/', views.order_done, name='order_done'),
]
