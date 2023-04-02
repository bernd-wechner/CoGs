# Generated by Django 4.1.4 on 2023-03-19 06:30

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Import', '0003_alter_import_filename_alter_importcontext_editors'),
        ('Leaderboards', '0009_leaderboard_cache_alter_location_blur_radius'),
    ]

    operations = [
        migrations.AlterField(
            model_name='session',
            name='source',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='sessions', to='Import.import', verbose_name='Source'),
        ),
    ]
