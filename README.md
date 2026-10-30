# survey-pipeline-gcp

Production deployment of the field survey ETL pipeline on Google Cloud Platform. The pipeline runs as a containerised Cloud Run job, triggered daily by Cloud Scheduler. It pulls SurveyCTO CSV exports from Cloud Storage, validates and deduplicates them, then upserts into a Cloud SQL (PostgreSQL 14) instance.

## Architecture

```
Cloud Scheduler (daily cron)
    → POST /run
        → Cloud Run job (this container)
            → Cloud Storage (reads pending exports)
            → Cloud SQL via Cloud SQL Auth Proxy (upserts clean records)
            → Cloud Storage (moves processed files to exports/processed/)
```

Credentials flow through Secret Manager — the DB password is injected at runtime via `--set-secrets`, so nothing sensitive touches the container image or environment config files.

## Stack

- Cloud Run (containerised Python/Flask job)
- Cloud SQL — PostgreSQL 14, db-f1-micro
- Cloud Storage — input queue and processed archive
- Secret Manager — DB password
- Cloud Scheduler — daily trigger at 06:00 UTC
- IAM service account with least-privilege roles

## Running locally

Prerequisites: Python 3.11+, a running Postgres instance, gcloud CLI authenticated.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in DB_PASSWORD and GCS_BUCKET

export $(grep -v '^#' .env | xargs)
python src/pipeline.py
```

For GCS access locally, make sure `GOOGLE_APPLICATION_CREDENTIALS` points to a service account key file with `roles/storage.objectAdmin` on the bucket.

## Deploying

1. Set your project:
   ```bash
   export PROJECT_ID=your-gcp-project-id
   export REGION=europe-west1
   gcloud config set project $PROJECT_ID
   ```

2. Build and push the image:
   ```bash
   gcloud builds submit --tag gcr.io/$PROJECT_ID/survey-pipeline:latest .
   ```

3. Run the infra setup script (idempotent):
   ```bash
   bash infra/setup.sh
   ```
   This creates: Cloud SQL instance, GCS bucket, Secret Manager secret, service account with IAM bindings, Cloud Run service, Cloud Scheduler job.

4. Apply the database schema (one time):
   ```bash
   # connect via Cloud SQL Auth Proxy then:
   psql -U etl_user -d surveys_db -f src/schema.sql
   ```

To remove all resources when not in use:
```bash
bash infra/teardown.sh
```

## How the pipeline works

On each trigger the Cloud Run handler:

1. Lists all `.csv` files under `GCS_PREFIX` that are not already in a `processed/` subfolder
2. Downloads each file, parses it, runs the transform (deduplication + validation)
3. Upserts clean records in batches of 500 using `ON CONFLICT DO UPDATE` with a change-detection predicate — rows that have not changed are skipped
4. Moves the source file to `exports/processed/` so it is not re-processed
5. Writes a run record to `surveys.etl_run_log` with counts and duration

## Tests

```bash
pytest tests/ -v
```

## Structure

```
survey-pipeline-gcp/
├── src/
│   ├── config.py        -- env-var config, DBConfig dataclass
│   ├── gcs_source.py    -- list / download / archive GCS blobs
│   ├── extract.py       -- CSV parsing
│   ├── transform.py     -- validation, deduplication, quality flags
│   ├── load.py          -- upsert to Postgres, audit log
│   └── pipeline.py      -- Flask app / Cloud Run entry point
├── infra/
│   ├── setup.sh         -- provisions all GCP resources
│   └── teardown.sh      -- removes all GCP resources
├── tests/
│   └── test_transform.py
├── Dockerfile
├── .env.example
├── .gitignore
└── requirements.txt
```
