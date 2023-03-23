# Generated by Django 4.1.4 on 2023-03-11 09:25

from django.db import migrations, models
import django.db.models.deletion
import markdownfield.models


class Migration(migrations.Migration):

    dependencies = [
        ('Import', '0003_alter_import_filename_alter_importcontext_editors'),
        ('Leaderboards', '0007_location_visibility_location'),
    ]

    operations = [
        migrations.AddField(
            model_name='location',
            name='blur_radius',
            field=models.FloatField(blank=True, null=True, verbose_name='Radius of Uncertainy when Location is Hidden'),
        ),
        migrations.AlterField(
            model_name='event',
            name='notes',
            field=markdownfield.models.MarkdownField(blank=True, null=True, rendered_field='notes_rendered'),
        ),
        migrations.AlterField(
            model_name='game',
            name='notes',
            field=markdownfield.models.MarkdownField(blank=True, null=True, rendered_field='notes_rendered'),
        ),
        migrations.AlterField(
            model_name='league',
            name='notes',
            field=markdownfield.models.MarkdownField(blank=True, null=True, rendered_field='notes_rendered'),
        ),
        migrations.AlterField(
            model_name='location',
            name='notes',
            field=markdownfield.models.MarkdownField(blank=True, null=True, rendered_field='notes_rendered'),
        ),
        migrations.AlterField(
            model_name='location',
            name='source',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='locations', to='Import.import', verbose_name='Source'),
        ),
        migrations.AlterField(
            model_name='player',
            name='notes',
            field=markdownfield.models.MarkdownField(blank=True, null=True, rendered_field='notes_rendered'),
        ),
        migrations.AlterField(
            model_name='session',
            name='notes',
            field=markdownfield.models.MarkdownField(blank=True, null=True, rendered_field='notes_rendered'),
        ),
        migrations.AlterField(
            model_name='team',
            name='notes',
            field=markdownfield.models.MarkdownField(blank=True, null=True, rendered_field='notes_rendered'),
        ),
        migrations.AlterField(
            model_name='tourney',
            name='notes',
            field=markdownfield.models.MarkdownField(blank=True, null=True, rendered_field='notes_rendered'),
        ),
    ]