"""
Entry point for the Cloud Run job.

Cloud Scheduler POSTs to /run — the handler pulls pending CSV exports
from GCS, runs the ETL, and moves processed files out of the queue.

Can also be triggered manually:
    python src/pipeline.py
"""

import logging
import os
import sys

from flask import Flask, jsonify

from config import get_db_config, GCS_BUCKET, GCS_PREFIX
from extract import parse_csv_text
from gcs_source import list_pending_files, download_blob_as_text, move_to_processed
from load import get_connection, upsert_records
from transform import transform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("pipeline")

app = Flask(__name__)


def run_for_blob(blob_name: str) -> dict:
    logger.info("processing %s", blob_name)

    text     = download_blob_as_text(GCS_BUCKET, blob_name)
    raw_rows = parse_csv_text(text)
    result   = transform(raw_rows)

    if not result.clean:
        logger.warning("nothing to load from %s", blob_name)
        return {"blob": blob_name, "inserted": 0, "updated": 0,
                "skipped": result.skipped_duplicates, "rejected": result.rejected_invalid}

    cfg  = get_db_config()
    conn = get_connection(cfg)
    try:
        stats = upsert_records(
            conn=conn,
            records=result.clean,
            source_file=blob_name,
            skipped=result.skipped_duplicates,
            rejected=result.rejected_invalid,
        )
    finally:
        conn.close()

    move_to_processed(GCS_BUCKET, blob_name)
    return {"blob": blob_name, **stats}


@app.route("/run", methods=["POST"])
def handle_run():
    pending = list_pending_files(GCS_BUCKET, GCS_PREFIX)
    if not pending:
        logger.info("no pending files")
        return jsonify({"status": "ok", "processed": 0}), 200

    results = []
    errors  = []
    for blob in pending:
        try:
            results.append(run_for_blob(blob))
        except Exception as exc:
            logger.error("failed on %s: %s", blob, exc, exc_info=True)
            errors.append({"blob": blob, "error": str(exc)})

    status_code = 207 if errors else 200
    return jsonify({"status": "ok", "results": results, "errors": errors}), status_code


@app.route("/healthz", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    app.run(host="0.0.0.0", port=port)
