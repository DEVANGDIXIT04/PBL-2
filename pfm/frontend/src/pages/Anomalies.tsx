import { useEffect, useState } from "react";
import { api, inr } from "../api";
import type { Transaction } from "../types";

export function Anomalies() {
  const [rows, setRows] = useState<Transaction[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  async function load() {
    setLoading(true);
    try {
      setRows(await api<Transaction[]>("/api/v1/anomalies"));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load anomalies");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function detect() {
    setBusy(true);
    try {
      await api("/api/v1/anomalies/detect", { method: "POST", body: JSON.stringify({ retrain: true }) });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Detection failed");
    } finally {
      setBusy(false);
    }
  }

  async function label(txn: Transaction, isAnomaly: boolean) {
    await api(`/api/v1/transactions/${txn.id}/anomaly-label`, {
      method: "PATCH",
      body: JSON.stringify({ is_anomaly: isAnomaly }),
    });
    await load();
  }

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>Anomalies</h1>
          <p className="sub">Isolation Forest plus a median-absolute-deviation rule. The sentence is the top two feature deviations.</p>
        </div>
        <button className="btn" type="button" disabled={busy} onClick={() => void detect()}>
          {busy ? "Scoring…" : "Re-score"}
        </button>
      </div>
      {error && <div className="error">{error}</div>}
      {loading && <p className="note">Loading flagged transactions…</p>}
      {!loading && rows.length === 0 && <p className="note">Nothing is flagged. Run re-score after importing history.</p>}
      <div className="panel">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>What</th>
              <th>Amount</th>
              <th>Score</th>
              <th>Why</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((txn) => (
              <tr key={txn.id}>
                <td>{txn.txn_date.slice(0, 10)}</td>
                <td>
                  {txn.category_name}
                  <div className="reason">{txn.merchant}</div>
                </td>
                <td className="amount expense">{inr(txn.amount)}</td>
                <td>{txn.anomaly_score?.toFixed(3)}</td>
                <td>
                  <div>{txn.anomaly_reason}</div>
                  <div className="row" style={{ marginTop: 6 }}>
                    <button className="btn ghost" type="button" onClick={() => void label(txn, false)}>
                      This is normal
                    </button>
                    <button className="btn secondary" type="button" onClick={() => void label(txn, true)}>
                      This is fraud
                    </button>
                  </div>
                  {txn.anomaly_label_manual !== null && (
                    <div className="reason">Your label: {txn.anomaly_label_manual ? "fraud" : "normal"}</div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
