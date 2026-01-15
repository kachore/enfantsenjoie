from django import template
from django.conf import settings
from pathlib import Path
import os
from urllib.parse import urlparse

register = template.Library()

VARIANT_WIDTHS = [800, 1200, 1600, 1920, 2560, 3200]

def _variant_name(original_name: str, width: int) -> str:
    base, ext = os.path.splitext(original_name)
    # Normaliser extension en .jpg pour variantes (générées en JPEG dans save())
    return f"{base}_w{width}.jpg"

@register.simple_tag
def responsive_srcset(image_field):
    """Retourne une chaîne srcset valide.
    Accepte ImageFieldFile ou simple string (URL relative/absolue).
    Si variantes absentes → seulement l'original.
    """
    if not image_field:
        return ""
    media_root = Path(settings.MEDIA_ROOT)
    # Déterminer nom relatif et URL d'origine
    if hasattr(image_field, 'name') and hasattr(image_field, 'url'):
        rel_name = image_field.name
        original_url = image_field.url
    else:
        # image_field peut être une chaîne (ex: déjà it.image dans posts_list)
        original_url = str(image_field)
        parsed = urlparse(original_url)
        # Si c'est absolu et ne pointe pas sur MEDIA_URL -> retourner simplement l'URL
        if parsed.scheme and settings.MEDIA_URL not in original_url:
            return original_url
        # Construire nom relatif probable
        if settings.MEDIA_URL and original_url.startswith(settings.MEDIA_URL):
            rel_name = original_url[len(settings.MEDIA_URL):]
        else:
            rel_name = original_url.lstrip('/')
    parts = []
    for w in VARIANT_WIDTHS:
        variant_rel = _variant_name(rel_name, w)
        variant_fs = media_root / variant_rel
        if variant_fs.exists():
            parts.append(f"{settings.MEDIA_URL}{variant_rel} {w}w")
    parts.append(f"{original_url}")
    return ", ".join(parts)

@register.simple_tag
def responsive_sizes(default="(max-width: 575px) 100vw, (max-width: 991px) 50vw, 33vw"):
    return default
