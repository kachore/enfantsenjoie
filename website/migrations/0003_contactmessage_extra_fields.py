from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ('website', '0002_add_initial_centers'),
    ]

    operations = [
        migrations.AddField(
            model_name='contactmessage',
            name='phone',
            field=models.CharField(verbose_name='Téléphone', max_length=30, blank=True),
        ),
        migrations.AddField(
            model_name='contactmessage',
            name='request_type',
            field=models.CharField(verbose_name='Type de demande', max_length=20, choices=[('info', 'Information'), ('partnership', 'Partenariat'), ('support', 'Soutien / Bénévolat'), ('urgent', 'Urgent')], default='info'),
        ),
    ]
