# Review notes

## Review 4 — Monday 5 October 2026

Working demo: `docker compose up --build`, then `make seed`, open http://localhost:3000 and sign in as `demo@example.com` / `Demo1234!`.

What to show:

- Dashboard for September 2026: income, expense, savings rate, category chart, budget bars.
- Transactions: anomaly badge and the generated reason. Buttons write `anomaly_label_manual`.
- Forecast: raw (dashed) versus anomaly-adjusted (solid). The adjusted line is the one that ignores flagged spikes.
- Model metrics: precision, recall, F1, ROC-AUC, PR-AUC, and MAPE / RMSE / MAE from `docs/evaluation.md`.

## The Review 3 forecast bug

A single INR 9,500 expense was left in the series, and exponential smoothing carried it into the next period. The fit now replaces a flagged amount with the category median only when it is at least three times that median, so a mild flag does not pull a normal month down. The original series stays on the chart. `tests/test_ml.py::test_adjusted_forecast_error_is_lower_than_raw` asserts that the adjusted MAE on that series is lower than the raw MAE. The same comparison is printed in `docs/evaluation.md`. Walk-forward MAPE is scored on the next month after labelled spikes are put back to the category median, because the forecast is of typical spending. The raw total, spikes included, is in the same report.

## Still rough

- Tokens live in `sessionStorage`, not an httpOnly cookie.
- The rate limit is in-memory, so it does not span multiple API processes.
- Prediction intervals are ± 1.96 residual standard deviations, not a full Holt-Winters interval.
- Walk-forward refits use 100 trees so the script finishes; the product detector uses 300.
