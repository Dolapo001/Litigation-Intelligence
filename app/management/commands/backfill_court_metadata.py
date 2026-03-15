"""
Management command: backfill_court_metadata
============================================

Populates court_name, court_full_name, and court_citation on Filing records
that were created before those fields were added.

For each distinct court code found in the database the command fetches the
court resource from CourtListener once (identical to the in-poller cache),
then bulk-updates every Filing row that shares that court code.

Usage::

    python manage.py backfill_court_metadata            # dry-run
    python manage.py backfill_court_metadata --apply    # persist changes
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from app.ingestion.courtlistener import CourtListenerClient
from app.storage.models import Filing


class Command(BaseCommand):
    help = "Backfill court_name / court_full_name / court_citation for existing Filing records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Persist changes to the database (default: dry-run only).",
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        mode = "APPLY" if apply else "DRY-RUN"
        self.stdout.write(f"[{mode}] Backfilling court metadata…\n")

        client = CourtListenerClient(
            base_url=settings.COURTLISTENER_BASE_URL,
            api_token=settings.COURTLISTENER_API_TOKEN,
        )

        # Only process rows where all three metadata fields are still blank.
        qs = Filing.objects.filter(court_name="", court_full_name="", court_citation="")
        total = qs.count()
        self.stdout.write(f"  {total} filing(s) need backfilling.\n")

        if total == 0:
            self.stdout.write(self.style.SUCCESS("Nothing to do."))
            return

        # Collect distinct court codes so we hit the API at most once per code.
        court_codes = list(qs.values_list("court", flat=True).distinct())
        self.stdout.write(f"  Distinct court codes: {court_codes}\n")

        # Fetch metadata for each unique court code.
        court_meta: dict[str, dict] = {}
        for code in court_codes:
            meta = client.fetch_court(code)
            if meta:
                court_meta[code] = meta
                self.stdout.write(
                    f"  Fetched: {code!r} → {meta.get('full_name', '(no full_name)')}"
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"  Could not fetch metadata for court {code!r} — skipping those rows.")
                )

        # Apply updates grouped by court code.
        updated = 0
        for code, meta in court_meta.items():
            name = meta.get("short_name") or ""
            full_name = meta.get("full_name") or ""
            citation = meta.get("citation_string") or ""

            rows = qs.filter(court=code)
            count = rows.count()
            self.stdout.write(
                f"  [{code}] {count} row(s): "
                f"court_name={name!r}, court_full_name={full_name!r}, court_citation={citation!r}"
            )
            if apply:
                rows.update(
                    court_name=name,
                    court_full_name=full_name,
                    court_citation=citation,
                )
            updated += count

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(f"Done ({mode}). {updated} filing(s) {'updated' if apply else 'would be updated'}.")
        )
        if not apply:
            self.stdout.write(
                self.style.WARNING("Re-run with --apply to persist these changes.")
            )
