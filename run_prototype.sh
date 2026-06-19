#!/usr/bin/env bash
# Run this script to install dependencies and launch the Tool-Share Matcher.
# Usage:  bash run_prototype.sh
# The app will open at http://localhost:8501

set -e   # stop immediately if any command fails

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Starting the app..."
streamlit run app.py
