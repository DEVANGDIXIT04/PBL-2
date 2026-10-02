import { FormEvent, useEffect, useState } from "react";
import { api, inr } from "../api";
import type { Category, Transaction, TransactionPage } from "../types";

const emptyForm = {
  category_id: "",
  amount: "",
  type: "expense",
  description: "",
  merchant: "",
  txn_date: "2026-09-15T13:00",
};

export function Transactions() {
  const [page, setPage] = useState<TransactionPage | null>(null);
  const [categories, setCategories] = useState<Category[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [txnType, setTxnType] = useState("");
  const [anomalyOnly, setAnomalyOnly] = useState("");
  const [form, setForm] = useState(emptyForm);
  const [message, setMessage] = useState("");

  async function load() {
    setLoading(true);
    const params = new URLSearchParams({ page_size: "50", sort: "-txn_date" });
    if (txnType) params.set("txn_type", txnType);
    if (anomalyOnly) params.set("is_anomaly", anomalyOnly);
    try {
      const [rows, cats] = await Promise.all([
        api<TransactionPage>(`/api/v1/transactions?${params.toString()}`),
        api<Category[]>("/api/v1/categories"),
      ]);
      setPage(rows);
      setCategories(cats);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load transactions");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [txnType, anomalyOnly]);

  async function addTransaction(event: FormEvent) {
    event.preventDefault();
    setMessage("");
    try {
      await api("/api/v1/transactions", {
        method: "POST",
        body: JSON.stringify({
          ...form,
          category_id: Number(form.category_id),
          amount: Number(form.amount),
        }),
      });
      setForm(emptyForm);
      setMessage("Saved.");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save");
    }
  }

  async function upload(file: File) {
    const body = new FormData();
    body.append("file", file);
    try {
      const result = await api<{ imported: number; rejected: { row: number; reason: string }[] }>(
        "/api/v1/transactions/import-csv",
        { method: "POST", body },
      );
      setMessage(`Imported ${result.imported}. Rejected ${result.rejected.length}.`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Import failed");
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
      <h1>Transactions</h1>
      <p className="sub">Filter, add, or import. Flagged rows carry a short reason, not just a score.</p>
      {error && <div className="error">{error}</div>}
      {message && <p className="note">{message}</p>}
      <div className="toolbar">
        <select value={txnType} onChange={(event) => setTxnType(event.target.value)}>
          <option value="">All types</option>
          <option value="expense">Expenses</option>
          <option value="income">Income</option>
        </select>
        <select value={anomalyOnly} onChange={(event) => setAnomalyOnly(event.target.value)}>
          <option value="">Anomalies and normal</option>
          <option value="true">Anomalies only</option>
          <option value="false">Normal only</option>
        </select>
        <label className="btn secondary">
          Import CSV
          <input
            type="file"
            accept=".csv,text/csv"
            hidden
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) void upload(file);
            }}
          />
        </label>
        <a className="btn ghost" href="/sample_transactions.csv">
          Sample CSV
        </a>
      </div>
      <form className="panel" onSubmit={addTransaction}>
        <h2>Add a transaction</h2>
        <div className="form-grid">
          <select
            required
            value={form.category_id}
            onChange={(event) => {
              const category = categories.find((item) => String(item.id) === event.target.value);
              setForm({ ...form, category_id: event.target.value, type: category?.type ?? form.type });
            }}
          >
            <option value="">Category</option>
            {categories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
          <input
            required
            type="number"
            min="1"
            step="0.01"
            placeholder="Amount"
            value={form.amount}
            onChange={(event) => setForm({ ...form, amount: event.target.value })}
          />
          <input
            required
            type="datetime-local"
            value={form.txn_date}
            onChange={(event) => setForm({ ...form, txn_date: event.target.value })}
          />
          <input
            placeholder="Merchant"
            value={form.merchant}
            onChange={(event) => setForm({ ...form, merchant: event.target.value })}
          />
          <input
            placeholder="Description"
            value={form.description}
            onChange={(event) => setForm({ ...form, description: event.target.value })}
          />
          <button className="btn" type="submit">
            Save
          </button>
        </div>
      </form>
      {loading && <p className="note">Loading transactions…</p>}
      {page && (
        <div className="panel">
          <p className="note">{page.total} transactions</p>
          <table>
            <thead>
              <tr>
                <th>Date</th>
                <th>Category</th>
                <th>Merchant</th>
                <th>Amount</th>
                <th>Flag</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((txn) => (
                <tr key={txn.id}>
                  <td>{txn.txn_date.slice(0, 16).replace("T", " ")}</td>
                  <td>{txn.category_name}</td>
                  <td>{txn.merchant || txn.description}</td>
                  <td className={`amount ${txn.type}`}>{inr(txn.amount)}</td>
                  <td>
                    {txn.is_anomaly && <span className="badge">Anomaly</span>}
                    {txn.anomaly_reason && <div className="reason">{txn.anomaly_reason}</div>}
                    <div className="row" style={{ marginTop: 6 }}>
                      <button className="btn ghost" type="button" onClick={() => void label(txn, false)}>
                        This is normal
                      </button>
                      <button className="btn secondary" type="button" onClick={() => void label(txn, true)}>
                        This is fraud
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
