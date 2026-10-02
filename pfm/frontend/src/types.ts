export type Tokens = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type User = { id: number; email: string; created_at: string };

export type Category = { id: number; user_id: number | null; name: string; type: "income" | "expense" };

export type Transaction = {
  id: number;
  category_id: number;
  category_name: string;
  amount: number;
  type: "income" | "expense";
  description: string;
  merchant: string;
  txn_date: string;
  created_at: string;
  is_anomaly: boolean;
  anomaly_score: number | null;
  anomaly_reason: string | null;
  anomaly_label_manual: boolean | null;
};

export type TransactionPage = { items: Transaction[]; total: number; page: number; page_size: number };

export type Summary = {
  month: string;
  income: number;
  expense: number;
  savings: number;
  savings_rate: number;
  top_categories: { category: string; amount: number }[];
  budget_usage: { category: string; month: string; limit_amount: number; spent: number; usage_ratio: number }[];
  anomaly_count: number;
  trend: { month: string; income: number; expense: number }[];
};

export type ForecastPoint = { period: string; value: number };

export type ForecastSeries = {
  history: ForecastPoint[];
  history_adjusted: ForecastPoint[];
  forecast_raw: ForecastPoint[];
  forecast_adjusted: ForecastPoint[];
  lower: ForecastPoint[];
  upper: ForecastPoint[];
  excluded_periods: string[];
  model_raw: string;
  model_adjusted: string;
  next_raw: number | null;
  next_adjusted: number | null;
};

export type ForecastResponse = {
  granularity: "monthly" | "weekly";
  horizon: number;
  overall: ForecastSeries;
  by_category: Record<string, ForecastSeries> | null;
};

export type MetricRow = {
  model: string;
  precision?: number;
  recall?: number;
  f1?: number;
  roc_auc?: number | null;
  pr_auc?: number | null;
  mape?: number;
  rmse?: number;
  mae?: number;
};

export type Evaluation = {
  available: boolean;
  generated_at: string | null;
  anomaly: MetricRow;
  baselines: MetricRow[];
  forecast: {
    models?: MetricRow[];
    mape_raw?: number;
    mape_adjusted?: number;
    adjusted_mape_lower?: boolean;
    canonical_outlier?: { mae_raw: number; mae_adjusted: number; adjusted_is_better?: boolean };
    origins?: number;
  };
  sensitivity: { contamination: string | number; f1: number; precision: number; recall: number }[];
  user_feedback: { n_labels: number; precision?: number; recall?: number; f1?: number } | null;
  model_runs: number;
  notes: string;
};
