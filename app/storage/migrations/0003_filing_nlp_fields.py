from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Add NLP intelligence fields to Filing:
      - case_type + case_type_confidence  (Bloomberg Law-parity case tagging)
      - allegations, statutes, damages    (extracted legal entities, JSON)
      - risk_score, risk_breakdown        (1-10 litigation risk score)
      - predicted_outcome                 (plain-English outcome)
      - embedding_json                    (384-dim sentence embedding for similarity)
      - similar_cases_json                (top-k precedent matches, JSON)
      - processing_status                 (async pipeline state machine)
    """

    dependencies = [
        ("storage", "0002_filing_court_metadata"),
    ]

    operations = [
        # Case type classification
        migrations.AddField(
            model_name="filing",
            name="case_type",
            field=models.CharField(blank=True, db_index=True, max_length=128),
        ),
        migrations.AddField(
            model_name="filing",
            name="case_type_confidence",
            field=models.FloatField(blank=True, null=True),
        ),
        # Legal entity extraction
        migrations.AddField(
            model_name="filing",
            name="allegations",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="filing",
            name="statutes",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="filing",
            name="damages",
            field=models.TextField(blank=True),
        ),
        # Risk scoring
        migrations.AddField(
            model_name="filing",
            name="risk_score",
            field=models.IntegerField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="filing",
            name="risk_breakdown",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="filing",
            name="predicted_outcome",
            field=models.TextField(blank=True),
        ),
        # Precedent matching
        migrations.AddField(
            model_name="filing",
            name="embedding_json",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="filing",
            name="similar_cases_json",
            field=models.TextField(blank=True),
        ),
        # Pipeline state machine
        migrations.AddField(
            model_name="filing",
            name="processing_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("ocr_queued", "OCR Queued"),
                    ("processing", "Processing"),
                    ("complete", "Complete"),
                    ("error", "Error"),
                ],
                db_index=True,
                default="pending",
                max_length=16,
            ),
        ),
    ]
