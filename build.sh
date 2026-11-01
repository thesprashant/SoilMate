#!/usr/bin/env bash
# Render Build Script for Unified SoilMate Web Service
# Builds the Vite React frontend and installs FastAPI backend dependencies.

set -o errexit

echo "==> [1/2] Building SoilMate Frontend (React + Vite)..."
npm --prefix frontend install
npm --prefix frontend run build

echo "==> [2/2] Installing SoilMate Backend Dependencies..."
python -m pip install --upgrade pip
python -m pip install -r backend/requirements.txt

echo "==> SoilMate build completed successfully!"

