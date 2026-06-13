# Diagnostic TAT Early Warning Agent

Problem 9 prototype. It monitors the interim diagnostic checkpoint,
scores the probability of an SLA breach, ranks an operational queue, and
emails new at-risk-order alerts to a configured diagnostics operations inbox.

All bundled inputs are synthetic. Email sending requires explicit SMTP
configuration and the `--send` flag.

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
- `frontend/`: React command center and Trigger Lab.
- `api.py`: FastAPI risk and queue endpoints.
- `evaluate.py`: held-out test evaluation and prediction export.
- `alert_runner.py`: automated scoring, deduplication, and SMTP email alerts.
- `watch_alerts.py`: continuously runs the alert workflow at a configured interval.
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
python -m uvicorn api:app --reload
python alert_runner.py
```

API documentation is available at `http://127.0.0.1:8000/docs`.

In a second terminal, start the React dashboard:

```bash
cd frontend
npm install
npm run dev -- --host 0.0.0.0 --port 5173
```

Open `http://127.0.0.1:5173`.

For Cloud Shell, run the React frontend on port `8080`, set the deployed
backend URL, and use Web Preview:

```bash
cd frontend
VITE_API_URL=https://YOUR-BACKEND-URL npm run dev -- --host 0.0.0.0 --port 8080
```

The React dashboard includes a **Trigger Lab**. Enter checkpoint inputs, calculate
risk, preview the generated alert, and select:

- **Trigger local alert**: writes a `.eml` message to `runtime/outbox/`.
- **Send SMTP alert**: sends to the entered operations mailbox after explicit confirmation.

## Decision policy

- Score every order when the specimen-received checkpoint is recorded.
- Alert when breach probability is at least `0.40`. On the held-out test set,
  this high-recall threshold warns about more than 90% of eventual breaches.
- Draft a patient notification only when the patient opted in.
- Require staff approval before any message is sent.

The current production baseline is retrospective detection, which provides
zero proactive warning. Evaluation results are written to `output/metrics.json`.

## Automated email alerts

The bundled patient data does not contain email addresses. The automated
runner therefore sends operational alerts to a configured diagnostics inbox,
including the patient notification-consent status for staff action.

Configure SMTP using environment variables. Never commit credentials:

```bash
export SMTP_HOST=smtp.gmail.com
export SMTP_PORT=587
export SMTP_USERNAME=your-account@example.com
export SMTP_PASSWORD='app-password-from-secret-manager'
export SMTP_SENDER=your-account@example.com
export ALERT_RECIPIENTS=diagnostics-operations@example.com
```

Preview the complete flow without sending:

```bash
python alert_runner.py --max-alerts 5
```

Send new alerts directly:

```bash
python alert_runner.py --send --max-alerts 25
```

For a continuously running VM or local demo:

```bash
python watch_alerts.py --send --interval-seconds 300
```

Sent order IDs are stored in `runtime/alert_state.json`, preventing duplicate
emails on a persistent filesystem. Schedule the command using cron or a Cloud
Run Job. For horizontally scaled production deployment, replace the local
state file with a shared transactional store such as Firestore.

Example cron entry, every five minutes:

```cron
*/5 * * * * cd /path/to/diagnostic-tat-early-warning && .venv/bin/python alert_runner.py --send
```
