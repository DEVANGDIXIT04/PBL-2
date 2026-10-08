# Evaluation

These figures were produced by `python -m app.ml.evaluate`. They are not hand-written.

- Generated at: 2026-10-08T18:33:07.335974+00:00
- Synthetic rows: 1217 over 24 months (seed 42)
- Labelled anomalies: 38 (3.1% of rows)
- Detector trees: 300. Walk-forward refits use 100 trees.

## Anomaly detection

Fit on the earliest 70% of transactions, score the latest 30%.
 The product model uses contamination 0.03, chosen to match the injected anomaly rate. The sweep below includes `auto`.
 Test rows: 366. Labelled anomalies in the test window: 13.

| Model | Precision | Recall | F1 | ROC-AUC | PR-AUC | TP | FP | FN | TN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Isolation Forest + MAD (product) | 0.467 | 0.538 | 0.500 | 0.739 | 0.564 | 7 | 8 | 6 | 345 |
| Isolation Forest | 1.000 | 0.154 | 0.267 | 0.740 | 0.278 | 2 | 0 | 11 | 353 |
| Z-score rule | 0.600 | 0.231 | 0.333 | 0.738 | 0.481 | 3 | 2 | 10 | 351 |
| MAD rule | 0.467 | 0.538 | 0.500 | 0.717 | 0.563 | 7 | 8 | 6 | 345 |
| Local Outlier Factor | 1.000 | 0.154 | 0.267 | 0.738 | 0.476 | 2 | 0 | 11 | 353 |
| One-Class SVM | 0.400 | 0.308 | 0.348 | 0.627 | 0.311 | 4 | 6 | 9 | 347 |

![F1 by model](figures/anomaly_f1.png)

## Contamination sensitivity

Same holdout, Isolation Forest only, varying `contamination`.

| Contamination | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| 0.01 | 1.000 | 0.077 | 0.143 |
| 0.02 | 1.000 | 0.077 | 0.143 |
| 0.05 | 0.375 | 0.231 | 0.286 |
| 0.1 | 0.192 | 0.385 | 0.256 |
| auto | 0.206 | 0.538 | 0.298 |

![Contamination sensitivity](figures/contamination_sensitivity.png)

## Forecasting

Monthly expense totals, rolling origin, one-step horizon. Each origin refits Isolation Forest on past rows only. Flagged amounts are replaced with the category median only when they are at least three times that median, then exponential smoothing is fit on the cleaned series. The main table scores every model on the next month after labelled spikes are put back to the category median. A second table scores the same forecasts on the raw total, which still includes those spikes. Origins: 12.

| Model | MAPE % | RMSE | MAE | Origins |
| --- | ---: | ---: | ---: | ---: |
| naive | 6.81 | 3829.13 | 2898.73 | 12 |
| moving_average | 6.37 | 3187.66 | 2664.61 | 12 |
| exponential_smoothing_raw | 6.24 | 3062.05 | 2625.11 | 12 |
| exponential_smoothing_adjusted | 5.26 | 2840.67 | 2289.48 | 12 |

![Forecast MAPE](figures/forecast_mape.png)

Same forecasts scored on the raw next-month total, spikes included.

| Model | MAPE % | RMSE | MAE | Origins |
| --- | ---: | ---: | ---: | ---: |
| naive | 6.56 | 4154.66 | 3050.05 | 12 |
| moving_average | 6.44 | 3630.80 | 2912.89 | 12 |
| exponential_smoothing_raw | 6.07 | 3620.16 | 2764.77 | 12 |
| exponential_smoothing_adjusted | 7.68 | 4380.85 | 3584.15 | 12 |

## The INR 9,500 outlier

A flat INR 3,000 monthly series with a single INR 9,500 point in the training window, then three normal months held out. This is the Review 3 failure, measured directly.

- Raw forecast MAE: **3640.00**
- Anomaly-adjusted forecast MAE: **0.00**
- Adjusted error is lower: **True**
- Raw next points: [6120.0, 6640.0, 7160.0]
- Adjusted next points: [3000.0, 3000.0, 3000.0]

## Reading the numbers

Anomaly metrics are a temporal holdout, not in-sample scores. On the controlled INR 9,500 series, replacing the outlier drops forecast MAE from 3640 to 0. On the synthetic walk-forward, replacing flagged spikes (at least three times the category median) lowers MAPE on the undistorted next month from 6.24% to 5.26%. Against the raw total, which still includes future spikes, the same forecasts score 6.07% raw and 7.68% adjusted.
 Duplicate charges of a normal amount are harder than 4–10x spikes, so recall is not 1. That is the labelled data, not a tuned table.
