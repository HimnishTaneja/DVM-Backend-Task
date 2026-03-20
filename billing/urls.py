from django.urls import path
from . import views

app_name = 'billing'

urlpatterns = [
    path('wallet/', views.wallet_view, name='wallet'),
    path('wallet/topup/', views.top_up, name='top_up'),
]
