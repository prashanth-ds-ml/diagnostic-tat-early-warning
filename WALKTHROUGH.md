# Diagnostic TAT Early Warning Agent: Build Walkthrough

## 1. The problem we solved

Diagnostic investigations sometimes exceed their promised turnaround time
(SLA). The current process detects a delay only after the SLA has already
been breached.

Our solution scores every diagnostic order at the specimen-received
checkpoint, identifies orders likely to breach their SLA, ranks them for the
diagnostics team, and drafts a patient delay notification before the breach.

The notification is never automatically sent. It is blocked when the patient
has not opted in and always requires staff approval.

## 2. The success criteria

The challenge evaluation contract defines Problem 9 as:

- Prediction: will this diagnostic order breach its SLA?
- Decision moment: interim checkpoint, before completion.
- Primary metric: ROC-AUC.
- Operational metric: recall on orders that eventually breach.
- Required bar: early-warning ROC-AUC of at least 0.80.

The operational baseline is retrospective detection, which gives patients
zero proactive warning.

## 3. The data we used

The local synthetic dataset is in `yashoda-synthetic-buildlab/op_diagnostics/`.

### Main order data

`synthetic_diagnostic_orders.csv` contains 144,750 diagnostic orders from
March 1 through June 13, 2026.

The important checkpoint-time inputs are:

- `elapsed_at_checkpoint_hours`: time already spent when the checkpoint occurs.
- `expected_remaining_hours`: estimated work remaining.
- `promised_completion_window_hours`: committed SLA.
- `priority`: routine, urgent, or stat.
- `on_track_at_checkpoint`: transparent existing checkpoint rule.
- `test_code` and `test_category`: test context.

Outcome fields such as `slip_complete_hours`, actual completion timestamps,
and actual report time are not used to score live orders. They are used only
to evaluate predictions after the outcome is known.

### Supporting data

- `synthetic_op_patients.csv`: contains patient notification consent.
- `synthetic_diagnostic_resources.csv`: contains daily capacity, throughput,
  and downtime.
- `synthetic_diagnostic_orders_test_labels.csv`: held-out test answers.

Resource values are shown as operational context in the dashboard. We do not
use them in the risk score because final daily throughput and downtime may not
be known at the checkpoint in a real deployment.

## 4. The core risk calculation

We first calculate the expected total turnaround:

```text
expected total hours = elapsed checkpoint hours + expected remaining hours
```

We then calculate projected SLA slip:

```text
projected slip hours = expected total hours - promised SLA hours
```

Examples:

- Projected slip `+2.0`: expected to finish two hours late.
- Projected slip `-1.0`: expected to finish one hour before the SLA.

To make different SLA lengths comparable, projected slip is divided by the
promised SLA:

```text
projected slip ratio = projected slip hours / promised SLA hours
```

The ratio is converted into a probability-like score using a sigmoid
function. A small priority adjustment is applied because urgent and stat
orders generally receive stronger operational priority.

The existing off-track checkpoint flag remains a transparent safety rule. If
an order is already marked off track, its risk score cannot fall below 0.70.

This is an explainable scoring system, not a trained black-box ML model.

## 5. Alert and escalation policy

Risk levels are:

| Probability | Level | Action |
|---|---|---|
| Below 0.40 | Low | Continue standard monitoring |
| 0.40–0.59 | Medium | Monitor at next checkpoint |
| 0.60–0.79 | High | Review queue and prepare notification |
| 0.80+ | Critical | Escalate and draft notification |

The operational alert threshold is `0.40`. We selected this threshold because
the clinical priority is to miss as few eventual breaches as possible.

At this threshold, recall improves substantially, with a controlled increase
in false alerts.

## 6. Patient-notification safety

For an at-risk order:

1. Join the order to the patient record.
2. Check `notification_opt_in`.
3. If consent is absent, block the notification.
4. If consent exists, create a patient-friendly draft.
5. Require staff approval.
6. Never send automatically from this prototype.

The notification explains that the test is taking longer than expected and
provides the current estimated completion time. It does not expose internal
resource or operational details.

## 7. Application architecture

```text
Synthetic diagnostic CSVs
          |
          v
  Checkpoint risk engine
          |
          +--> Ranked at-risk queue
          |
          +--> Explanation and recommended action
          |
          +--> Consent check --> notification draft --> staff review
```

### `risk_engine.py`

The shared business-logic layer:

- Loads local synthetic data.
- Calculates breach risk.
- Produces human-readable reasons.
- Calculates promised and estimated completion times.
- Creates consent-checked notification drafts.
- Adds resource pressure context for the dashboard.

### `api.py`

FastAPI service exposing:

- `GET /health`: service and synthetic-data status.
- `GET /queue`: highest-risk recent orders.
- `GET /orders/{order_id}/risk`: risk explanation and notification draft.

### `dashboard.py`

Streamlit operations dashboard showing:

- Number of monitored orders.
- Alert and critical-order counts.
- Ranked at-risk queue.
- Test category and threshold filters.
- Projected slip, resource load, and downtime context.
- Risk explanation and notification-review panel.

### `evaluate.py`

Offline held-out evaluation:

- Selects only test-split orders.
- Scores each test order.
- Compares predictions against withheld labels.
- Computes ROC-AUC, recall, precision, and confusion-matrix counts.
- Compares our score against the existing checkpoint rule.
- Writes metrics and predictions to `output/`.

## 8. Evaluation results

Held-out test set:

- Test orders: 17,450
- Breach rate: 32.87%
- ROC-AUC: 0.953
- Alert threshold: 0.40
- Recall: 91.27%
- Precision: 72.12%

Comparison:

| Metric | Existing checkpoint rule | Our score |
|---|---:|---:|
| Recall | 83.11% | 91.27% |
| Precision | 82.76% | 72.12% |
| Breaches detected early | 4,767 | 5,235 |
| Breaches missed | 969 | 501 |

Our score finds 468 additional eventual breaches before they happen. The
tradeoff is 1,031 additional false alerts. This is intentional because the
selected operating point prioritizes patient communication and breach recall.

The current retrospective process provides zero proactive warning. The
prototype identifies 91.27% of eventual breaches at the interim checkpoint.

## 9. How to explain the demo

### 30-second summary

“Today, delayed diagnostic investigations are noticed after the promised
turnaround has already passed. We use information available at the
specimen-received checkpoint to calculate the expected completion time and
the probability of an SLA breach. At-risk orders are ranked for operational
review. For opted-in patients, the system prepares a delay notification, but
staff approval is always required. On the held-out test set, we identify
91.3% of eventual breaches before they happen, compared with 83.1% for the
existing checkpoint rule and zero proactive warning in the current process.”

### Three-minute demo flow

1. Open the dashboard and explain the monitored-order and alert counts.
2. Show that the at-risk queue is ranked by breach probability.
3. Select one order and explain:
   - promised SLA,
   - time already elapsed,
   - expected remaining time,
   - projected slip,
   - why the system classified it as at risk.
4. Show capacity and downtime as context for operational staff.
5. Show the patient notification draft and consent/review gates.
6. Close with the held-out metrics and baseline comparison.

## 10. Limitations and production next steps

This is a local prototype using synthetic data. Before production:

- Validate against real, approved hospital data.
- Confirm exactly which fields exist at the checkpoint.
- Replace daily final resource values with real-time queue and downtime signals.
- Calibrate probabilities and alert thresholds with diagnostics staff.
- Add authentication, role-based access, audit logging, and encryption.
- Integrate with LIS/HIS event streams and approved messaging systems.
- Monitor alert fatigue, delivery success, SLA impact, and patient complaints.
- Run a silent prospective trial before enabling patient notifications.

The current score is deterministic and explainable. A trained model can be
considered later, but only if it improves performance, remains leakage-safe,
and is clinically validated.

## 11. Run and verify locally

From `diagnostic-tat-agent/`:

```powershell
python evaluate.py
python -m pytest
python -m streamlit run dashboard.py
python -m uvicorn api:app --reload
```

Outputs:

- `output/metrics.json`: held-out metrics.
- `output/test_predictions.csv`: predictions for held-out orders.
- Streamlit dashboard: `http://127.0.0.1:8501`
- FastAPI documentation: `http://127.0.0.1:8000/docs`

## 12. Relevant documentation map

| Document | Why it matters |
|---|---|
| `data/Team-08-keeping-diagnostic-tests-on-time.pdf` | Original Team 8 problem statement |
| `BUILD.md` | Local solution plan, metrics, and demo checklist |
| `diagnostic-tat-agent/README.md` | How to run the local prototype |
| `diagnostic-tat-agent/WALKTHROUGH.md` | Full explanation and presentation guide |
| `yashoda-synthetic-buildlab/EVAL_CONTRACT.md` | Official prediction task and evaluation bar |
| `yashoda-synthetic-buildlab/BUILD_LAB_GUIDE.md` | Challenge build and scoring guidance |
| `yashoda-synthetic-buildlab/BASELINES.md` | Challenge baseline measurements |
| `yashoda-synthetic-buildlab/op_diagnostics/README.md` | Dataset overview and provenance |
| `yashoda-synthetic-buildlab/op_diagnostics/SCHEMA.md` | Column definitions and leakage warnings |
| `yashoda-synthetic-buildlab/op_diagnostics/splits.json` | Time-based train/validation/test assignments |
| `yashoda-synthetic-buildlab/starters/starter_p09_diagnostics_tat.py` | Problem 9 starter and baseline |

