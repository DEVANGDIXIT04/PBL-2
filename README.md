# Smart Personal Finance Tracker

Individual PBL-II project. Users record income and expenses. The API flags unusual transactions, explains the flag from the features that deviate, and forecasts next-period spending after those anomalies have been replaced so one spike does not distort the forecast.

The full project lives in [`pfm`](pfm).

```bash
cd pfm
docker compose up --build
```

In another shell, once the API is healthy:

```bash
cd pfm
make seed
```

Open http://localhost:3000 and sign in as `demo@example.com` / `Demo1234!`.

Setup, API summary, and limitations are in [pfm/README.md](pfm/README.md).
