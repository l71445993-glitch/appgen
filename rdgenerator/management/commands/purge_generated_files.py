"""Remove generated artifacts after their seven-day retention window.

The web process does not run a scheduler, so production should invoke this
command from a host cron/systemd timer. Generated-task rows are intentionally
kept as audit metadata; short-lived registration codes are removed after one
day.
"""

from datetime import timedelta, timezone as dt_timezone
from pathlib import Path
import shutil

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from ...models import (
    GithubRun,
    RegistrationEmailCode,
    release_generation_reservation,
)


RETENTION_DAYS = 7
STALE_RUN_STATUSES = (
    "Starting generator...please wait",
    "in_progress",
    "queued",
    "artifacts_pending",
)


class Command(BaseCommand):
    help = "Delete generated client artifacts and temporary archives older than seven days."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List files that would be removed without deleting them.",
        )
        parser.add_argument(
            "--max-age-days",
            type=int,
            default=RETENTION_DAYS,
            help="Retention window in days (1-7; defaults to 7).",
        )

    def handle(self, *args, **options):
        max_age_days = options["max_age_days"]
        if not 1 <= max_age_days <= RETENTION_DAYS:
            raise CommandError("--max-age-days must be between 1 and 7.")

        now = timezone.now()
        cutoff = now - timedelta(days=max_age_days)
        dry_run = options["dry_run"]
        removed_files = 0
        removed_dirs = 0
        released_reservations = 0
        timed_out_runs = 0
        removed_email_codes = 0

        email_code_queryset = RegistrationEmailCode.objects.filter(
            created_at__lte=now - timedelta(hours=24)
        )
        removed_email_codes = email_code_queryset.count()
        if not dry_run:
            email_code_queryset.delete()

        # Callback credentials expire after 24 hours. Runs still awaiting a
        # callback after that point can no longer deliver an artifact.
        stale_cutoff = now - timedelta(hours=24)
        stale_runs = GithubRun.objects.filter(
            status__in=STALE_RUN_STATUSES,
            created_at__lte=stale_cutoff,
        ).only("pk", "status", "quota_reserved", "quota_counted", "owner_id")
        for run in stale_runs:
            if dry_run:
                timed_out_runs += 1
                if run.quota_reserved and not run.quota_counted:
                    released_reservations += 1
                continue
            transitioned = GithubRun.objects.filter(
                pk=run.pk,
                status__in=STALE_RUN_STATUSES,
            ).update(status="timed_out")
            if transitioned:
                timed_out_runs += 1
                if release_generation_reservation(run):
                    released_reservations += 1

        run_by_uuid = {
            run.uuid: run
            for run in GithubRun.objects.only(
                "uuid",
                "created_at",
                "artifact_uploaded_at",
                "artifact_expires_at",
            )
        }

        for dirname in ("exe", "png"):
            root = Path(settings.BASE_DIR) / dirname
            files, dirs = self._purge_artifact_root(
                root,
                run_by_uuid,
                now=now,
                cutoff=cutoff,
                max_age=timedelta(days=max_age_days),
                dry_run=dry_run,
            )
            removed_files += files
            removed_dirs += dirs

        temp_root = Path(settings.BASE_DIR) / "temp_zips"
        files, dirs = self._purge_temp_root(temp_root, cutoff=cutoff, dry_run=dry_run)
        removed_files += files
        removed_dirs += dirs

        action = "Would remove" if dry_run else "Removed"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} {removed_files} file(s), {removed_dirs} director(ies), "
                f"{released_reservations} quota reservation(s), and "
                f"timed out {timed_out_runs} stale run(s); "
                f"{removed_email_codes} expired email code(s)."
            )
        )

    def _purge_artifact_root(
        self,
        root,
        run_by_uuid,
        *,
        now,
        cutoff,
        max_age,
        dry_run,
    ):
        """Purge known runs by their recorded expiry and orphan files by mtime."""
        if not root.is_dir():
            return 0, 0

        removed_files = 0
        removed_dirs = 0
        for run_dir in root.iterdir():
            if not run_dir.is_dir():
                # Keep unrelated files out of the generated-artifact cleanup.
                continue

            run = run_by_uuid.get(run_dir.name)
            if run is not None:
                expiry = run.artifact_expires_at
                if expiry is None:
                    # Legacy tasks predate artifact timestamps. Their retention
                    # window is anchored to task creation, preserving old rows.
                    expiry = run.created_at + timedelta(days=RETENTION_DAYS)
                anchor = run.artifact_uploaded_at or run.created_at
                expiry = min(expiry, anchor + max_age)
                expired = expiry <= now
                if expired:
                    files, directory_removed = self._remove_tree(
                        run_dir,
                        dry_run=dry_run,
                    )
                    removed_files += files
                    removed_dirs += directory_removed
                continue

            # An orphan directory has no task metadata.  Remove only files that
            # are older than the requested window, then prune empty directories.
            for path in sorted(run_dir.rglob("*"), reverse=True):
                if path.is_file() and self._is_older_than(path, cutoff):
                    if dry_run:
                        self.stdout.write(f"Would remove {path}")
                    else:
                        path.unlink(missing_ok=True)
                    removed_files += 1
                elif path.is_dir() and not dry_run:
                    self._remove_empty_dir(path)
            if not dry_run:
                if self._remove_empty_dir(run_dir):
                    removed_dirs += 1

        return removed_files, removed_dirs

    def _purge_temp_root(self, root, *, cutoff, dry_run):
        if not root.is_dir():
            return 0, 0
        removed_files = 0
        removed_dirs = 0
        for path in sorted(root.iterdir()):
            if path.is_file() and self._is_older_than(path, cutoff):
                if dry_run:
                    self.stdout.write(f"Would remove {path}")
                else:
                    path.unlink(missing_ok=True)
                removed_files += 1
            elif path.is_dir() and not dry_run:
                self._remove_empty_dir(path)
        return removed_files, removed_dirs

    @staticmethod
    def _is_older_than(path, cutoff):
        try:
            return timezone.datetime.fromtimestamp(
                path.stat().st_mtime,
                tz=dt_timezone.utc,
            ) <= cutoff
        except (FileNotFoundError, OSError, ValueError):
            return False

    def _remove_tree(self, path, *, dry_run):
        files = sum(1 for item in path.rglob("*") if item.is_file())
        dirs = 1 + sum(1 for item in path.rglob("*") if item.is_dir())
        if dry_run:
            self.stdout.write(f"Would remove {path}")
        else:
            shutil.rmtree(path, ignore_errors=True)
        return files, dirs

    @staticmethod
    def _remove_empty_dir(path):
        try:
            path.rmdir()
            return True
        except (FileNotFoundError, OSError):
            return False
