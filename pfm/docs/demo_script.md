# Five-minute demo

1. Open http://localhost:3000 and sign in as `demo@example.com` / `Demo1234!` (30 seconds).
2. Dashboard, month September 2026. Point at income, expense, savings rate, the category bars, and any budget that is filling up (45 seconds).
3. Transactions. Filter to anomalies. Read one reason aloud — it is built from the two features that deviate most, for example a multiple of the usual Food spend or a new merchant (60 seconds).
4. Click "This is normal" on one row and "This is fraud" on another. Those labels are stored for the metrics page (30 seconds).
5. Forecast. Leave monthly, horizon 3. The dashed raw line sits above the solid adjusted line when a spike was in the history. Mention the excluded periods under the chart, and the INR 9,500 case from Review 3 (90 seconds).
6. Model metrics. Read precision, recall, and F1 for Isolation Forest plus the MAD rule, then MAPE for raw versus adjusted exponential smoothing. The tables match `docs/evaluation.md` (45 seconds).

If the metrics page says the evaluation file is missing, run `make evaluate` once and reload.
