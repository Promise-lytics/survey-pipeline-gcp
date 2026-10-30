#!/usr/bin/env bash
# Removes all GCP resources created by setup.sh.
# Useful for keeping costs to zero between demos.
#
# Usage:
#   export PROJECT_ID=your-gcp-project-id
#   export REGION=europe-west1
#   bash infra/teardown.sh

set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
REGION="${REGION:-europe-west1}"

gcloud scheduler jobs delete survey-pipeline-trigger \
    --location="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null || true

gcloud run services delete survey-pipeline \
    --region="${REGION}" --project="${PROJECT_ID}" --quiet 2>/dev/null || true

gcloud sql instances delete survey-pipeline-db \
    --project="${PROJECT_ID}" --quiet 2>/dev/null || true

gcloud secrets delete survey-pipeline-db-password \
    --project="${PROJECT_ID}" --quiet 2>/dev/null || true

gsutil -m rm -r "gs://${PROJECT_ID}-survey-exports" 2>/dev/null || true

echo "done — all resources removed"
