"""
Write a full backup of the database (JSON) and uploaded files (photos, logo).

    python manage.py backup              # into ./backups
    python manage.py backup --keep 30    # also delete all but the newest 30 backups

Schedule it daily with Windows Task Scheduler (see docs/DEPLOYMENT.md).
Restore with:  python manage.py loaddata backups/sars-YYYYMMDD-HHMM.json
"""
import shutil

from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Back up the database and uploaded files into BACKUP_DIR."

    def add_arguments(self, parser):
        parser.add_argument("--keep", type=int, default=0, help="Number of most recent backups to keep (0 = keep all).")

    def handle(self, *args, keep=0, **options):
        backup_dir = settings.BACKUP_DIR
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = timezone.localtime().strftime("%Y%m%d-%H%M")
        data_file = backup_dir / f"sars-{stamp}.json"
        with open(data_file, "w", encoding="utf-8") as fh:
            management.call_command(
                "dumpdata", "--natural-foreign", "--natural-primary", "--indent", "1",
                "--exclude", "contenttypes", "--exclude", "auth.permission", "--exclude", "sessions",
                "--exclude", "admin.logentry", stdout=fh,
            )
        if settings.MEDIA_ROOT.exists():
            shutil.make_archive(str(backup_dir / f"sars-media-{stamp}"), "zip", settings.MEDIA_ROOT)
        self.stdout.write(self.style.SUCCESS(f"Backup written to {data_file}"))

        if keep > 0:
            for pattern in ("sars-2*.json", "sars-media-*.zip"):
                old = sorted(backup_dir.glob(pattern))[:-keep]
                for f in old:
                    f.unlink()
