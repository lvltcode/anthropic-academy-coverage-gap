# AI Content Decay Analysis

Research notebook measuring the gap between AI product release velocity and learning content coverage/update frequency.

## Research Question

What is the gap between AI product release velocity and public learning-content coverage?

## Project Structure

```
notebooks/       Jupyter notebooks (reconnaissance, then analysis)
scripts/         Data fetch and parse pipeline
data/raw/        Cached HTML (gitignored)
data/interim/    Intermediate CSVs (source status, parsed releases, parsed courses)
data/processed/  Final analysis-ready datasets
outputs/         Charts and tables
docs/            Source feasibility report
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

## Pipeline

```bash
python scripts/fetch_sources.py
python scripts/parse_release_notes.py
python scripts/parse_learning_catalogs.py
```

Then open `notebooks/00_data_reconnaissance.ipynb`.

## Part of

Portfolio series: *Anthropic Academy and the Skill Formation Gap*
