#!/bin/bash
# =============================================================================
# KDV Bedding — ERPNext Custom App Installation Script
# Run this as the frappe user inside kdv-bench
# =============================================================================

set -e

BENCH_DIR="/home/frappe/kdv-bench"
APP_NAME="kdv_bedding"
SITE_NAME="kdv.localhost"

echo "=================================================="
echo " KDV Bedding App Installation"
echo "=================================================="

cd $BENCH_DIR

# Step 1: Get the app (from local path for dev, or GitHub for production)
echo "[1/5] Installing kdv_bedding app..."
# For local dev — copy app into bench apps folder:
# cp -r /path/to/kdv_bedding apps/kdv_bedding

# For production from GitHub (when repo is ready):
# bench get-app https://github.com/yourusername/kdv_bedding --branch main

echo "[2/5] Installing app on site..."
bench --site $SITE_NAME install-app $APP_NAME

echo "[3/5] Running migrations..."
bench --site $SITE_NAME migrate

echo "[4/5] Building assets..."
bench build --app $APP_NAME

echo "[5/5] Restarting services..."
bench restart

echo ""
echo "=================================================="
echo " Installation complete!"
echo " Next steps:"
echo " 1. Open ERPNext and go to KDV Fiscalisation Settings"
echo " 2. Configure ZIMRA device credentials"
echo " 3. Run Sage Pastel migration from the Migration page"
echo " 4. Set up Chart of Accounts for Zimbabwe"
echo "=================================================="
