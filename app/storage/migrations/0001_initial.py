from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Filing",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("docket_id", models.CharField(db_index=True, max_length=128, unique=True)),
                ("court", models.CharField(max_length=64)),
                ("case_name", models.CharField(max_length=512)),
                ("plaintiff", models.CharField(blank=True, max_length=256)),
                ("defendant", models.CharField(blank=True, max_length=256)),
                ("summary", models.TextField(blank=True)),
                ("pdf_path", models.CharField(blank=True, max_length=512)),
                ("date_filed", models.DateField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-created_at"], "verbose_name": "Filing", "verbose_name_plural": "Filings"},
        ),
        migrations.CreateModel(
            name="IngestionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("docket_id", models.CharField(db_index=True, max_length=128)),
                ("status", models.CharField(choices=[("success", "Success"), ("error", "Error"), ("skipped", "Skipped (duplicate)")], max_length=16)),
                ("message", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"ordering": ["-created_at"]},
        ),
    ]
