from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render
from django.utils import timezone
from django.db.models import Q
from .models import NewsItem, ContactMessage, Center


@staff_member_required
def dashboard(request):
    total_news = NewsItem.objects.count()
    published_news = NewsItem.objects.filter(status='published').count()
    now = timezone.now()
    # Un événement est futur si event_end >= now, sinon si event_start >= now, sinon si date_event >= now
    future_events = NewsItem.objects.filter(type='event', status='published').filter(
        (
            (Q(event_end__isnull=False) & Q(event_end__gte=now)) |
            (Q(event_end__isnull=True) & Q(event_start__isnull=False) & Q(event_start__gte=now)) |
            (Q(event_end__isnull=True) & Q(event_start__isnull=True) & Q(date_event__gte=now))
        )
    ).count()
    pending_messages = ContactMessage.objects.filter(handled=False).count()
    latest_news = NewsItem.objects.order_by('-created')[:5]
    centers_count = Center.objects.count()
    return render(request, 'admin/eej_dashboard.html', {
        'total_news': total_news,
        'published_news': published_news,
        'future_events': future_events,
        'pending_messages': pending_messages,
        'latest_news': latest_news,
        'centers_count': centers_count,
    })
