"""
Management command to upload default tournament banners to S3
Usage: python manage.py upload_default_banners
"""
import os

from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Upload default tournament banners to S3"

    def handle(self, *args, **options):
        if not settings.USE_S3:
            self.stdout.write(self.style.WARNING("S3 is not enabled. Skipping upload."))
            return

        from storages.backends.s3boto3 import S3Boto3Storage

        storage = S3Boto3Storage()

        # Default banner files
        banner_files = [
            "BGMI_Banner.jpeg",
            "COD_Banner.jpg",
            "Freefire_banner.jpeg",
            "Scarfall_banner.jpeg",
        ]

        # Source directory (local)
        source_dir = os.path.join(settings.BASE_DIR, "media", "tournaments", "default_banners")

        # Destination path on S3
        s3_path_prefix = "tournaments/default_banners/"

        uploaded_count = 0

        for banner_file in banner_files:
            local_path = os.path.join(source_dir, banner_file)
            s3_path = f"{s3_path_prefix}{banner_file}"

            if not os.path.exists(local_path):
                self.stdout.write(self.style.WARNING(f"File not found: {local_path}. Skipping."))
                continue

            try:
                # Check if file already exists on S3
                if storage.exists(s3_path):
                    self.stdout.write(self.style.WARNING(f"File already exists on S3: {s3_path}. Skipping."))
                    continue

                # Upload file
                with open(local_path, "rb") as f:
                    storage.save(s3_path, File(f))

                uploaded_count += 1
                self.stdout.write(self.style.SUCCESS(f"✓ Uploaded: {banner_file} → {s3_path}"))

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"✗ Failed to upload {banner_file}: {str(e)}"))

        self.stdout.write(self.style.SUCCESS(f"\n✓ Upload complete! {uploaded_count} files uploaded."))
