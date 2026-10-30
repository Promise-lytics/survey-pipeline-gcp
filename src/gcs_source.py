import io
import logging
import os

from google.cloud import storage

logger = logging.getLogger(__name__)


def list_pending_files(bucket_name: str, prefix: str) -> list[str]:
    """Return GCS blob names under prefix that haven't been moved to processed/."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blobs = client.list_blobs(bucket, prefix=prefix)
    pending = [
        b.name for b in blobs
        if b.name.endswith(".csv") and "/processed/" not in b.name
    ]
    logger.info("found %d pending file(s) in gs://%s/%s", len(pending), bucket_name, prefix)
    return pending


def download_blob_as_text(bucket_name: str, blob_name: str) -> str:
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    content = blob.download_as_bytes()
    # handle BOM from SurveyCTO exports
    return content.decode("utf-8-sig")


def move_to_processed(bucket_name: str, blob_name: str) -> None:
    """Rename blob into a processed/ subfolder so it isn't picked up again."""
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    source = bucket.blob(blob_name)

    parts = blob_name.split("/")
    parts.insert(-1, "processed")
    dest_name = "/".join(parts)

    bucket.copy_blob(source, bucket, dest_name)
    source.delete()
    logger.info("moved gs://%s/%s → %s", bucket_name, blob_name, dest_name)
