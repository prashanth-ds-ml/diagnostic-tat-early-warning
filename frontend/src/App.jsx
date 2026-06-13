import { useEffect, useMemo, useState } from "react";

const API = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";
const riskColor = { critical: "#ff4d5f", high: "#ff8a3d", medium: "#f6c453", low: "#4bd4a0" };

async function api(path, options) {
  const response = await fetch(`${API}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.detail || "Request failed");
  return body;
}

function Metric({ label, value, note, accent }) {
  return (
    <article className="metric" style={{ "--accent": accent }}>
      <span>{label}</span><strong>{value}</strong><small>{note}</small>
    </article>
  );
}

function Bars({ data }) {
  const entries = Object.entries(data || {});
  const max = Math.max(...entries.map(([, value]) => value), 1);
  return <div className="bars">{entries.map(([name, value]) => (
    <div className="bar-row" key={name}>
      <span>{name.replaceAll("_", " ")}</span>
      <div><i style={{ width: `${(value / max) * 100}%` }} /></div>
      <b>{value < 2 ? `${Math.round(value * 100)}%` : value}</b>
    </div>
  ))}</div>;
}

function Queue({ rows, onSelect }) {
  return <div className="table-wrap"><table>
    <thead><tr><th>Order</th><th>Test</th><th>Priority</th><th>Risk</th><th>Projected slip</th><th>Resource load</th><th></th></tr></thead>
    <tbody>{rows.map(row => <tr key={row.order_id}>
      <td><b>{row.order_id}</b><small>{row.test_category.replaceAll("_", " ")}</small></td>
      <td>{row.test_code.replaceAll("_", " ")}</td>
      <td><span className={`priority ${row.priority}`}>{row.priority}</span></td>
      <td><span className="risk-pill" style={{ background: riskColor[row.risk_level] }}>{Math.round(row.breach_probability * 100)}% {row.risk_level}</span></td>
      <td className="slip">+{row.projected_slip_hours.toFixed(2)} h</td>
      <td>{Math.round((row.capacity_load_ratio || 0) * 100)}%</td>
      <td><button className="text-button" onClick={() => onSelect(row.order_id)}>Review</button></td>
    </tr>)}</tbody>
  </table></div>;
}

function App() {
  const [view, setView] = useState("command");
  const [dashboard, setDashboard] = useState(null);
  const [queue, setQueue] = useState([]);
  const [options, setOptions] = useState({ test_codes: [], test_categories: [], priorities: [] });
  const [threshold, setThreshold] = useState(.4);
  const [selected, setSelected] = useState(null);
  const [message, setMessage] = useState("");
  const [form, setForm] = useState({
    order_id: "LOCAL-DEMO-001", patient_id: "LOCAL-PATIENT", test_code: "CBC",
    test_category: "hematology", priority: "routine", order_time: new Date().toISOString(),
    promised_completion_window_hours: 6, elapsed_at_checkpoint_hours: 2,
    expected_remaining_hours: 6, on_track_at_checkpoint: false,
    notification_opt_in: true, recipient: "diagnostics-operations@example.com",
  });
  const [simulation, setSimulation] = useState(null);

  const load = async () => {
    const [d, q, o] = await Promise.all([
      api(`/dashboard?minimum_probability=${threshold}`),
      api(`/queue?limit=100&minimum_probability=${threshold}`),
      api("/options"),
    ]);
    setDashboard(d); setQueue(q); setOptions(o);
    if (o.test_codes.length && form.test_code === "CBC") setForm(f => ({ ...f, test_code: o.test_codes[0], test_category: o.test_categories[0] }));
  };
  useEffect(() => { load().catch(e => setMessage(e.message)); }, [threshold]);

  const review = async id => { setSelected(await api(`/orders/${id}/risk`)); setView("review"); };
  const simulate = async e => {
    e.preventDefault(); setMessage("");
    try { setSimulation(await api("/simulate", { method: "POST", body: JSON.stringify(form) })); }
    catch (error) { setMessage(error.message); }
  };
  const trigger = async delivery => {
    try {
      const result = await api("/trigger", { method: "POST", body: JSON.stringify({ order: form, delivery }) });
      setMessage(delivery === "local" ? `Local alert created: ${result.path}` : `Alert sent to ${result.recipient}`);
    } catch (error) { setMessage(error.message); }
  };
  const metrics = dashboard?.metrics || {};
  const filteredQueue = useMemo(() => queue, [queue]);

  return <div className="app-shell">
    <aside>
      <div className="brand"><span>YT</span><div><b>Yashoda</b><small>Diagnostics AI</small></div></div>
      <nav>{[
        ["command", "Command Center"], ["review", "Alert Review"], ["trigger", "Trigger Lab"], ["delivery", "Delivery Setup"],
      ].map(([id, label]) => <button key={id} className={view === id ? "active" : ""} onClick={() => setView(id)}>{label}</button>)}</nav>
      <div className="system"><i /> System operational<small>Synthetic data environment</small></div>
    </aside>
    <main>
      <header><div><small>CLINICAL OPERATIONS</small><h1>Diagnostic TAT Command Center</h1><p>Predict SLA breaches, prioritize intervention, and trigger proactive alerts.</p></div><div className="header-actions"><label>Alert threshold <b>{Math.round(threshold * 100)}%</b><input type="range" min=".2" max=".9" step=".05" value={threshold} onChange={e => setThreshold(Number(e.target.value))} /></label><button onClick={load}>Refresh</button></div></header>
      {message && <div className="toast" onClick={() => setMessage("")}>{message}</div>}

      {view === "command" && dashboard && <>
        <section className="metrics-grid">
          <Metric label="Orders monitored" value={metrics.orders_monitored?.toLocaleString()} note="Most recent checkpoints" accent="#54b8ff" />
          <Metric label="Active alerts" value={metrics.active_alerts?.toLocaleString()} note={`At ≥ ${Math.round(threshold * 100)}% risk`} accent="#f6c453" />
          <Metric label="Critical" value={metrics.critical?.toLocaleString()} note="Immediate escalation" accent="#ff4d5f" />
          <Metric label="Consent eligible" value={metrics.consent_eligible?.toLocaleString()} note="Patient notification allowed" accent="#4bd4a0" />
        </section>
        <section className="split"><article className="panel wide"><div className="panel-title"><div><small>LIVE QUEUE</small><h2>Prioritized intervention queue</h2></div><span>{filteredQueue.length} orders</span></div><Queue rows={filteredQueue} onSelect={review} /></article>
        <div className="side-panels"><article className="panel"><small>RISK DISTRIBUTION</small><h2>Active alert mix</h2><Bars data={dashboard.risk_mix} /></article><article className="panel"><small>CAPACITY SIGNAL</small><h2>Resource pressure</h2><Bars data={dashboard.resource_pressure} /></article></div></section>
      </>}

      {view === "review" && <section className="panel review">
        <div className="panel-title"><div><small>CLINICAL REVIEW</small><h2>Alert detail</h2></div></div>
        {!selected ? <div className="empty">Select an order from the command center to review its risk and communication plan.</div> :
        <><div className="review-hero"><div><span className="risk-pill" style={{ background: riskColor[selected.risk.risk_level] }}>{selected.risk.risk_level}</span><h2>{selected.risk.order_id}</h2><p>{selected.order.test_code.replaceAll("_", " ")} · {selected.order.priority}</p></div><strong>{Math.round(selected.risk.breach_probability * 100)}%<small>breach risk</small></strong></div>
        <div className="metrics-grid three"><Metric label="Projected slip" value={`${selected.risk.projected_slip_hours > 0 ? "+" : ""}${selected.risk.projected_slip_hours} h`} note="Beyond committed SLA" accent="#ff4d5f" /><Metric label="Promised completion" value={selected.risk.promised_completion_time.replace("T", " ")} note="Committed time" accent="#54b8ff" /><Metric label="Estimated completion" value={selected.risk.estimated_completion_time.replace("T", " ")} note="Current estimate" accent="#f6c453" /></div>
        <div className="review-grid"><article><small>WHY THIS ALERT FIRED</small>{selected.risk.reasons.map(x => <p className="reason" key={x}>{x}</p>)}<div className="recommend">{selected.risk.recommended_action}</div></article><article><small>PATIENT COMMUNICATION</small><h3>{selected.notification.status.replaceAll("_", " ")}</h3><p className="notification">{selected.notification.message || "Patient communication is blocked because consent is unavailable."}</p></article></div></>}
      </section>}

      {view === "trigger" && <section className="trigger-grid"><form className="panel" onSubmit={simulate}><small>LOCAL SIMULATION</small><h2>Enter checkpoint inputs</h2><div className="form-grid">
        {["order_id", "patient_id"].map(name => <label key={name}>{name.replaceAll("_", " ")}<input value={form[name]} onChange={e => setForm({ ...form, [name]: e.target.value })} /></label>)}
        <label>Test<select value={form.test_code} onChange={e => setForm({ ...form, test_code: e.target.value })}>{options.test_codes.map(x => <option key={x}>{x}</option>)}</select></label>
        <label>Category<select value={form.test_category} onChange={e => setForm({ ...form, test_category: e.target.value })}>{options.test_categories.map(x => <option key={x}>{x}</option>)}</select></label>
        <label>Priority<select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value })}>{options.priorities.map(x => <option key={x}>{x}</option>)}</select></label>
        {[["promised_completion_window_hours","Promised SLA hours"],["elapsed_at_checkpoint_hours","Elapsed checkpoint hours"],["expected_remaining_hours","Expected remaining hours"]].map(([name,label]) => <label key={name}>{label}<input type="number" step=".5" value={form[name]} onChange={e => setForm({ ...form, [name]: Number(e.target.value) })} /></label>)}
        <label className="check"><input type="checkbox" checked={form.on_track_at_checkpoint} onChange={e => setForm({ ...form, on_track_at_checkpoint: e.target.checked })} /> Checkpoint is on track</label>
        <label className="check"><input type="checkbox" checked={form.notification_opt_in} onChange={e => setForm({ ...form, notification_opt_in: e.target.checked })} /> Patient consent available</label>
        <label className="full">Operations recipient<input type="email" value={form.recipient} onChange={e => setForm({ ...form, recipient: e.target.value })} /></label>
      </div><button className="primary" type="submit">Calculate risk</button></form>
      <article className="panel result"><small>RISK RESULT</small><h2>Simulation output</h2>{!simulation ? <div className="empty">Provide checkpoint inputs and calculate risk.</div> : <><div className="risk-orb" style={{ "--risk": riskColor[simulation.risk.risk_level] }}><strong>{Math.round(simulation.risk.breach_probability * 100)}%</strong><span>{simulation.risk.risk_level} risk</span></div><h3>{simulation.risk.projected_slip_hours > 0 ? `Projected ${simulation.risk.projected_slip_hours} hours late` : "Projected within SLA"}</h3>{simulation.risk.reasons.map(x => <p className="reason" key={x}>{x}</p>)}<div className="trigger-actions"><button className="primary" onClick={() => trigger("local")}>Trigger local alert</button><button onClick={() => trigger("smtp")}>Send SMTP alert</button></div></>}</article></section>}

      {view === "delivery" && <section className="panel"><small>DELIVERY & AUTOMATION</small><h2>Operational setup</h2><div className="delivery-cards"><article><b>Local outbox</b><p>Safe demo delivery. Trigger Lab writes a standards-compliant .eml file into runtime/outbox.</p><span className="ready">Ready</span></article><article><b>SMTP operations mailbox</b><p>Configure SMTP environment variables, then send directly to diagnostics operations.</p><span>Requires configuration</span></article><article><b>Continuous watcher</b><p>Run the watcher on a VM or schedule a Cloud Run Job to scan for new alerts.</p><code>python watch_alerts.py --send</code></article></div></section>}
    </main>
  </div>;
}

export default App;
