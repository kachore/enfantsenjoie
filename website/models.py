from django.db import models
import os
from django.utils.text import slugify
from django.urls import reverse
from django.utils import timezone
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile
import mimetypes
from django.conf import settings
from pathlib import Path
import shutil


class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=120, unique=True, blank=True, null=True, db_index=True)

    class Meta:
        verbose_name = 'Catégorie'
        verbose_name_plural = 'Catégories'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Génère un slug à partir du nom si absent
        if not self.slug and self.name:
            base = slugify(self.name)[:110]
            candidate = base
            i = 1
            while Category.objects.filter(slug=candidate).exclude(pk=self.pk).exists():
                candidate = f"{base}-{i}"[:120]
                i += 1
            self.slug = candidate
        super().save(*args, **kwargs)


class NewsItem(models.Model):
    TYPE_CHOICES = (
        ('post', 'Article'),
        ('event', 'Événement'),
    )
    STATUS_CHOICES = (
        ('draft', 'Brouillon'),
        ('published', 'Publié'),
    )

    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES, default='post')
    content = models.TextField(blank=True)
    date_event = models.DateTimeField(null=True, blank=True, help_text="Date/heure si type = Événement")
    # Nouveau: intervalle de date/heure pour les événements
    event_start = models.DateTimeField(null=True, blank=True, help_text="Début de l'événement (date & heure)")
    event_end = models.DateTimeField(null=True, blank=True, help_text="Fin de l'événement (date & heure)")
    location = models.CharField(max_length=200, blank=True)
    image = models.ImageField(upload_to='news/', blank=True, null=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='draft')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ('-created',)
        verbose_name = 'Publication'
        verbose_name_plural = 'Publications'

    def __str__(self):
        return f"[{self.get_type_display()}] {self.title}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title)[:200]
            slug_candidate = base_slug
            i = 1
            while NewsItem.objects.filter(slug=slug_candidate).exclude(pk=self.pk).exists():
                slug_candidate = f"{base_slug}-{i}"[:220]
                i += 1
            self.slug = slug_candidate
        # Clean event date if not an event
        if self.type != 'event':
            self.date_event = None
            self.event_start = None
            self.event_end = None
            self.location = ''
        else:
            # Synchroniser l'ancien champ (compatibilité) avec le nouveau champ de début
            # Si seul l'ancien champ est renseigné, l'utiliser comme début
            if not self.event_start and self.date_event:
                self.event_start = self.date_event
            # Si le nouveau champ est renseigné, refléter vers l'ancien pour compatibilité
            if self.event_start:
                self.date_event = self.event_start
        super().save(*args, **kwargs)

        # Post-save image optimization (only if image newly set or updated)
        if self.image and hasattr(self.image, 'path'):
            try:
                img_path = self.image.path
                with Image.open(img_path) as im:
                    im_format = im.format
                    # Largeur max augmentée pour meilleure netteté sur écrans haute densité et sections plein-largeur
                    max_width = 3200
                    if im.width > max_width:
                        ratio = max_width / float(im.width)
                        new_size = (max_width, int(im.height * ratio))
                        im = im.resize(new_size, Image.LANCZOS)
                    # Convert to RGB if JPEG candidate
                    save_format = 'JPEG'
                    # Légère hausse de la qualité JPEG pour réduire l'effet de flou/compression
                    save_kwargs = {'quality': 85, 'optimize': True, 'progressive': True}
                    if im_format and im_format.upper() in ('PNG', 'WEBP'):
                        # Conserver PNG si transparence détectée
                        if im.mode in ('RGBA', 'LA') or (im.mode == 'P' and 'transparency' in im.info):
                            save_format = im_format.upper()
                            if save_format == 'PNG':
                                save_kwargs = {'optimize': True}
                        else:
                            if im.mode != 'RGB':
                                im = im.convert('RGB')
                    else:
                        if im.mode != 'RGB':
                            im = im.convert('RGB')
                    buffer = BytesIO()
                    im.save(buffer, save_format, **save_kwargs)
                    file_basename = self.image.name.rsplit('.', 1)[0]
                    new_ext = save_format.lower()
                    new_name = f"{file_basename}.{new_ext}"
                    self.image.save(new_name, ContentFile(buffer.getvalue()), save=False)
                    super().save(update_fields=['image'])

                    # Génération de variantes responsives (srcset) si image suffisamment large
                    try:
                        # Générer davantage de variantes pour les écrans rétina / grands écrans
                        variant_sizes = [800, 1200, 1600, 1920, 2560, 3200]
                        dir_name, base_filename = os.path.split(self.image.path)
                        root_no_ext = os.path.splitext(base_filename)[0]
                        # Recharger l'image optimisée (taille potentiellement modifiée)
                        with Image.open(self.image.path) as master:
                            for w in variant_sizes:
                                if master.width <= w:  # inutile d'upscaler
                                    continue
                                ratio_v = w / float(master.width)
                                target_size = (w, int(master.height * ratio_v))
                                variant = master.resize(target_size, Image.LANCZOS)
                                if variant.mode != 'RGB':
                                    variant = variant.convert('RGB')
                                v_buffer = BytesIO()
                                variant.save(v_buffer, 'JPEG', quality=78, optimize=True, progressive=True)
                                variant_name = f"{root_no_ext}_w{w}.jpg"
                                variant_path = os.path.join(dir_name, variant_name)
                                # Écrire seulement si non existant ou plus ancien (simple heuristique)
                                if not os.path.exists(variant_path):
                                    with open(variant_path, 'wb') as f_out:
                                        f_out.write(v_buffer.getvalue())
                    except Exception:
                        # Ne doit pas casser la sauvegarde principale
                        pass
            except Exception:
                # Silencieux : ne pas interrompre la sauvegarde si optimisation échoue
                pass

    def get_absolute_url(self):
        return reverse('website:post_detail', args=[self.slug])

    @property
    def date_for_order(self):
        if self.type == 'event':
            if self.event_start:
                return self.event_start
            if self.date_event:
                return self.date_event
        return self.created

    @property
    def is_future_event(self):
        if self.type != 'event':
            return False
        now = timezone.now()
        # Si une fin est définie, considérer futur si fin >= maintenant, sinon se baser sur le début
        if self.event_end:
            return self.event_end >= now
        if self.event_start:
            return self.event_start >= now
        if self.date_event:
            return self.date_event >= now
        return False

    def clean(self):
        # Validation cohérence des dates d'événement
        from django.core.exceptions import ValidationError
        if self.type == 'event' and self.event_start and self.event_end:
            if self.event_end < self.event_start:
                raise ValidationError({
                    'event_end': "La fin de l'événement doit être postérieure ou égale au début."
                })

    @property
    def event_status(self):
        """Retourne 'À venir', 'En cours', 'Terminé' ou None selon les dates d'un événement."""
        if self.type != 'event':
            return None
        now = timezone.now()
        start = self.event_start or self.date_event
        end = self.event_end
        if start and end:
            if now < start:
                return 'À venir'
            if start <= now <= end:
                return 'En cours'
            return 'Terminé'
        if start:
            return 'À venir' if now < start else 'En cours'
        if end:
            # Sans début connu, si fin passée on considère terminé
            return 'Terminé' if now > end else 'En cours'
        return None


class NewsMedia(models.Model):
    """Média associé à un NewsItem: image ou vidéo, multi-upload via admin inline."""
    MEDIA_CHOICES = (
        ('image', 'Image'),
        ('video', 'Vidéo'),
        ('file', 'Fichier'),
    )
    news_item = models.ForeignKey(NewsItem, on_delete=models.CASCADE, related_name='media')
    file = models.FileField(upload_to='news/media/')
    media_type = models.CharField(max_length=10, choices=MEDIA_CHOICES, default='file')
    caption = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0, help_text="Ordre d'affichage (0 en premier)")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('order', 'id')
        verbose_name = 'Média'
        verbose_name_plural = 'Médias'

    def __str__(self):
        return f"{self.get_media_type_display()} pour {self.news_item.title}"

    def save(self, *args, **kwargs):
        # Détecter le type de média à partir du mimetype/extension
        if self.file and (not self.media_type or self.media_type == 'file'):
            guessed, _ = mimetypes.guess_type(self.file.name)
            if guessed:
                if guessed.startswith('image/'):
                    self.media_type = 'image'
                elif guessed.startswith('video/'):
                    self.media_type = 'video'
                else:
                    self.media_type = 'file'
            else:
                # fallback par extension simple
                name = (self.file.name or '').lower()
                if name.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                    self.media_type = 'image'
                elif name.endswith(('.mp4', '.webm', '.ogg', '.ogv', '.mov')):
                    self.media_type = 'video'
                else:
                    self.media_type = 'file'
        super().save(*args, **kwargs)


class Center(models.Model):
    name = models.CharField(max_length=200)
    city = models.CharField(max_length=100)
    address = models.CharField(max_length=255, blank=True)
    contact = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return f"{self.name} ({self.city})"

    class Meta:
        verbose_name = 'Centre'
        verbose_name_plural = 'Centres'


class ContactMessage(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField("Téléphone", max_length=30, blank=True)
    subject = models.CharField(max_length=200, blank=True)
    REQUEST_TYPE_CHOICES = [
        ("info", "Information"),
        ("partnership", "Partenariat"),
        ("support", "Soutien / Bénévolat"),
        ("urgent", "Urgent"),
    ]
    request_type = models.CharField("Type de demande", max_length=20, choices=REQUEST_TYPE_CHOICES, default="info")
    message = models.TextField()
    created = models.DateTimeField(auto_now_add=True)
    handled = models.BooleanField(default=False)

    def __str__(self):
        return f"Message de {self.name} <{self.email}>"

    class Meta:
        verbose_name = 'Message de contact'
        verbose_name_plural = 'Messages de contact'


class ImpactMetrics(models.Model):
    """Métriques d'impact affichées sur les pages About et Donate.
    Utiliser des CharField pour permettre des formats comme "120+".
    """
    jeunes_formes = models.CharField("Jeunes formés", max_length=50, default="120+")
    sessions_sante = models.CharField("Sessions santé", max_length=50, default="35")
    actions_environnement = models.CharField("Actions environnement", max_length=50, default="18")
    zones_intervention = models.CharField("Zones d'intervention", max_length=50, default="5")

    class Meta:
        verbose_name = "Métriques d'impact"
        verbose_name_plural = "Métriques d'impact"

    def __str__(self):
        return "Métriques d'impact"


class GalleryCollection(models.Model):
    """Collection/Album Galerie importé depuis un dossier.
    Le nom de la collection sert de titre pour les médias affichés côté visiteur.
    """
    name = models.CharField("Nom de la collection", max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    # Dossier source relatif à MEDIA_ROOT/gallery_sources/ (sécurité)
    source_folder = models.CharField("Sous-dossier source", max_length=255, blank=True, help_text="(Optionnel) Sous-dossier de media/gallery_sources/ contenant images et vidéos")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Galerie'
        verbose_name_plural = 'Galeries'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Génère un slug unique
        if not self.slug and self.name:
            base = slugify(self.name)[:200]
            cand = base
            i = 1
            while GalleryCollection.objects.filter(slug=cand).exclude(pk=self.pk).exists():
                cand = f"{base}-{i}"[:220]
                i += 1
            self.slug = cand
        super().save(*args, **kwargs)

    def import_media(self):
        """Importer tous les fichiers image/vidéo du dossier source vers MEDIA_ROOT/gallery/<slug>/ et créer les entrées GalleryMedia."""
        images_ext = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
        videos_ext = {'.mp4', '.webm', '.ogg', '.ogv', '.mov'}
        base_src = Path(settings.MEDIA_ROOT) / 'gallery_sources'
        src = (base_src / self.source_folder).resolve()
        # Sécurité: src doit être sous base_src
        try:
            src.relative_to(base_src)
        except Exception:
            return 0
        if not src.exists() or not src.is_dir():
            return 0
        dest_base = Path(settings.MEDIA_ROOT) / 'gallery' / self.slug
        dest_base.mkdir(parents=True, exist_ok=True)
        created_count = 0
        for entry in sorted(src.iterdir()):
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            media_type = 'image' if ext in images_ext else ('video' if ext in videos_ext else None)
            if not media_type:
                continue
            # Copier vers destination
            dest_path = dest_base / entry.name
            try:
                if not dest_path.exists():
                    shutil.copy2(entry, dest_path)
                rel_path = dest_path.relative_to(Path(settings.MEDIA_ROOT)).as_posix()
                GalleryMedia.objects.get_or_create(
                    collection=self,
                    file=rel_path,
                    defaults={'media_type': media_type}
                )
                created_count += 1
            except Exception:
                # Continuer même si un fichier pose problème
                continue
        return created_count


class GalleryMedia(models.Model):
    MEDIA_CHOICES = (
        ('image', 'Image'),
        ('video', 'Vidéo'),
    )
    collection = models.ForeignKey(GalleryCollection, on_delete=models.CASCADE, related_name='medias')
    file = models.FileField(upload_to='gallery/%Y/%m/', blank=False)
    media_type = models.CharField(max_length=10, choices=MEDIA_CHOICES)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('id',)
        verbose_name = 'Média de galerie'
        verbose_name_plural = 'Médias de galerie'

    def __str__(self):
        return f"{self.get_media_type_display()} - {self.collection.name}"
