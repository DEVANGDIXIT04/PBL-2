"""Filesystem locations shared by the API, seed command, and evaluation."""

from pathlib import Path

# app/core/paths.py -> core -> app -> backend -> pfm
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DOCS_DIR = PROJECT_ROOT / "docs"
EVALUATION_JSON = DOCS_DIR / "evaluation_results.json"
EVALUATION_MD = DOCS_DIR / "evaluation.md"
FIGURES_DIR = DOCS_DIR / "figures"
