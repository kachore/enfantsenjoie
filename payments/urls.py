from django.urls import path
from . import views

app_name = 'payments'

urlpatterns = [
    path('paiement/demarrer/', views.start_checkout, name='start'),
    path('paiement/succes/', views.success, name='success'),
    path('paiement/annule/', views.cancel, name='cancel'),
    path('webhooks/fedapay/', views.webhook, name='webhook'),
    path('dashboard/donations/', views.donations_list, name='donations_list'),
    path('dashboard/fedapay-debug/', views.fedapay_debug, name='fedapay_debug'),
]
