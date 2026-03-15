from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("storage", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="filing",
            name="court_name",
            field=models.CharField(blank=True, max_length=256),
        ),
        migrations.AddField(
            model_name="filing",
            name="court_full_name",
            field=models.CharField(blank=True, max_length=512),
        ),
        migrations.AddField(
            model_name="filing",
            name="court_citation",
            field=models.CharField(blank=True, max_length=64),
        ),
    ]
