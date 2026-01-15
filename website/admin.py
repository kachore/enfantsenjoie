from django.contrib import admin
from django import forms
from django.http import HttpResponse
import csv
from datetime import datetime
from .models import NewsItem, Center, ContactMessage, Category, NewsMedia, ImpactMetrics, GalleryCollection, GalleryMedia
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings
from pathlib import Path
import mimetypes
import shutil
import io
import zipfile


class NewsItemAdminForm(forms.ModelForm):
    class Meta:
        model = NewsItem
        fields = '__all__'
        help_texts = {
            'image': "Image de couverture affichée en premier dans les listes et en tête du carrousel. Ajoutez d'autres images/vidéos dans la section \"Médias\" ci-dessous.",
        }
        labels = {
            'image': 'Image de couverture',
        }
from django.utils import timezone


class RecentDateFilter(admin.SimpleListFilter):
    title = 'Période'
    parameter_name = 'periode'

    def lookups(self, request, model_admin):
        return [
            ('1d', 'Dernières 24h'),
            ('7d', '7 derniers jours'),
            ('30d', '30 derniers jours'),
        ]

    def queryset(self, request, queryset):
        value = self.value()
        if not value:
            return queryset
        now = timezone.now()
        if value == '1d':
            return queryset.filter(created__gte=now - timezone.timedelta(days=1))
        if value == '7d':
            return queryset.filter(created__gte=now - timezone.timedelta(days=7))
        if value == '30d':
            return queryset.filter(created__gte=now - timezone.timedelta(days=30))
        return queryset


@admin.register(NewsItem)
class NewsItemAdmin(admin.ModelAdmin):
    form = NewsItemAdminForm
    list_display = ('title', 'type', 'status', 'created', 'event_range')
    list_filter = ('type', 'status', 'created', 'event_start', 'event_end', 'category')
    search_fields = ('title', 'content', 'location')
    prepopulated_fields = {'slug': ('title',)}
    date_hierarchy = 'created'
    ordering = ('-created',)
    fieldsets = (
        (None, {'fields': ('title', 'slug', 'type', 'status', 'category')}),
        ('Contenu', {
            'fields': ('content', 'image'),
            'description': "Téléversez ici l'image de couverture. Pour plusieurs images ou des vidéos, utilisez le bloc \"Médias\" ci-dessous (ordre configurable)."
        }),
        ('Événement', {'fields': ('event_start', 'event_end', 'location')}),
        ('Meta', {'fields': ('created', 'updated')}),
    )
    readonly_fields = ('created', 'updated')

    class MediaInline(admin.TabularInline):
        model = NewsMedia
        extra = 1
        fields = ('file', 'media_type', 'caption', 'order')
        ordering = ('order', 'id')
        verbose_name = 'Média'
        verbose_name_plural = 'Médias'

    inlines = [MediaInline]

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        preset_type = request.GET.get('type')
        if preset_type in ('post', 'event'):
            initial['type'] = preset_type
        return initial

    def event_range(self, obj: NewsItem):
        # Affichage lisible de l'intervalle
        if obj.type != 'event':
            return '—'
        from django.utils import formats
        start = obj.event_start or obj.date_event
        end = obj.event_end
        if start and end:
            return f"{formats.date_format(start, 'DATETIME_FORMAT')} → {formats.date_format(end, 'DATETIME_FORMAT')}"
        if start:
            return formats.date_format(start, 'DATETIME_FORMAT')
        return '—'
    event_range.short_description = "Période"

class CenterAdmin(admin.ModelAdmin):
    list_display = ('name', 'city', 'contact')


class ContactAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'subject', 'created', 'handled')
    list_filter = ('handled', RecentDateFilter, 'created')
    search_fields = ('name', 'email', 'message')
    actions = ['exporter_messages_csv']

    def exporter_messages_csv(self, request, queryset):
        """Action admin: export des messages sélectionnés en CSV."""
        # Préparer réponse HTTP
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = f'attachment; filename="contact_messages_{timestamp}.csv"'
        writer = csv.writer(response, delimiter=';')
        # En-têtes
        writer.writerow([
            'ID', 'Nom', 'Email', 'Téléphone', 'Type de demande', 'Objet', 'Message', 'Créé le', 'Traité'
        ])
        for msg in queryset.select_related(None):
            writer.writerow([
                msg.id,
                msg.name,
                msg.email,
                msg.phone,
                msg.get_request_type_display(),
                msg.subject,
                msg.message.replace('\n', ' ').strip(),
                msg.created.strftime('%Y-%m-%d %H:%M:%S'),
                'oui' if msg.handled else 'non'
            ])
        return response
    exporter_messages_csv.short_description = 'Exporter en CSV les messages sélectionnés'


admin.site.register(Category)
admin.site.register(Center, CenterAdmin)
admin.site.register(ContactMessage, ContactAdmin)


@admin.register(ImpactMetrics)
class ImpactMetricsAdmin(admin.ModelAdmin):
    fieldsets = (
        (None, {
            'fields': ('jeunes_formes', 'sessions_sante', 'actions_environnement', 'zones_intervention'),
            'description': "Ces valeurs s'affichent sur les pages À propos et Soutenir. Vous pouvez saisir des formats comme 120+.",
        }),
    )

    def has_add_permission(self, request):
        # Option: limiter à un seul enregistrement
        if ImpactMetrics.objects.exists():
            return False
        return super().has_add_permission(request)


class GalleryMediaInline(admin.TabularInline):
    model = GalleryMedia
    extra = 0
    fields = ('file', 'media_type')
    readonly_fields = ('media_type',)
    verbose_name = 'Média'
    verbose_name_plural = 'Médias'


@admin.register(GalleryCollection)
class GalleryCollectionAdmin(admin.ModelAdmin):
    list_display = ('name', 'source_folder', 'slug', 'created', 'media_count')
    search_fields = ('name', 'source_folder')
    readonly_fields = ('slug',)
    inlines = [GalleryMediaInline]
    actions = ['importer_medias', 'exporter_zip', 'vider_medias']

    # Champ additionnel pour importer un dossier (upload multiple)
    class GalleryCollectionAdminForm(forms.ModelForm):
        # NOTE: Django FileInput ne supporte pas multiple nativement ici; on garde un seul zip.
        upload_zip = forms.FileField(
            label="Importer un ZIP de médias (images/vidéos)",
            required=False,
            help_text="Téléversez une archive .zip contenant les fichiers images et vidéos"
        )

        class Meta:
            model = GalleryCollection
            fields = ['name', 'source_folder']

    form = GalleryCollectionAdminForm

    def media_count(self, obj):
        return obj.medias.count()
    media_count.short_description = 'Médias'

    def importer_medias(self, request, queryset):
        total = 0
        for coll in queryset:
            total += coll.import_media() or 0
        self.message_user(request, f"Import terminé. {total} fichiers traités.")
    importer_medias.short_description = "Importer / Mettre à jour les médias depuis le dossier source"

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Traitement upload ZIP
        zip_file = request.FILES.get('upload_zip')
        if not zip_file:
            return
        import zipfile, io
        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_file.read()))
        except Exception:
            self.message_user(request, "Le fichier fourni n'est pas une archive ZIP valide", level='error')
            return
        dest_base = Path(settings.MEDIA_ROOT) / 'gallery' / obj.slug
        dest_base.mkdir(parents=True, exist_ok=True)
        created = 0
        for member in zf.namelist():
            if member.endswith('/'):
                continue
            filename = Path(member).name
            data = zf.read(member)
            guessed, _ = mimetypes.guess_type(filename)
            name_lower = filename.lower()
            if guessed and guessed.startswith('image/'):
                mtype = 'image'
            elif guessed and guessed.startswith('video/'):
                mtype = 'video'
            else:
                if name_lower.endswith(('.jpg', '.jpeg', '.png', '.webp', '.gif')):
                    mtype = 'image'
                elif name_lower.endswith(('.mp4', '.webm', '.ogg', '.ogv', '.mov')):
                    mtype = 'video'
                else:
                    continue
            rel_path = f"gallery/{obj.slug}/{filename}"
            if not default_storage.exists(rel_path):
                default_storage.save(rel_path, ContentFile(data))
            GalleryMedia.objects.get_or_create(
                collection=obj,
                file=rel_path,
                defaults={'media_type': mtype}
            )
            created += 1
        self.message_user(request, f"{created} fichiers extraits du ZIP importés")

    def exporter_zip(self, request, queryset):
        # N'autoriser l'export que d'une seule collection à la fois pour créer un ZIP propre
        if queryset.count() != 1:
            self.message_user(request, "Veuillez sélectionner exactement une collection pour exporter en ZIP.", level='error')
            return
        coll = queryset.first()
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for gm in coll.medias.all():
                name = getattr(gm.file, 'name', None) or str(gm.file)
                if not name:
                    continue
                try:
                    with default_storage.open(name, 'rb') as f:
                        data = f.read()
                        arcname = Path(name).name
                        zf.writestr(arcname, data)
                except Exception:
                    continue
        buffer.seek(0)
        resp = HttpResponse(buffer.getvalue(), content_type='application/zip')
        safe_slug = coll.slug or 'galerie'
        resp['Content-Disposition'] = f'attachment; filename="gallery_{safe_slug}.zip"'
        return resp
    exporter_zip.short_description = "Exporter en ZIP la collection sélectionnée"

    def vider_medias(self, request, queryset):
        removed_files = 0
        removed_entries = 0
        for coll in queryset:
            medias = list(coll.medias.all())
            for gm in medias:
                name = getattr(gm.file, 'name', None) or str(gm.file)
                if name and default_storage.exists(name):
                    try:
                        default_storage.delete(name)
                        removed_files += 1
                    except Exception:
                        pass
            removed_entries += len(medias)
            coll.medias.all().delete()
        self.message_user(request, f"Médias supprimés: {removed_entries} (fichiers supprimés: {removed_files}).")
    vider_medias.short_description = "Vider/retirer tous les médias des collections sélectionnées"
