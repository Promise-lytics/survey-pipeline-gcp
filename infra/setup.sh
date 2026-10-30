#!/usr/bin/env bash
# Provisions the GCP infrastructure for the survey pipeline.
# Run once per environment. Idempotent — safe to re-run.
#
# Prerequisites:
#   gcloud auth login
#   gcloud config set project <your-project-id>
#
# Usage:
#   export PROJECT_ID=your-gcp-project-id
#   export REGION=europe-west1
#   bash infra/setup.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-europe-west1}"

DB_INSTANCE="survey-pipeline-db"
DB_NAME="surveys_db"
DB_USER="etl_user"
SECRET_NAME="survey-pipeline-db-password"
GCS_BUCKET="${PROJECT_ID}-survey-exports"
SERVICE_ACCOUNT="survey-pipeline-sa"
SA_EMAIL="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com"
IMAGE="gcr.io/${PROJECT_ID}/survey-pipeline:latest"
CLOUD_RUN_SERVICE="survey-pipeline"
SCHEDULER_JOB="survey-pipeline-trigger"

echo "--- enabling APIs"
gcloud services enable \
    run.googleapis.com \
    sql-component.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    cloudscheduler.googleapis.com \
    --project="${PROJECT_ID}"

echo "--- service account"
if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud iam service-accounts create "${SERVICE_ACCOUNT}" \
        --display-name="Survey Pipeline SA" \
        --project="${PROJECT_ID}"
fi

# roles the pipeline needs
for role in \
    roles/cloudsql.client \
    roles/storage.objectAdmin \
    roles/secretmanager.secretAccessor \
    roles/run.invoker; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="${role}" \
        --condition=None
done

echo "--- Cloud SQL (Postgres 14)"
if ! gcloud sql instances describe "${DB_INSTANCE}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud sql instances create "${DB_INSTANCE}" \
        --database-version=POSTGRES_14 \
        --tier=db-f1-micro \
        --region="${REGION}" \
        --storage-auto-increase \
        --backup-start-time=02:00 \
        --project="${PROJECT_ID}"
fi

if ! gcloud sql databases describe "${DB_NAME}" --instance="${DB_INSTANCE}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud sql databases create "${DB_NAME}" \
        --instance="${DB_INSTANCE}" \
        --project="${PROJECT_ID}"
fi

# generate a random password and store it in Secret Manager
DB_PASSWORD=$(openssl rand -base64 24)

if ! gcloud secrets describe "${SECRET_NAME}" --project="${PROJECT_ID}" &>/dev/null; then
    echo -n "${DB_PASSWORD}" | gcloud secrets create "${SECRET_NAME}" \
        --data-file=- \
        --replication-policy=automatic \
        --project="${PROJECT_ID}"
else
    echo -n "${DB_PASSWORD}" | gcloud secrets versions add "${SECRET_NAME}" \
        --data-file=- \
        --project="${PROJECT_ID}"
fi

gcloud sql users create "${DB_USER}" \
    --instance="${DB_INSTANCE}" \
    --password="${DB_PASSWORD}" \
    --project="${PROJECT_ID}" 2>/dev/null || true

echo "--- GCS bucket"
if ! gsutil ls "gs://${GCS_BUCKET}" &>/dev/null; then
    gsutil mb -p "${PROJECT_ID}" -l "${REGION}" "gs://${GCS_BUCKET}"
fi

gsutil iam ch "serviceAccount:${SA_EMAIL}:roles/storage.objectAdmin" "gs://${GCS_BUCKET}"

echo "--- Cloud Run"
gcloud run deploy "${CLOUD_RUN_SERVICE}" \
    --image="${IMAGE}" \
    --platform=managed \
    --region="${REGION}" \
    --service-account="${SA_EMAIL}" \
    --no-allow-unauthenticated \
    --set-env-vars="DB_HOST=127.0.0.1,DB_NAME=${DB_NAME},DB_USER=${DB_USER},GCS_BUCKET=${GCS_BUCKET},GCS_PREFIX=exports/" \
    --set-secrets="DB_PASSWORD=${SECRET_NAME}:latest" \
    --add-cloudsql-instances="${PROJECT_ID}:${REGION}:${DB_INSTANCE}" \
    --project="${PROJECT_ID}"

SERVICE_URL=$(gcloud run services describe "${CLOUD_RUN_SERVICE}" \
    --region="${REGION}" \
    --format="value(status.url)" \
    --project="${PROJECT_ID}")

echo "--- Cloud Scheduler"
if ! gcloud scheduler jobs describe "${SCHEDULER_JOB}" --location="${REGION}" --project="${PROJECT_ID}" &>/dev/null; then
    gcloud scheduler jobs create http "${SCHEDULER_JOB}" \
        --location="${REGION}" \
        --schedule="0 6 * * *" \
        --uri="${SERVICE_URL}/run" \
        --http-method=POST \
        --oidc-service-account-email="${SA_EMAIL}" \
        --project="${PROJECT_ID}"
fi

echo ""
echo "done. service: ${SERVICE_URL}"
echo "scheduler fires daily at 06:00 UTC"
