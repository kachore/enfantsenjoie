from django.shortcuts import render, get_object_or_404, redirect
from .models import NewsItem, Center, ContactMessage, Category, ImpactMetrics
from .forms import ContactForm
from django.db.models import Q
from django.contrib import messages
from django.core.mail import send_mail, EmailMultiAlternatives
from django.conf import settings
from django.utils import timezone
from django.utils.text import slugify
from pathlib import Path
import os
from django.db.models.functions import Coalesce


def home(request):
    # Listes séparées pour les sections plus bas
    posts = NewsItem.objects.filter(status='published', type='post').prefetch_related('media')[:3]
    events = NewsItem.objects.filter(status='published', type='event').prefetch_related('media').order_by('event_start', 'date_event')[:3]

    # À la une: mélange posts + événements, triés par date pertinente (event_start → date_event → created)
    highlights = (
        NewsItem.objects.filter(status='published')
        .annotate(sort_date=Coalesce('event_start', 'date_event', 'created'))
        .order_by('-sort_date')
        .prefetch_related('media')[:6]
    )

    return render(request, 'website/home.html', {
        'posts': posts,
        'events': events,
        'highlights': highlights,
    })


def about(request):
    centers = Center.objects.all()
    events = NewsItem.objects.filter(type='event', status='published')
    metrics = ImpactMetrics.objects.first()
    # Rassembler automatiquement les médias 3D du projet de siège depuis static/img/building
    def gather_building_gallery():
        images_ext = {'.jpg', '.jpeg', '.png', '.webp'}
        videos_ext = {'.mp4', '.webm', '.ogg', '.mov'}
        roots = []
        # Racine static principale de l'app
        roots.append(Path(settings.BASE_DIR) / 'eej_site' / 'static')
        # Dossiers static additionnels s'ils existent
        for p in getattr(settings, 'STATICFILES_DIRS', []):
            roots.append(Path(p))
        items = []
        seen = set()
        for root in roots:
            folder = root / 'img' / 'building'
            if not folder.exists():
                continue
            for entry in sorted(folder.iterdir()):
                if not entry.is_file():
                    continue
                ext = entry.suffix.lower()
                if ext in images_ext or ext in videos_ext:
                    rel = entry.relative_to(root).as_posix()  # ex: img/building/render1.jpg
                    if rel in seen:
                        continue
                    seen.add(rel)
                    items.append({
                        'type': 'image' if ext in images_ext else 'video',
                        'url': rel,
                    })
        return items

    building_gallery = gather_building_gallery()
    return render(request, 'website/about.html', {
        'centers': centers,
        'events': events,
        'metrics': metrics,
        'building_gallery': building_gallery,
    })


def posts_list(request):
    qs = NewsItem.objects.filter(status='published').prefetch_related('media')
    f = request.GET.get('f')  # 'upcoming' pour événements à venir uniquement
    t = request.GET.get('t')  # 'event' ou 'post' pour filtrer le type
    cat = request.GET.get('cat', '').strip()
    now = timezone.now()

    if t == 'event':
        qs = qs.filter(type='event')
    elif t == 'post':
        qs = qs.filter(type='post')

    if f == 'upcoming':
        # Événements à venir uniquement (non démarrés)
        qs = qs.filter(type='event').filter(
            (Q(event_start__isnull=False) & Q(event_start__gte=now)) |
            (Q(event_start__isnull=True) & Q(date_event__gte=now))
        )
    # Filtre catégorie par slug
    active_category = ''
    active_category_slug = ''
    active_category_obj = None
    if cat:
        active_category_obj = Category.objects.filter(slug=cat).first()
        if not active_category_obj:
            # Fallback: support des anciens liens par nom exact (insensible à la casse)
            active_category_obj = Category.objects.filter(name__iexact=cat).first()
            # Backfill slug si manquant
            if active_category_obj and not active_category_obj.slug:
                try:
                    active_category_obj.save(update_fields=None)  # déclenche la génération du slug
                except Exception:
                    pass
        if not active_category_obj:
            # Fallback 2: comparer slugify(name) au paramètre reçu (ex: "Éducation & Tech" -> "education-tech")
            try:
                for cobj in Category.objects.all():
                    if slugify(cobj.name) == cat:
                        active_category_obj = cobj
                        if not active_category_obj.slug:
                            try:
                                active_category_obj.save(update_fields=None)
                            except Exception:
                                pass
                        break
            except Exception:
                pass
        if active_category_obj:
            qs = qs.filter(category=active_category_obj)
            active_category = active_category_obj.name
            active_category_slug = active_category_obj.slug or ''
    items = []
    for obj in qs:
        if obj.type == 'event':
            date_val = obj.event_start or obj.date_event or obj.created
            date_end = obj.event_end
            # Statut de l'événement
            status = None
            start = obj.event_start or obj.date_event
            end = obj.event_end
            if start and end:
                if now < start:
                    status = 'À venir'
                elif start <= now <= end:
                    status = 'En cours'
                else:
                    status = 'Terminé'
            elif start:
                status = 'À venir' if now < start else 'En cours'
        else:
            date_val = obj.created
            date_end = None
            status = None
        img_url = None
        media_type = None
        media_url = None
        if getattr(obj, 'image', None):
            try:
                if obj.image and hasattr(obj.image, 'url'):
                    img_url = obj.image.url
            except Exception:
                img_url = None
        # Fallback vers premier média si pas d'image principale
        if not img_url:
            try:
                m = obj.media.first()
            except Exception:
                m = None
            if m:
                try:
                    url = m.file.url
                except Exception:
                    url = None
                if url:
                    if m.media_type == 'image':
                        media_type = 'image'
                        media_url = url
                    elif m.media_type == 'video':
                        media_type = 'video'
                        media_url = url
        # Construire slides (image principale + médias image/vidéo)
        slides = []
        if img_url:
            slides.append({'type': 'image', 'url': img_url})
        try:
            for m in obj.media.all():
                try:
                    mu = m.file.url
                except Exception:
                    mu = None
                if not mu:
                    continue
                if m.media_type in ('image', 'video'):
                    slides.append({'type': m.media_type, 'url': mu})
        except Exception:
            pass

        items.append({
            'type': obj.type,
            'title': obj.title,
            'slug': obj.slug,
            'date': date_val,
            'date_end': date_end,
            'status': status,
            'location': obj.location if obj.type == 'event' and obj.location else '',
            'image': img_url,
            'media_type': media_type,
            'media_url': media_url,
            'slides': slides,
        })
    # Tri: si on filtre "à venir", on met par date croissante; sinon par date décroissante
    if f == 'upcoming':
        items.sort(key=lambda x: (x['date'] is None, x['date'] or now))
    else:
        items.sort(key=lambda x: x['date'], reverse=True)
    # Charger la liste des catégories "actives": celles qui ont au moins un contenu publié
    cat_qs = Category.objects.filter(newsitem__status='published')
    if t in ('event', 'post'):
        cat_qs = cat_qs.filter(newsitem__type=t)
    categories = list(cat_qs.distinct().order_by('name'))
    # S'assurer que chaque catégorie du menu possède un slug utilisable
    for c in categories:
        if not getattr(c, 'slug', None) and c.name:
            try:
                c.save(update_fields=None)
            except Exception:
                pass
    return render(request, 'website/posts_list.html', {
        'items': items,
        'active_filter': f or '',
        'active_type': t or '',
        'active_category': active_category,
        'active_category_slug': active_category_slug,
        'categories': categories,
    })


def post_detail(request, slug):
    item = get_object_or_404(NewsItem.objects.prefetch_related('media'), slug=slug, status='published')
    item_date = (item.event_start or item.date_event) if (item.type == 'event') else item.created
    # Calcul temps de lecture (200 wpm approximatif)
    word_count = 0
    if item.content:
        word_count = len(item.content.split())
    read_time = max(1, round(word_count / 200)) if word_count else 1
    # Contenus liés (même type ou mélange) - exclure courant
    related_qs = NewsItem.objects.filter(status='published').exclude(id=item.id)[:6]
    related = []
    for r in related_qs:
        date_val = (r.event_start or r.date_event) if r.type == 'event' else r.created
        related.append({
            'title': r.title,
            'slug': r.slug,
            'type': r.type,
            'date': date_val,
        })
    # Pagination prev/next
    prev_item = NewsItem.objects.filter(status='published', created__gt=item.created).order_by('created').first()
    next_item = NewsItem.objects.filter(status='published', created__lt=item.created).order_by('-created').first()

    # TOC parsing (simple regex for h2/h3)
    article_html = ''
    toc = []
    if item.content:
        raw = item.content
        # Si le contenu ne contient pas de balises h2/h3, article_html = linebreaks fallback
        import re
        heading_pattern = re.compile(r'<(h2|h3)>(.*?)</\1>', re.IGNORECASE | re.DOTALL)
        matches = list(heading_pattern.finditer(raw))
        if matches:
            # Inject id dans les balises
            def slugify_heading(text):
                s = re.sub(r'<.*?>', '', text)  # remove inner html
                s = re.sub(r'[^\w\- ]+', '', s).strip().lower().replace(' ', '-')
                return s[:60]
            new_html = raw
            offset = 0
            for m in matches:
                tag = m.group(1).lower()
                inner = m.group(2)
                hid = slugify_heading(inner)
                if not hid:
                    continue
                toc.append({'id': hid, 'text': re.sub(r'<.*?>', '', inner).strip(), 'level': int(tag[1])})
                original = m.group(0)
                replaced = f'<{tag} id="{hid}">{inner}</{tag}>'
                start = m.start() + offset
                end = m.end() + offset
                new_html = new_html[:start] + replaced + new_html[end:]
                offset += len(replaced) - len(original)
            article_html = new_html
        else:
            # Pas d'en-têtes html, fallback simple
            from django.utils.html import linebreaks
            article_html = linebreaks(item.content)
    # Préparer fallback média si pas d'image principale
    media_list = list(getattr(item, 'media').all()) if hasattr(item, 'media') else []
    primary_media = None
    if (not item.image) and media_list:
        primary_media = media_list[0]

    # Construire les slides pour carrousel (image principale + médias)
    slides = []
    if item.image:
        try:
            slides.append({'type': 'image', 'url': item.image.url, 'caption': ''})
        except Exception:
            pass
    for m in media_list:
        try:
            mu = m.file.url
        except Exception:
            mu = None
        if not mu:
            continue
        if m.media_type in ('image', 'video'):
            slides.append({'type': m.media_type, 'url': mu, 'caption': m.caption or ''})

    context = {
        'item': item,
        'item_date': item_date,
        'read_time': read_time,
        'related': related[:3],
        'prev_item': prev_item,
        'next_item': next_item,
        'article_html': article_html or None,
        'toc': toc,
        'media_list': media_list,
        'primary_media': primary_media,
        'slides': slides,
    }
    return render(request, 'website/post_detail.html', context)


def contact(request):
    if request.method == 'POST':
        form = ContactForm(request.POST)
        if form.is_valid():
            msg_obj = form.save()
            # Préparation emails
            subject_ack = "Accusé de réception - Enfants En Joie"
            user_email = form.cleaned_data.get('email')
            name = form.cleaned_data.get('name')
            plain_body = (
                f"Bonjour {name},\n\n"
                "Nous avons bien reçu votre message et vous remercions de votre intérêt. "
                "Notre équipe le traitera dans les meilleurs délais (24–48h).\n\n"
                "Récapitulatif :\n"
                f"Type: {msg_obj.get_request_type_display()}\n"
                f"Objet: {msg_obj.subject or '(aucun)'}\n"
                f"Message: {msg_obj.message[:400]}{'...' if len(msg_obj.message) > 400 else ''}\n\n"
                "Ceci est un envoi automatique, merci de ne pas répondre directement à cet email.\n\n"
                "Enfants En Joie"
            )
            preview = msg_obj.message[:400]
            preview_html = preview.replace('\n', '<br>')
            if len(msg_obj.message) > 400:
                preview_html += '...'
            html_body = (
                f"<p>Bonjour <strong>{name}</strong>,</p>"
                "<p>Nous avons bien reçu votre message et vous remercions de votre intérêt. "
                "Notre équipe le traitera dans les meilleurs délais (24–48h).</p>"
                "<p><strong>Récapitulatif :</strong><br>"
                f"Type : {msg_obj.get_request_type_display()}<br>"
                f"Objet : {msg_obj.subject or '(aucun)'}<br>"
                f"Message : {preview_html}</p>"
                "<p style='font-size:12px;color:#555'>Ceci est un envoi automatique, merci de ne pas répondre directement à cet email.</p>"
                "<p style='font-size:13px'>Enfants En Joie</p>"
            )
            try:
                if user_email:
                    email = EmailMultiAlternatives(
                        subject_ack,
                        plain_body,
                        getattr(settings, 'DEFAULT_FROM_EMAIL', 'no-reply@example.com'),
                        [user_email],
                        cc=['tfeinsti@gmail.com'],
                    )
                    email.attach_alternative(html_body, 'text/html')
                    email.send(fail_silently=True)
            except Exception:
                # Ne pas bloquer l'utilisateur si l'email échoue
                pass
            messages.success(request, "Message envoyé avec succès. Merci pour votre contact ! Un accusé vous a été envoyé.")
            return redirect('website:contact')
        else:
            messages.error(request, "Veuillez corriger les erreurs ci-dessous.")
    else:
        form = ContactForm()
    return render(request, 'website/contact.html', {'form': form})


def donate(request):
    metrics = ImpactMetrics.objects.first()
    return render(request, 'website/donate.html', {'metrics': metrics})


def search(request):
    query = request.GET.get('q', '').strip()
    results = []
    if query:
        qs = NewsItem.objects.filter(status='published').filter(
            Q(title__icontains=query) | Q(content__icontains=query) | Q(location__icontains=query)
        )
        for obj in qs:
            date_val = (obj.event_start or obj.date_event) if obj.type == 'event' else obj.created
            image_url = ''
            media_type = None
            media_url = None
            if obj.image:
                try:
                    # Utiliser .url si File/ImageField; fallback direct sinon
                    image_url = obj.image.url
                except Exception:
                    image_url = str(obj.image)
            if not image_url:
                try:
                    m = obj.media.first()
                except Exception:
                    m = None
                if m:
                    try:
                        mu = m.file.url
                    except Exception:
                        mu = None
                    if mu:
                        if m.media_type == 'image':
                            media_type = 'image'
                            media_url = mu
                        elif m.media_type == 'video':
                            media_type = 'video'
                            media_url = mu
            results.append({
                'type': obj.type,
                'title': obj.title,
                'slug': obj.slug,
                'date': date_val,
                'image': image_url,
                'media_type': media_type,
                'media_url': media_url,
            })
        results.sort(key=lambda x: x['date'], reverse=True)
    return render(request, 'website/search.html', {'query': query, 'results': results})


def gallery(request):
    """Galerie des images et vidéos alimentée par les GalleryCollection.
    Fallback: si aucune collection, on affiche les médias des NewsItem comme avant.
    GET params:
      - type=images|videos
      - page=N
    """
    from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
    from .models import GalleryCollection

    kind = (request.GET.get('type') or '').lower().strip()
    page = request.GET.get('page', '1')

    collections = GalleryCollection.objects.prefetch_related('medias').order_by('-created')
    flat = []
    if collections.exists():
        for coll in collections:
            for gm in coll.medias.all():
                try:
                    url = gm.file.url
                except Exception:
                    url = None
                if not url:
                    continue
                flat.append({
                    'title': coll.name,
                    'slug': None,  # Pas de page détail pour l'instant
                    'post_type': 'gallery',
                    'media_type': gm.media_type,
                    'url': url,
                    'caption': '',
                    'date': coll.created,
                })
    else:
        # Fallback sur NewsItem (ancienne logique réduite)
        qs = NewsItem.objects.filter(status='published').prefetch_related('media')
        for obj in qs:
            date_val = (obj.event_start or obj.date_event) if obj.type == 'event' else obj.created
            if obj.image:
                try:
                    flat.append({
                        'title': obj.title,
                        'slug': obj.slug,
                        'post_type': obj.type,
                        'media_type': 'image',
                        'url': obj.image.url,
                        'caption': '',
                        'date': date_val,
                    })
                except Exception:
                    pass
            try:
                for m in obj.media.all():
                    if m.media_type in ('image', 'video'):
                        try:
                            mu = m.file.url
                        except Exception:
                            mu = None
                        if not mu:
                            continue
                        flat.append({
                            'title': obj.title,
                            'slug': obj.slug,
                            'post_type': obj.type,
                            'media_type': m.media_type,
                            'url': mu,
                            'caption': m.caption or '',
                            'date': date_val,
                        })
            except Exception:
                pass

    # Filtrage type
    if kind in ('image', 'images'):
        flat = [x for x in flat if x['media_type'] == 'image']
        active_type = 'images'
    elif kind in ('video', 'videos'):
        flat = [x for x in flat if x['media_type'] == 'video']
        active_type = 'videos'
    else:
        active_type = 'all'

    flat.sort(key=lambda x: (x.get('date') is None, x.get('date')), reverse=True)

    paginator = Paginator(flat, 32)
    try:
        page_obj = paginator.page(page)
    except PageNotAnInteger:
        page_obj = paginator.page(1)
    except EmptyPage:
        page_obj = paginator.page(paginator.num_pages)

    context = {
        'media_list': list(page_obj.object_list),
        'page_obj': page_obj,
        'paginator': paginator,
        'active_type': active_type,
        'total_count': paginator.count,
    }
    return render(request, 'website/gallery.html', context)
