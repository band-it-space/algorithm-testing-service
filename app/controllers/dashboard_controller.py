"""
Custom optimization dashboard served as an HTML page.
Auto-polls the status API and displays progress, ETA, skipped genomes, toxic params.
"""
import logging
from fastapi import APIRouter
from fastapi.responses import HTMLResponse

logger = logging.getLogger(__name__)

dashboard_router = APIRouter(tags=["dashboard"])

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Optimization Dashboard</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #0f1923; color: #e0e6ed; padding: 24px; }
  h1 { text-align: center; margin-bottom: 24px; color: #4fc3f7; font-size: 1.6rem; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; max-width: 1100px; margin: 0 auto; }
  .card { background: #1a2733; border-radius: 10px; padding: 20px; border: 1px solid #2a3a4a; }
  .card h2 { font-size: 1rem; color: #90a4ae; margin-bottom: 14px; text-transform: uppercase; letter-spacing: 1px; }
  .card.full { grid-column: 1 / -1; }
  .metric { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid #2a3a4a; }
  .metric:last-child { border-bottom: none; }
  .metric .label { color: #78909c; font-size: 0.9rem; }
  .metric .value { font-weight: 600; font-size: 1.05rem; color: #e0e6ed; }
  .metric .value.highlight { color: #4fc3f7; font-size: 1.3rem; }
  .metric .value.green { color: #66bb6a; }
  .metric .value.orange { color: #ffa726; }
  .metric .value.red { color: #ef5350; }

  .progress-bar-container { width: 100%; background: #263238; border-radius: 8px; height: 28px; margin: 12px 0; overflow: hidden; position: relative; }
  .progress-bar { height: 100%; background: linear-gradient(90deg, #0288d1, #4fc3f7); border-radius: 8px; transition: width 0.6s ease; min-width: 0; }
  .progress-bar-text { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-weight: 700; font-size: 0.85rem; color: #fff; text-shadow: 0 1px 2px rgba(0,0,0,0.5); }

  .status-badge { display: inline-block; padding: 4px 12px; border-radius: 12px; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; }
  .status-running { background: #1b5e20; color: #a5d6a7; }
  .status-completed { background: #0d47a1; color: #90caf9; }
  .status-cancelled { background: #b71c1c; color: #ef9a9a; }
  .status-pending { background: #e65100; color: #ffcc80; }

  table { width: 100%; border-collapse: collapse; margin-top: 8px; }
  th { text-align: left; padding: 8px 10px; color: #90a4ae; font-size: 0.8rem; text-transform: uppercase; border-bottom: 2px solid #2a3a4a; }
  td { padding: 7px 10px; font-size: 0.88rem; border-bottom: 1px solid #2a3a4a; }

  .no-data { text-align: center; color: #546e7a; padding: 40px; font-size: 1rem; }
  .refresh-info { text-align: center; color: #546e7a; font-size: 0.75rem; margin-top: 16px; }
  #opt-select { margin: 0 auto 20px; display: block; padding: 8px 16px; background: #1a2733; color: #e0e6ed; border: 1px solid #4fc3f7; border-radius: 6px; font-size: 0.95rem; cursor: pointer; }
  #opt-select option { background: #1a2733; }
</style>
</head>
<body>
<h1>Optimization Dashboard</h1>
<select id="opt-select"><option value="">Loading optimizations...</option></select>
<div id="dashboard" class="no-data">Select an optimization to monitor</div>
<div class="refresh-info" id="refresh-info"></div>

<script>
const API = '/api/v1';
let currentOptId = null;
let pollTimer = null;

async function loadOptimizations() {
    try {
        const res = await fetch(`${API}/optimizations?limit=20`);
        const data = await res.json();
        const sel = document.getElementById('opt-select');
        sel.innerHTML = '<option value="">-- Select optimization --</option>';
        data.forEach(opt => {
            const o = document.createElement('option');
            o.value = opt.optimization_id;
            const pct = opt.progress_percent || 0;
            o.textContent = `${opt.optimization_id} [${opt.status}] ${pct}% — ${opt.stock_codes.join(',')}`;
            sel.appendChild(o);
        });
        // Auto-select the most recent running one
        const running = data.find(o => o.status === 'running');
        if (running) {
            sel.value = running.optimization_id;
            selectOpt(running.optimization_id);
        } else if (data.length > 0) {
            sel.value = data[0].optimization_id;
            selectOpt(data[0].optimization_id);
        }
    } catch(e) { console.error('Failed to load optimizations', e); }
}

function selectOpt(id) {
    currentOptId = id;
    if (pollTimer) clearInterval(pollTimer);
    if (!id) { document.getElementById('dashboard').innerHTML = '<div class="no-data">Select an optimization</div>'; return; }
    pollStatus();
    pollTimer = setInterval(pollStatus, 3000);
}

document.getElementById('opt-select').addEventListener('change', e => selectOpt(e.target.value));

async function pollStatus() {
    if (!currentOptId) return;
    try {
        const res = await fetch(`${API}/optimization/${currentOptId}/status`);
        if (!res.ok) throw new Error(res.statusText);
        const d = await res.json();
        renderDashboard(d);
        document.getElementById('refresh-info').textContent = 'Auto-refresh every 3s — Last: ' + new Date().toLocaleTimeString();
        if (d.status === 'completed' || d.status === 'cancelled') {
            clearInterval(pollTimer);
            document.getElementById('refresh-info').textContent += ' (stopped — optimization finished)';
        }
    } catch(e) { console.error('Poll error', e); }
}

function statusClass(s) {
    if (s === 'running') return 'status-running';
    if (s === 'completed') return 'status-completed';
    if (s === 'cancelled') return 'status-cancelled';
    return 'status-pending';
}

function fmtElapsed(sec) {
    if (!sec) return '—';
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    const h = Math.floor(m / 60);
    const mm = m % 60;
    if (h > 0) return `${h}h ${mm}m ${s}s`;
    if (mm > 0) return `${mm}m ${s}s`;
    return `${s}s`;
}

function renderDashboard(d) {
    const sf = d.smart_filtering || {};
    const skipped = sf.genomes_skipped || 0;
    const elim = sf.eliminated_params || [];
    const pct = d.progress_percent || 0;

    let html = '<div class="grid">';

    // — Progress card —
    html += `<div class="card full">
        <h2>Progress</h2>
        <div class="progress-bar-container">
            <div class="progress-bar" style="width:${pct}%"></div>
            <div class="progress-bar-text">${pct}%</div>
        </div>
        <div class="metric"><span class="label">Status</span><span class="value"><span class="${statusClass(d.status)} status-badge">${d.status}</span></span></div>
        <div class="metric"><span class="label">Tasks</span><span class="value highlight">${d.completed_tasks} / ${d.total_tasks}</span></div>
        <div class="metric"><span class="label">Failed</span><span class="value ${d.failed_tasks > 0 ? 'red' : ''}">${d.failed_tasks}</span></div>
        <div class="metric"><span class="label">Elapsed</span><span class="value">${fmtElapsed(d.elapsed_seconds)}</span></div>
        <div class="metric"><span class="label">ETA</span><span class="value orange">${d.eta_formatted || '—'}</span></div>
    </div>`;

    // — Info card —
    html += `<div class="card">
        <h2>Optimization Info</h2>
        <div class="metric"><span class="label">ID</span><span class="value">${d.optimization_id}</span></div>
        <div class="metric"><span class="label">Total Genomes</span><span class="value">${d.total_genomes}</span></div>
        <div class="metric"><span class="label">Stocks</span><span class="value">${d.stock_codes.join(', ')}</span></div>
        <div class="metric"><span class="label">Created</span><span class="value">${d.created_at}</span></div>
    </div>`;

    // — Smart filtering card —
    html += `<div class="card">
        <h2>Smart Filtering</h2>`;
    if (!sf.enabled) {
        html += `<div class="metric"><span class="label">Status</span><span class="value">Disabled</span></div>`;
    } else {
        html += `
        <div class="metric"><span class="label">Genomes Skipped</span><span class="value green">${skipped}</span></div>
        <div class="metric"><span class="label">Toxic Params Found</span><span class="value orange">${elim.length}</span></div>`;
    }
    html += `</div>`;

    // — Toxic params table —
    if (elim.length > 0) {
        html += `<div class="card full"><h2>Eliminated Toxic Parameters</h2><table>
            <tr><th>Parameter</th><th>Value</th><th>Method</th><th>Observations</th><th>After Genome</th></tr>`;
        elim.forEach(p => {
            html += `<tr><td>${p.param}</td><td>${p.value}</td><td>${p.method}</td><td>${p.observations}</td><td>${p.after_genome}</td></tr>`;
        });
        html += `</table></div>`;
    }

    html += '</div>';
    document.getElementById('dashboard').innerHTML = html;
    document.getElementById('dashboard').classList.remove('no-data');
}

loadOptimizations();
</script>
</body>
</html>
"""


@dashboard_router.get("/dashboard", response_class=HTMLResponse)
async def optimization_dashboard():
    """Serve the optimization monitoring dashboard."""
    return DASHBOARD_HTML
