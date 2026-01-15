from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Redirection legacy de l'ancien chemin custom dashboard (doit précéder admin/)
    path('admin/eej-dashboard/', RedirectView.as_view(url='/dashboard/', permanent=True)),
    path('admin/', admin.site.urls),
    # Favicon direct (évite 404 si certain navigateur cherche /favicon.ico)
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.ico', permanent=True)),
    path('', include('payments.urls', namespace='payments')),
    path('', include('website.urls', namespace='website')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
