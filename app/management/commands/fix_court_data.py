"""
Management command: fix_court_data
====================================

Repairs historical Filing records that were persisted by older versions of the
poller before court-URL parsing and plaintiff/defendant fallback extraction were
implemented.

Two categories of records are fixed:

1. **Bad court codes** — any record whose `court` field looks like a full URL
   (contains "http") or is clearly a query-string artefact (e.g. "?format=json").
   The correct short code is extracted from the URL; when no code can be
   extracted (e.g. "?format=json" with no court segment), the value falls back
   to settings.TARGET_COURT.

2. **Missing plaintiff / defendant** — any record where one or both party names
   are blank is given a best-effort value derived from `case_name` by splitting
   on " v. ".

Usage::

    python manage.py fix_court_data            # dry-run (no writes)
    python manage.py fix_court_data --apply    # actually save changes
"""
from urllib.parse import urlparse

from django.conf import settings
from django.core.management.base import BaseCommand

from app.storage.models import Filing


def _extract_court_code(court_raw: str) -> str:
    """Return a cleaned court code from a raw value (URL or plain string)."""
    if not court_raw:
        return ""

    if "/courts/" in court_raw:
        path = urlparse(court_raw).path          # e.g. "/api/rest/v3/courts/dcd/"
        segments = [s for s in path.split("/") if s]
        try:
            idx = segments.index("courts")
            code = segments[idx + 1] if idx + 1 < len(segments) else ""
        except (ValueError, IndexError):
            code = ""
        return code

    # Strip any query-string fragment from a plain value.
    return court_raw.split("?")[0].strip()


def _is_bad_court(court: str) -> bool:
    """Return True when the court field does not look like a valid short code."""
    return "http" in court or court.startswith("?") or "/" in court


class Command(BaseCommand):
    help = "Fix corrupted court codes and missing plaintiff/defendant in Filing records."

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
        self.stdout.write(f"[{mode}] Scanning Filing records for data issues…\n")

        court_fixed = 0
        parties_fixed = 0

        for filing in Filing.objects.all().order_by("id"):
            changed = False

            # --- 1. Fix bad court codes ---
            if _is_bad_court(filing.court):
                new_court = _extract_court_code(filing.court)
                # Fall back to TARGET_COURT when the raw value carries no code
                # (e.g. "?format=json" — the URL contained no court segment).
                if not new_court:
                    new_court = settings.TARGET_COURT
                    self.stdout.write(
                        self.style.WARNING(
                            f"  [court]  id={filing.id} docket={filing.docket_id}: "
                            f"could not parse court from {filing.court!r} — "
                            f"falling back to TARGET_COURT={new_court!r}"
                        )
                    )
                if new_court != filing.court:
                    self.stdout.write(
                        f"  [court]  id={filing.id} docket={filing.docket_id}: "
                        f"{filing.court!r}  →  {new_court!r}"
                    )
                    if apply:
                        filing.court = new_court
                    court_fixed += 1
                    changed = True

            # --- 2. Fix missing plaintiff / defendant from case_name ---
            if (not filing.plaintiff or not filing.defendant) and " v. " in filing.case_name:
                parts = filing.case_name.split(" v. ", 1)
                new_p = parts[0].strip()
                new_d = parts[1].strip()

                if not filing.plaintiff and new_p:
                    self.stdout.write(
                        f"  [plaintiff] id={filing.id} docket={filing.docket_id}: "
                        f"'' → {new_p!r}"
                    )
                    if apply:
                        filing.plaintiff = new_p
                    parties_fixed += 1
                    changed = True

                if not filing.defendant and new_d:
                    self.stdout.write(
                        f"  [defendant] id={filing.id} docket={filing.docket_id}: "
                        f"'' → {new_d!r}"
                    )
                    if apply:
                        filing.defendant = new_d
                    parties_fixed += 1
                    changed = True

            if changed and apply:
                filing.save(update_fields=["court", "plaintiff", "defendant",
                                           "court_name", "court_full_name", "court_citation"])

        self.stdout.write("")
        self.stdout.write(
            self.style.SUCCESS(
                f"Done ({mode}). "
                f"court_fixed={court_fixed}, party_fields_fixed={parties_fixed}."
            )
        )
        if not apply:
            self.stdout.write(
                self.style.WARNING("Re-run with --apply to persist these changes.")
            )
