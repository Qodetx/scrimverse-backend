"""
Custom storage backends for AWS S3
Separates static and media files into different directories
"""
from django.conf import settings  # noqa: F401

from storages.backends.s3boto3 import S3Boto3Storage


class StaticStorage(S3Boto3Storage):
    """Storage backend for static files (CSS, JS, etc.)"""

    location = "static"
    default_acl = "public-read"
    file_overwrite = True  # Static files can be overwritten


class MediaStorage(S3Boto3Storage):
    """Storage backend for media files (user uploads)"""

    location = "media"
    default_acl = "public-read"
    file_overwrite = False  # Don't overwrite user uploads
