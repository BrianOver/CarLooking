#!/bin/bash
# Azure App Service startup script
# Set as the "Startup Command" in Azure portal -> Configuration -> General settings
set -e
mkdir -p /home/output
exec gunicorn \
  --bind=0.0.0.0:${PORT:-8000} \
  --workers=1 \
  --threads=4 \
  --timeout=1800 \
  --access-logfile=- \
  webapp:app
