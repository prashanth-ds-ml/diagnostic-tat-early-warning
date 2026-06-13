# Diagnostic TAT Early Warning Agent

Local Problem 9 prototype. It monitors the interim diagnostic checkpoint,
scores the probability of an SLA breach, ranks an operational queue, and
drafts consent-checked patient delay notifications for staff review.

All inputs are synthetic. The application does not send notifications and
does not push data or code to any remote service.

## GCP Cloud Shell setup

Clone the application. The required synthetic challenge data is bundled:

```bash
git clone https://github.com/prashanth-ds-ml/diagnostic-tat-early-warning.git
cd diagnostic-tat-early-warning
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python evaluate.py
```

To use data from another location:

```bash
export DIAGNOSTIC_DATA_DIR=/path/to/yashoda-synthetic-buildlab/op_diagnostics
```

## Components

- `risk_engine.py`: explainable checkpoint-time risk scoring and notification drafts.
- `dashboard.py`: Streamlit operations dashboard.
- `api.py`: FastAPI risk and queue endpoints.
- `evaluate.py`: held-out test evaluation and prediction export.
- `tests/`: focused risk and consent-gate tests.
- `WALKTHROUGH.md`: step-by-step build explanation, demo script, and documentation map.

Resource throughput and downtime are displayed as operational context. They
are not included in the risk score because the provided daily values may not
be known at the checkpoint in a real deployment.

## Bundled synthetic data

- `synthetic_diagnostic_orders.csv`: checkpoint and outcome data for 144,750 orders.
- `synthetic_diagnostic_resources.csv`: daily resource capacity and downtime context.
- `synthetic_op_patients.csv`: notification consent records.
- `synthetic_diagnostic_orders_test_labels.csv`: official held-out test labels.

The files are synthetic and originate from
`github.com/nallamotu/yashoda-synthetic-buildlab`.

## Run

From this directory:

```powershell
python evaluate.py
python -m pytest
python -m streamlit run dashboard.py
python -m uvicorn api:app --reload
```

API documentation is available at `http://127.0.0.1:8000/docs`.

In Cloud Shell, use Web Preview for the Streamlit port:

```bash
python -m streamlit run dashboard.py --server.port 8080
```

## Decision policy

- Score every order when the specimen-received checkpoint is recorded.
- Alert when breach probability is at least `0.40`. On the held-out test set,
  this high-recall threshold warns about more than 90% of eventual breaches.
- Draft a patient notification only when the patient opted in.
- Require staff approval before any message is sent.

The current production baseline is retrospective detection, which provides
zero proactive warning. Evaluation results are written to `output/metrics.json`.
