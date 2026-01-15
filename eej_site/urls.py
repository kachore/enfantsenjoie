from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/eej-dashboard/', RedirectView.as_view(url='/dashboard/', permanent=True)),
    path('eej-admin/', admin.site.urls),
    path('gestion/', RedirectView.as_view(url='/eej-admin/login/', permanent=False)),
    path('favicon.ico', RedirectView.as_view(url='/static/favicon.ico', permanent=True)),
    path('', include('payments.urls', namespace='payments')),
    path('', include('website.urls', namespace='website')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
