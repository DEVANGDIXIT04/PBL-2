import { useEffect, useState } from "react";
import { api } from "../api";
import type { Evaluation } from "../types";

function pct(value: number | null | undefined) {
  if (value === null || value === undefined) return "—";
  return value.toFixed(3);
}

export function Metrics() {
  const [data, setData] = useState<Evaluation | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api<Evaluation>("/api/v1/reports/evaluation")
      .then((payload) => {
        setData(payload);
        setError("");
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div>
      <h1>Model metrics</h1>
      <p className="sub">Numbers from the evaluation script. They are computed on synthetic labelled data, then stored for this page.</p>
      {error && <div className="error">{error}</div>}
      {loading && <p className="note">Loading metrics…</p>}
      {data && !data.available && (
        <div className="panel">
          <p>No evaluation file yet. From the project folder run <code>make evaluate</code>.</p>
        </div>
      )}
      {data?.available && (
        <>
          <section className="cards">
            <article className="card">
              <div className="label">Precision</div>
              <strong>{pct(data.anomaly.precision)}</strong>
            </article>
            <article className="card">
              <div className="label">Recall</div>
              <strong>{pct(data.anomaly.recall)}</strong>
            </article>
            <article className="card">
              <div className="label">F1</div>
              <strong>{pct(data.anomaly.f1)}</strong>
            </article>
            <article className="card">
              <div className="label">Forecast MAPE, adjusted</div>
              <strong>{data.forecast.mape_adjusted?.toFixed(1) ?? "—"}%</strong>
            </article>
          </section>
          <section className="panel">
            <h2>Anomaly baselines</h2>
            <p className="note">Temporal holdout: train on the earliest 70%, score the rest. Generated {data.generated_at}.</p>
            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>Precision</th>
                  <th>Recall</th>
                  <th>F1</th>
                  <th>ROC-AUC</th>
                  <th>PR-AUC</th>
                </tr>
              </thead>
              <tbody>
                {data.baselines.map((row) => (
                  <tr key={row.model}>
                    <td>{row.model}</td>
                    <td>{pct(row.precision)}</td>
                    <td>{pct(row.recall)}</td>
                    <td>{pct(row.f1)}</td>
                    <td>{pct(row.roc_auc)}</td>
                    <td>{pct(row.pr_auc)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
          <section className="panel">
            <h2>Forecast comparison</h2>
            <p className="note">
              Raw MAPE {data.forecast.mape_raw?.toFixed(2)}% · adjusted MAPE {data.forecast.mape_adjusted?.toFixed(2)}%.
              {data.forecast.adjusted_mape_lower ? " Adjusted is lower." : " Adjusted is not lower on this run."}
            </p>
            <table>
              <thead>
                <tr>
                  <th>Model</th>
                  <th>MAPE %</th>
                  <th>RMSE</th>
                  <th>MAE</th>
                </tr>
              </thead>
              <tbody>
                {(data.forecast.models ?? []).map((row) => (
                  <tr key={row.model}>
                    <td>{row.model}</td>
                    <td>{row.mape?.toFixed(2)}</td>
                    <td>{row.rmse?.toFixed(2)}</td>
                    <td>{row.mae?.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {data.forecast.canonical_outlier && (
              <p>
                INR 9,500 case — raw MAE {data.forecast.canonical_outlier.mae_raw.toFixed(2)}, adjusted MAE{" "}
                {data.forecast.canonical_outlier.mae_adjusted.toFixed(2)}.
              </p>
            )}
          </section>
          <section className="panel">
            <h2>Your labels</h2>
            <p className="note">
              Manual labels on this account: {data.user_feedback?.n_labels ?? 0}. Stored model runs: {data.model_runs}.
              {data.user_feedback && data.user_feedback.n_labels > 0
                ? ` Agreement with the model — precision ${pct(data.user_feedback.precision)}, recall ${pct(data.user_feedback.recall)}, F1 ${pct(data.user_feedback.f1)}.`
                : " Mark a few anomalies as normal or fraud and this updates."}
            </p>
          </section>
        </>
      )}
    </div>
  );
}
