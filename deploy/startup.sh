#!/usr/bin/env bash
# Comando de inicio para Azure App Service (Linux, runtime Python).
# Configurar en: App Service > Configuración > Configuración general > Comando de inicio
#   bash /home/site/wwwroot/deploy/startup.sh
set -euo pipefail

python -m streamlit run /home/site/wwwroot/app.py \
  --server.port="${PORT:-8000}" \
  --server.address=0.0.0.0 \
  --server.headless=true \
  --server.fileWatcherType=none \
  --server.enableCORS=false \
  --server.enableXsrfProtection=false
