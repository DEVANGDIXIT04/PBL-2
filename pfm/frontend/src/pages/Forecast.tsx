import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, inr } from "../api";
import type { ForecastPoint, ForecastResponse, ForecastSeries } from "../types";

function mergeSeries(series: ForecastSeries) {
  const map = new Map<string, Record<string, string | number>>();
  const put = (points: ForecastPoint[], key: string) => {
    for (const point of points) {
      const row = map.get(point.period) ?? { period: point.period };
      row[key] = point.value;
      map.set(point.period, row);
    }
  };
  put(series.history, "history");
  put(series.history_adjusted, "adjustedHistory");
  put(series.forecast_raw, "rawForecast");
  put(series.forecast_adjusted, "adjustedForecast");
  put(series.lower, "lower");
  put(series.upper, "upper");
  return Array.from(map.values());
}

export function Forecast() {
  const [horizon, setHorizon] = useState(3);
  const [granularity, setGranularity] = useState<"monthly" | "weekly">("monthly");
  const [byCategory, setByCategory] = useState(false);
  const [data, setData] = useState<ForecastResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    const params = new URLSearchParams({
      horizon: String(horizon),
      granularity,
      by_category: String(byCategory),
    });
    api<ForecastResponse>(`/api/v1/forecast?${params.toString()}`)
      .then((payload) => {
        setData(payload);
        setError("");
      })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [horizon, granularity, byCategory]);

  const overall = data?.overall;

  return (
    <div>
      <h1>Forecast</h1>
      <p className="sub">
        The dashed line is exponential smoothing on the raw totals. The solid line replaces flagged anomalies with the
        category median first, so one spike does not drag the next period.
      </p>
      <div className="toolbar">
        <select value={granularity} onChange={(event) => setGranularity(event.target.value as "monthly" | "weekly")}>
          <option value="monthly">Monthly</option>
          <option value="weekly">Weekly</option>
        </select>
        <select value={horizon} onChange={(event) => setHorizon(Number(event.target.value))}>
          {[1, 2, 3, 4, 5, 6].map((value) => (
            <option key={value} value={value}>
              {value} period{value > 1 ? "s" : ""}
            </option>
          ))}
        </select>
        <label className="row">
          <input type="checkbox" checked={byCategory} onChange={(event) => setByCategory(event.target.checked)} />
          By category
        </label>
      </div>
      {error && <div className="error">{error}</div>}
      {loading && <p className="note">Fitting the forecast…</p>}
      {overall && (
        <>
          <section className="cards">
            <article className="card expense">
              <div className="label">Next period, raw</div>
              <strong>{overall.next_raw === null ? "—" : inr(overall.next_raw)}</strong>
            </article>
            <article className="card">
              <div className="label">Next period, adjusted</div>
              <strong>{overall.next_adjusted === null ? "—" : inr(overall.next_adjusted)}</strong>
            </article>
            <article className="card alert">
              <div className="label">Periods with outliers removed</div>
              <strong>{overall.excluded_periods.length}</strong>
            </article>
          </section>
          <section className="panel">
            <h2>
              Overall · {overall.model_adjusted} · band is the adjusted interval
            </h2>
            <div className="chart">
              <ResponsiveContainer>
                <LineChart data={mergeSeries(overall)}>
                  <CartesianGrid stroke="#efe7da" vertical={false} />
                  <XAxis dataKey="period" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="history" name="Actual" stroke="#1c2430" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="rawForecast" name="Raw forecast" stroke="#9f2d2d" strokeDasharray="6 4" dot={false} />
                  <Line type="monotone" dataKey="adjustedForecast" name="Adjusted forecast" stroke="#0e6b67" strokeWidth={2.4} dot={false} />
                  <Line type="monotone" dataKey="upper" name="Upper" stroke="#9ec9c4" dot={false} />
                  <Line type="monotone" dataKey="lower" name="Lower" stroke="#9ec9c4" dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
            {overall.excluded_periods.length > 0 && (
              <p className="note">Outlier periods replaced before fitting: {overall.excluded_periods.join(", ")}</p>
            )}
          </section>
          {data.by_category &&
            Object.entries(data.by_category).map(([name, series]) => (
              <section className="panel" key={name}>
                <h2>
                  {name}: adjusted {series.next_adjusted === null ? "—" : inr(series.next_adjusted)} vs raw{" "}
                  {series.next_raw === null ? "—" : inr(series.next_raw)}
                </h2>
                <div className="chart">
                  <ResponsiveContainer>
                    <LineChart data={mergeSeries(series)}>
                      <CartesianGrid stroke="#efe7da" vertical={false} />
                      <XAxis dataKey="period" />
                      <YAxis />
                      <Tooltip />
                      <Line dataKey="history" stroke="#1c2430" dot={false} />
                      <Line dataKey="rawForecast" stroke="#9f2d2d" strokeDasharray="6 4" dot={false} />
                      <Line dataKey="adjustedForecast" stroke="#0e6b67" strokeWidth={2} dot={false} />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </section>
            ))}
        </>
      )}
    </div>
  );
}
