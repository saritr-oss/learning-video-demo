#!/bin/bash

# Deploy video_web to Google Cloud Run
# Usage: ./deploy.sh

set -e

# Load environment variables from .env if it exists
if [ -f .env ]; then
    while IFS='=' read -r key value || [ -n "$key" ]; do
        if [[ ! $key =~ ^# && -n $key ]]; then
            key=$(echo "$key" | xargs)
            value=$(echo "$value" | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//')
            value=$(echo "$value" | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'$//")
            export "$key=$value"
        fi
    done < .env
fi

# Configuration
PROJECT_ID="basic-garden-483315-e8"
REGION="us-central1"
SERVICE_NAME="video-web"

echo "🚀 Starting Deployment for ${SERVICE_NAME}..."
echo "   Project:  ${PROJECT_ID}"
echo "   Region:   ${REGION}"
echo ""

# 1. Set the active project
echo "Setting project to ${PROJECT_ID}..."
gcloud config set project ${PROJECT_ID}

# 2. Create temporary env_vars.yaml
ENV_FILE="env_vars_temp.yaml"

cat <<EOF > "$ENV_FILE"
USER1_NAME: ${USER1_NAME}
USER1_PASS: ${USER1_PASS}
USER2_NAME: ${USER2_NAME}
USER2_PASS: ${USER2_PASS}
EOF

echo "Created temporary environment file: ${ENV_FILE}"

# Cleanup on exit
cleanup() {
    if [ -f "$ENV_FILE" ]; then
        rm "$ENV_FILE"
        echo "Removed temporary environment file."
    fi
}
trap cleanup EXIT

# 3. Build and deploy to Cloud Run
echo "Building and deploying service..."
gcloud run deploy "${SERVICE_NAME}" \
    --source . \
    --region "${REGION}" \
    --min-instances 1 \
    --max-instances 3 \
    --memory 256Mi \
    --allow-unauthenticated \
    --env-vars-file "${ENV_FILE}"

echo ""
echo "✅ Deployment Complete!"
URL=$(gcloud run services describe "${SERVICE_NAME}" --region "${REGION}" --format='value(status.url)')
echo "Your video player is running at: ${URL}"
