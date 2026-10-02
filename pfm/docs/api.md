# API

Base URL: `/api/v1`. Every route except auth requires `Authorization: Bearer <access token>`.

Errors are JSON:

```json
{"detail": "Transaction not found", "code": "not_found"}
```

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/auth/register` | Create an account. Returns access and refresh tokens. |
| POST | `/auth/login` | Exchange email and password for tokens. |
| POST | `/auth/refresh` | Exchange a refresh token for a new pair. |
| GET | `/auth/me` | Current user. |
| GET/POST | `/transactions` | List (filters, pagination, sort) and create. |
| POST | `/transactions/import-csv` | Import `date,amount,type,category,description,merchant`. |
| GET/PATCH/DELETE | `/transactions/{id}` | Read, update, delete. |
| PATCH | `/transactions/{id}/anomaly-label` | Body `{ "is_anomaly": true/false }` stores a manual label. |
| GET/POST/PATCH/DELETE | `/categories` | Defaults are shared. Only user-owned categories can be edited. |
| GET/POST/PATCH/DELETE | `/budgets` | Monthly limit per category. |
| POST | `/anomalies/detect` | Re-score all rows, or a date range. |
| GET | `/anomalies` | Flagged rows with score and reason. |
| GET | `/forecast` | `horizon` 1–6, `granularity` monthly or weekly, `by_category`. |
| GET | `/reports/summary?month=YYYY-MM` | Income, expense, savings rate, top categories, budgets, anomalies. |
| GET | `/reports/evaluation` | Latest offline metrics plus this user's manual-label agreement. |
| GET | `/health` | Database ping. |

Interactive examples are in the OpenAPI UI at `/docs`.
