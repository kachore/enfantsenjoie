from django.urls import path
from . import views
from . import views_admin

app_name = 'website'

urlpatterns = [
    path('', views.home, name='home'),
    path('a-propos/', views.about, name='about'),
    path('galerie/', views.gallery, name='gallery'),
    path('actualites/', views.posts_list, name='posts_list'),
    path('actualites/<slug:slug>/', views.post_detail, name='post_detail'),
    path('contact/', views.contact, name='contact'),
    path('donner/', views.donate, name='donate'),
    path('recherche/', views.search, name='search'),
    # Dashboard custom staff : ne pas préfixer par 'admin/' pour éviter conflit avec admin.site
    path('dashboard/', views_admin.dashboard, name='admin_dashboard'),
]
