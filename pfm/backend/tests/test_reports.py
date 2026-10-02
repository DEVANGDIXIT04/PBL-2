import json

from app.core.paths import EVALUATION_JSON
from app.services import evaluation_service


def test_evaluation_endpoint_without_artifact(client, monkeypatch, tmp_path):
    from tests.conftest import auth_header

    monkeypatch.setattr(evaluation_service, "EVALUATION_JSON", tmp_path / "missing.json")
    headers = auth_header(client)
    response = client.get("/api/v1/reports/evaluation", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["user_feedback"]["n_labels"] == 0


def test_evaluation_endpoint_reads_artifact(client, monkeypatch, tmp_path):
    from tests.conftest import auth_header

    artifact = tmp_path / "evaluation_results.json"
    artifact.write_text(
        json.dumps(
            {
                "generated_at": "2026-10-02T00:00:00+00:00",
                "notes": "computed",
                "anomaly": {
                    "product": {"f1": 0.8, "precision": 0.7, "recall": 0.9},
                    "baselines": [{"model": "MAD rule", "f1": 0.5}],
                    "sensitivity": [{"contamination": 0.02, "f1": 0.6}],
                },
                "forecast": {
                    "models": [{"model": "exponential_smoothing_adjusted", "mape": 8.5}],
                    "mape_raw": 12.0,
                    "mape_adjusted": 8.5,
                    "adjusted_mape_lower": True,
                    "origins": 6,
                },
                "canonical_outlier": {"mae_raw": 100.0, "mae_adjusted": 10.0},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(evaluation_service, "EVALUATION_JSON", artifact)
    headers = auth_header(client)
    response = client.get("/api/v1/reports/evaluation", headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["available"] is True
    assert body["anomaly"]["f1"] == 0.8
    assert body["forecast"]["mape_adjusted"] == 8.5
    assert EVALUATION_JSON.name == "evaluation_results.json"
