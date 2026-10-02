import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, inr } from "../api";
import type { Summary } from "../types";

export function Dashboard() {
  const [month, setMonth] = useState("2026-09");
  const [data, setData] = useState<Summary | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    api<Summary>(`/api/v1/reports/summary?month=${month}`)
      .then((summary) => {
        setData(summary);
        setError("");
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [month]);

  return (
    <div>
      <div className="row" style={{ justifyContent: "space-between" }}>
        <div>
          <h1>This month</h1>
          <p className="sub">What came in, what went out, and which categories are carrying the month.</p>
        </div>
        <label>
          Month
          <input type="month" value={month} onChange={(event) => setMonth(event.target.value)} />
        </label>
      </div>
      {error && <div className="error">{error}</div>}
      {loading && <p className="note">Loading the month…</p>}
      {data && (
        <>
          <section className="cards">
            <article className="card income">
              <div className="label">Income</div>
              <strong>{inr(data.income)}</strong>
            </article>
            <article className="card expense">
              <div className="label">Expense</div>
              <strong>{inr(data.expense)}</strong>
            </article>
            <article className="card">
              <div className="label">Savings rate</div>
              <strong>{Math.round(data.savings_rate * 100)}%</strong>
            </article>
            <article className="card alert">
              <div className="label">Anomalies</div>
              <strong>{data.anomaly_count}</strong>
            </article>
          </section>
          <div className="grid-2">
            <section className="panel">
              <h2>Income and expense</h2>
              <div className="chart">
                <ResponsiveContainer>
                  <LineChart data={data.trend}>
                    <CartesianGrid stroke="#efe7da" vertical={false} />
                    <XAxis dataKey="month" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="income" stroke="#1d7a46" strokeWidth={2} dot={false} />
                    <Line type="monotone" dataKey="expense" stroke="#9f2d2d" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </section>
            <section className="panel">
              <h2>Spend by category</h2>
              <div className="chart">
                <ResponsiveContainer>
                  <BarChart data={data.top_categories}>
                    <CartesianGrid stroke="#efe7da" vertical={false} />
                    <XAxis dataKey="category" />
                    <YAxis />
                    <Tooltip />
                    <Bar dataKey="amount" fill="#0e6b67" radius={[6, 6, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          </div>
          <section className="panel">
            <h2>Budgets</h2>
            {data.budget_usage.length === 0 && <p className="note">No budgets for this month.</p>}
            {data.budget_usage.map((budget) => {
              const ratio = Math.min(budget.usage_ratio, 1);
              const tone = budget.usage_ratio > 1 ? "over" : budget.usage_ratio > 0.85 ? "warn" : "";
              return (
                <div key={budget.category}>
                  <div className="row" style={{ justifyContent: "space-between" }}>
                    <strong>{budget.category}</strong>
                    <span>
                      {inr(budget.spent)} / {inr(budget.limit_amount)}
                    </span>
                  </div>
                  <div className={`bar ${tone}`}>
                    <span style={{ width: `${ratio * 100}%` }} />
                  </div>
                </div>
              );
            })}
          </section>
        </>
      )}
    </div>
  );
}
