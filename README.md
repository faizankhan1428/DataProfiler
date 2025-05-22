# Data Profiler & Cleaner Flask App

This is a lightweight Flask web app to upload, analyze, clean, and download CSV files.

## 🔍 Features

- 📤 Upload CSV files
- 📊 View column profiling (missing %, duplicates, unique values)
- 📈 Histograms for numeric data
- 🔥 Correlation heatmap
- 🧹 Cleaning options:
  - Drop columns
  - Remove duplicate rows
  - Drop columns with over 50% missing values
  - Fill numeric NaNs with mean
  - Fill text NaNs with mode

## 🚀 Run It Locally

```bash
# 1. Create virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate  # or source venv/bin/activate on Mac/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the app
python app.py

