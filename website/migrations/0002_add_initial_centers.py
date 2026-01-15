from django.db import migrations

CITIES = [
    ("Ouidah", "Bénin"),
    ("Abomey", "Bénin"),
    ("Cotonou", "Bénin"),
    ("Toffo", "Bénin"),
    ("Parakou", "Bénin"),
]

def create_centers(apps, schema_editor):
    Center = apps.get_model('website', 'Center')
    for city, country in CITIES:
        name = f"Centre EEJ {city}"
        if not Center.objects.filter(name=name, city=city).exists():
            Center.objects.create(name=name, city=city, address='', contact='')

def reverse_centers(apps, schema_editor):
    Center = apps.get_model('website', 'Center')
    for city, _ in CITIES:
        name = f"Centre EEJ {city}"
        Center.objects.filter(name=name, city=city).delete()

class Migration(migrations.Migration):
    dependencies = [
        ('website', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_centers, reverse_centers),
    ]
