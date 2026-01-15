from django import forms
from .models import ContactMessage


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ['name', 'email', 'phone', 'request_type', 'subject', 'message']
        widgets = {
            'message': forms.Textarea(attrs={'rows':4, 'placeholder': 'Décrivez votre demande ou idée...'}),
            'request_type': forms.Select(attrs={'class': 'form-select'}),
            'phone': forms.TextInput(attrs={'inputmode': 'tel', 'placeholder': 'Ex: +229 ...'}),
            'name': forms.TextInput(attrs={'placeholder': 'Nom complet'}),
            'email': forms.EmailInput(attrs={'placeholder': 'vous@exemple.com'}),
            'subject': forms.TextInput(attrs={'placeholder': 'Objet (facultatif)'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Style épuré sans icônes décoratives ni placeholders redondants
        icon_map = {
            'name': 'fa-user',
            'email': 'fa-at',
            'phone': 'fa-phone',
            'request_type': 'fa-tag',
            'subject': 'fa-lightbulb',
            'message': 'fa-message'
        }
        for field_name, field in self.fields.items():
            base_classes = 'contact-field'
            if field_name == 'request_type':
                existing = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = (existing + ' form-select ' + base_classes).strip()
            elif field_name == 'message':
                existing = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = (existing + ' form-control ' + base_classes + ' contact-message').strip()
            else:
                existing = field.widget.attrs.get('class', '')
                field.widget.attrs['class'] = (existing + ' form-control ' + base_classes).strip()

            # ARIA labels complémentaires
            if 'aria-label' not in field.widget.attrs:
                field.widget.attrs['aria-label'] = field.label
            # Data attrib pour icône (utilisé dans template wrap automatique si besoin futur)
            field.widget.attrs['data-icon'] = icon_map.get(field_name, '')

        # Ajuster longueur max message côté widget pour UX (non sécuritaire, purement UI)
        self.fields['message'].widget.attrs.setdefault('maxlength', '2000')
