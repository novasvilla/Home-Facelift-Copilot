"""GCS image storage: upload images to Google Cloud Storage with local fallback."""

import logging
import os

logger = logging.getLogger(__name__)

_GCS_BUCKET = os.environ.get(
    "GCS_IMAGES_BUCKET",
    f"{os.environ.get('GCP_PROJECT_ID', 'capella-vertex-rag')}-facelift-images",
)
_client = None


def _get_client():
    """Lazy-init GCS client."""
    global _client
    if _client is None:
        try:
            from google.cloud import storage

            _client = storage.Client(
                project=os.environ.get("GCP_PROJECT_ID", "capella-vertex-rag")
            )
            logger.info("GCS client initialized for bucket %s", _GCS_BUCKET)
        except Exception as e:
            logger.warning("GCS client init failed (will use local): %s", e)
            _client = False  # Sentinel: don't retry
    return _client if _client else None


def upload_image(local_path: str, gcs_folder: str = "images") -> str | None:
    """Upload a local image to GCS and return the public URL.

    Returns:
        Public URL like https://storage.googleapis.com/bucket/folder/filename
        or None if GCS is unavailable (local fallback).
    """
    client = _get_client()
    if not client:
        return None

    try:
        bucket = client.bucket(_GCS_BUCKET)
        filename = os.path.basename(local_path)
        blob_name = f"{gcs_folder}/{filename}"
        blob = bucket.blob(blob_name)

        # Detect content type
        ext = os.path.splitext(filename)[1].lower()
        content_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        content_type = content_types.get(ext, "application/octet-stream")

        blob.upload_from_filename(local_path, content_type=content_type)
        public_url = f"https://storage.googleapis.com/{_GCS_BUCKET}/{blob_name}"
        logger.info("Uploaded to GCS: %s", public_url)
        return public_url
    except Exception as e:
        logger.warning("GCS upload failed for %s: %s", local_path, e)
        return None


def upload_bytes(data: bytes, filename: str, gcs_folder: str = "images") -> str | None:
    """Upload raw bytes to GCS and return the public URL."""
    client = _get_client()
    if not client:
        return None

    try:
        bucket = client.bucket(_GCS_BUCKET)
        blob_name = f"{gcs_folder}/{filename}"
        blob = bucket.blob(blob_name)

        ext = os.path.splitext(filename)[1].lower()
        content_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }
        content_type = content_types.get(ext, "application/octet-stream")

        blob.upload_from_string(data, content_type=content_type)
        public_url = f"https://storage.googleapis.com/{_GCS_BUCKET}/{blob_name}"
        logger.info("Uploaded bytes to GCS: %s", public_url)
        return public_url
    except Exception as e:
        logger.warning("GCS upload bytes failed for %s: %s", filename, e)
        return None
