"""
Enhanced “Data Profiler & Cleaner” — single-file Flask app.
Save as app.py, create venv, then:
    pip install flask pandas matplotlib numpy
Run:
    python app.py
Open http://localhost:5000 in your browser.
"""
import os, io, uuid, base64, tempfile
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")          # headless backend
import matplotlib.pyplot as plt
from flask import (
    Flask, request, render_template_string,
    send_file, url_for, flash
)

# --------------------------------------------------------------------- #
#  Flask setup
# --------------------------------------------------------------------- #
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 200 * 1024 * 1024     # 200 MB limit
app.secret_key = "CHANGE-ME-IN-PRODUCTION"

# --------------------------------------------------------------------- #
#  HTML templates (Bootstrap 5)
# --------------------------------------------------------------------- #
INDEX_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>CSV Data Profiler</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body class="container py-5">
  <h1 class="mb-4">CSV Data Profiler & Cleaner</h1>
  {% with msgs = get_flashed_messages() %}
    {% if msgs %}
      <div class="alert alert-warning">{{ msgs[0] }}</div>
    {% endif %}
  {% endwith %}
  <form method="POST" enctype="multipart/form-data" action="{{ url_for('upload') }}" class="mb-4">
    <div class="mb-3">
      <input type="file" name="file" accept=".csv" class="form-control" required>
    </div>
    <button type="submit" class="btn btn-primary">Upload & Profile</button>
  </form>
  <p class="text-muted">Max upload size: 200 MB</p>
</body></html>
"""

PROFILE_HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Profile Report</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
  <style>.dataframe td, .dataframe th {padding:4px 8px;}</style>
</head>
<body class="container py-4">
  <h2 class="mb-4">Data-Quality Profile</h2>
  <div class="table-responsive">{{ table | safe }}</div>

  {% if hist_imgs %}
  <h3 class="mt-5">Numeric Distributions</h3>
  <div class="row">
    {% for img in hist_imgs %}
      <div class="col-lg-4 col-md-6 col-sm-12 mb-4">
        <img src="data:image/png;base64,{{ img }}" class="img-fluid border rounded">
      </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if corr_img %}
    <h3 class="mt-5">Correlation Heat-map</h3>
    <img src="data:image/png;base64,{{ corr_img }}" class="img-fluid border rounded mb-4">
  {% endif %}

  <h3 class="mt-5">Cleaning Options</h3>
  <form method="POST" action="{{ url_for('clean') }}">
    <input type="hidden" name="temp_csv" value="{{ tempname }}" />
    <div class="row">
      <div class="col-md-6">
        <label class="form-label fw-bold">Drop specific columns</label>
        <select multiple class="form-select mb-3" name="drop_cols">
          {% for col in columns %}
            <option value="{{ col }}">{{ col }}</option>
          {% endfor %}
        </select>
      </div>
      <div class="col-md-6">
        <div class="form-check mb-2">
          <input class="form-check-input" type="checkbox" name="drop_duplicates" id="dup" checked>
          <label class="form-check-label" for="dup">Drop duplicate rows</label>
        </div>
        <div class="form-check mb-2">
          <input class="form-check-input" type="checkbox" name="drop_empty_cols" id="empty">
          <label class="form-check-label" for="empty">Drop columns with &gt;50 % missing</label>
        </div>
        <div class="form-check mb-2">
          <input class="form-check-input" type="checkbox" name="fill_numeric_mean" id="mean">
          <label class="form-check-label" for="mean">Fill numeric NaNs with column mean</label>
        </div>
        <div class="form-check mb-4">
          <input class="form-check-input" type="checkbox" name="fill_categorical_mode" id="mode">
          <label class="form-check-label" for="mode">Fill text NaNs with column mode</label>
        </div>
      </div>
    </div>
    <button type="submit" class="btn btn-success">Clean & Download CSV</button>
    <a href="{{ url_for('index') }}" class="btn btn-link">Start over</a>
  </form>
</body></html>
"""

# --------------------------------------------------------------------- #
#  Helper functions
# --------------------------------------------------------------------- #
def df_profile(df: pd.DataFrame) -> pd.DataFrame:
    """Return per-column summary."""
    rows = []
    for col in df.columns:
        s = df[col]
        info = dict(
            column=col,
            dtype=str(s.dtype),
            missing=int(s.isna().sum()),
            missing_pct=round(s.isna().mean()*100, 2),
            unique=int(s.nunique(dropna=False)),
            duplicates=int(s.duplicated().sum())
        )
        if pd.api.types.is_numeric_dtype(s):
            desc = s.describe(percentiles=[.25, .5, .75])
            info.update(desc.to_dict())
        rows.append(info)
    return pd.DataFrame(rows)

def fig_to_base64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()

def numeric_histograms(df: pd.DataFrame):
    """Return list of base64 PNGs, one per numeric column."""
    images = []
    for col in df.select_dtypes(include="number").columns:
        fig = plt.figure()
        df[col].plot(kind="hist", bins=30, title=f"Histogram — {col}")
        images.append(fig_to_base64(fig))
    return images

def correlation_heatmap(df: pd.DataFrame):
    num_df = df.select_dtypes(include="number")
    if num_df.shape[1] < 2:
        return None
    corr = num_df.corr(numeric_only=True)
    fig = plt.figure(figsize=(6,5))
    plt.imshow(corr, interpolation='nearest')
    plt.xticks(range(len(corr.columns)), corr.columns, rotation=90)
    plt.yticks(range(len(corr.columns)), corr.columns)
    plt.colorbar()
    plt.title("Correlation Matrix")
    return fig_to_base64(fig)

# --------------------------------------------------------------------- #
#  Routes
# --------------------------------------------------------------------- #
@app.route("/")
def index():
    return render_template_string(INDEX_HTML)

@app.route("/upload", methods=["POST"])
def upload():
    file = request.files.get("file")
    if not file or file.filename == "":
        flash("No file selected.")
        return render_template_string(INDEX_HTML)

    # Read CSV
    try:
        df = pd.read_csv(file.stream, low_memory=False)
    except Exception as e:
        flash(f"Cannot read CSV: {e}")
        return render_template_string(INDEX_HTML)

    # Warn if huge
    if df.shape[0] > 2_000_000:
        flash(f"Warning: large file with {df.shape[0]:,} rows may be slow.")

    # Build profile + visuals
    prof_df = df_profile(df)
    html_table = prof_df.round(3).fillna("").to_html(classes="table table-striped table-sm", index=False, border=0)

    hist_imgs = numeric_histograms(df)
    corr_img  = correlation_heatmap(df)

    # Save original CSV to temp for later cleaning
    temp_name = os.path.join(tempfile.gettempdir(), f"{uuid.uuid4()}.csv")
    df.to_csv(temp_name, index=False)

    return render_template_string(
        PROFILE_HTML,
        table=html_table,
        hist_imgs=hist_imgs,
        corr_img=corr_img,
        tempname=temp_name,
        columns=df.columns
    )

@app.route("/clean", methods=["POST"])
def clean():
    temp_csv = request.form.get("temp_csv")
    if not temp_csv or not os.path.exists(temp_csv):
        flash("Session expired — please upload again.")
        return render_template_string(INDEX_HTML)

    df = pd.read_csv(temp_csv, low_memory=False)
    os.remove(temp_csv)                 # tidy up

    # Handle cleaning selections
    drop_cols = request.form.getlist("drop_cols")
    if drop_cols:
        df.drop(columns=drop_cols, inplace=True, errors="ignore")

    if "drop_duplicates" in request.form:
        df = df.drop_duplicates()

    if "drop_empty_cols" in request.form:
        thresh = len(df) * 0.5          # require ≥50 % non-null
        df = df.dropna(axis=1, thresh=thresh)

    if "fill_numeric_mean" in request.form:
        for col in df.select_dtypes(include="number"):
            df[col].fillna(df[col].mean(), inplace=True)

    if "fill_categorical_mode" in request.form:
        for col in df.select_dtypes(exclude="number"):
            mode = df[col].mode(dropna=True)
            if not mode.empty:
                df[col].fillna(mode[0], inplace=True)

    # Return cleaned CSV
    out_path = os.path.join(tempfile.gettempdir(), f"cleaned_{uuid.uuid4()}.csv")
    df.to_csv(out_path, index=False)
    return send_file(out_path, as_attachment=True, download_name="cleaned_data.csv")

# --------------------------------------------------------------------- #
if __name__ == "__main__":
    # reachable on LAN; remove host param if not needed
    app.run(host="0.0.0.0", port=5000, debug=True)
