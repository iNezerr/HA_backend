# Generated by Django 4.2.20 on 2025-06-30 10:11

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0004_alter_document_processing_status'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='educationprofile',
            options={'ordering': ['-start_date']},
        ),
        migrations.AlterModelOptions(
            name='experienceprofile',
            options={'ordering': ['-start_date']},
        ),
        migrations.AlterModelOptions(
            name='projectsprofile',
            options={'ordering': ['-start_date']},
        ),
        migrations.AddField(
            model_name='educationprofile',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='educationprofile',
            name='is_currently_studying',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='experienceprofile',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='experienceprofile',
            name='is_currently_working',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='projectsprofile',
            name='created_at',
            field=models.DateTimeField(auto_now_add=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='projectsprofile',
            name='is_currently_working',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='recommendationpriority',
            name='additional_preferences',
            field=models.TextField(blank=True, help_text='Additional preferences for recommendations'),
        ),
        migrations.AlterField(
            model_name='educationprofile',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='educationprofile',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='education_profiles', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='experienceprofile',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='experienceprofile',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='experience_profiles', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name='projectsprofile',
            name='end_date',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='projectsprofile',
            name='user',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='project_profiles', to=settings.AUTH_USER_MODEL),
        ),
    ]
