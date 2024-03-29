# Generated by Django 4.1.4 on 2023-04-02 00:41

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('Import', '0003_alter_import_filename_alter_importcontext_editors'),
        ('Leaderboards', '0010_alter_session_source'),
    ]

    operations = [
        migrations.AlterField(
            model_name='game',
            name='source',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='games', to='Import.import', verbose_name='Source'),
        ),
    ]
