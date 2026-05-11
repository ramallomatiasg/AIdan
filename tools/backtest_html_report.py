"""
backtest_html_report.py — convierte el output JSON+CSV de backtest_h1_m15.py
en un HTML interactivo con sliders, charts, y stats recomputables client-side.

Inspirado en el approach de Thariq (Anthropic) — HTML como output format de
documentos generados por IA, en lugar de Markdown plano. Densidad info >>>,
interactividad (sliders/knobs), shareable (un solo archivo .html portable).

Features del report:
- Sliders min_confidence (filtrar signals con conf >= X client-side)
- Checkboxes setup_type (toggle setups individuales)
- Filter direction (CALL / PUT / both)
- Equity curve chart por timeframe (cumulative pips)
- Breakdown setup_type table que recomputa en filtro change
- Summary stats (WR/PF/avg pips) live
- Comparativa M15 vs H1 lado a lado

Uso:
    python tools/backtest_html_report.py                   # usa latest JSON+CSV
    python tools/backtest_html_report.py --json FILE.json --csv FILE.csv

Output: backtest_h1_m15_TIMESTAMP.html (open en cualquier browser, no requiere server)
"""
import argparse
import csv
import glob
import json
import os
import sys
from datetime import datetime
from html import escape

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def find_latest_pair():
    """Encuentra el JSON + CSV mas reciente del backtest."""
    jsons = sorted(glob.glob(os.path.join(ROOT, 'backtest_h1_m15_*.json')))
    csvs = sorted(glob.glob(os.path.join(ROOT, 'backtest_h1_m15_*.csv')))
    if not jsons or not csvs:
        return None, None
    return jsons[-1], csvs[-1]


def load_signals(csv_path):
    signals = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        for row in csv.DictReader(f):
            try:
                signals.append({
                    'tf': row['tf'],
                    'step': int(row['step']),
                    'datetime': row['datetime'],
                    'direction': row['direction'],
                    'confidence': float(row['confidence']) if row['confidence'] else 0.0,
                    'setup_type': row['setup_type'],
                    'entry_price': float(row['entry_price']) if row['entry_price'] else 0.0,
                    'result': row['result'],
                    'pips': float(row['pips']) if row['pips'] else 0.0,
                    'reason': row['reason'],
                })
            except Exception:
                continue
    return signals


def build_html(stats, signals, json_name, csv_name):
    """Build a single self-contained HTML page."""
    data_js = json.dumps({'stats': stats, 'signals': signals}, ensure_ascii=False)
    title = f"AIdan Backtest H1 + M15 — {datetime.now().strftime('%Y-%m-%d')}"

    return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>{escape(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0a0a0a; --panel: #111; --panel2: #161616; --border: #1a1a1a;
    --text: #e8ecf2; --muted: #999; --accent: #4f8ff7;
    --green: #00f5a0; --red: #ff4466; --yellow: #ffcc00; --purple: #a78bfa;
    --radius: 14px;
  }}
  * {{ box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; margin: 0; padding: 24px; line-height: 1.5; }}
  h1 {{ font-size: 24px; margin: 0 0 4px 0; }}
  .sub {{ color: var(--muted); font-size: 13px; margin-bottom: 24px; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .panel {{ background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 20px; }}
  .panel h2 {{ margin: 0 0 12px 0; font-size: 16px; display: flex; align-items: center; gap: 8px; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 6px; font-size: 11px; font-weight: 600; background: var(--accent); color: #fff; }}
  .badge.gold {{ background: var(--yellow); color: #000; }}
  .badge.purple {{ background: var(--purple); color: #fff; }}
  .controls {{ background: var(--panel2); border-radius: 10px; padding: 16px; margin-bottom: 20px; }}
  .control-row {{ display: flex; gap: 24px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }}
  .control-row:last-child {{ margin-bottom: 0; }}
  .control-row label {{ font-size: 13px; color: var(--muted); margin-right: 8px; }}
  .control-row input[type=range] {{ width: 200px; vertical-align: middle; }}
  .control-row .val {{ display: inline-block; min-width: 50px; font-variant-numeric: tabular-nums; color: var(--text); font-weight: 600; margin-left: 8px; }}
  .control-row .reset-btn {{ background: var(--panel2); color: var(--text); border: 1px solid var(--border); padding: 6px 14px; border-radius: 8px; cursor: pointer; font-size: 12px; }}
  .control-row .reset-btn:hover {{ background: var(--bg); border-color: var(--accent); }}
  .stats-row {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 18px; }}
  .stat {{ background: var(--panel2); border-radius: 10px; padding: 12px; text-align: center; }}
  .stat .label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }}
  .stat .value {{ font-size: 22px; font-weight: 600; margin-top: 4px; font-variant-numeric: tabular-nums; }}
  .stat .value.green {{ color: var(--green); }}
  .stat .value.red {{ color: var(--red); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th, td {{ padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 500; font-size: 11px; text-transform: uppercase; }}
  td.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  td.green {{ color: var(--green); }}
  td.red {{ color: var(--red); }}
  .setup-toggle {{ display: inline-flex; align-items: center; gap: 6px; background: var(--panel2); padding: 4px 10px; border-radius: 6px; margin: 4px 4px 4px 0; cursor: pointer; font-size: 12px; user-select: none; transition: all 0.2s; border: 1px solid var(--border); }}
  .setup-toggle:hover {{ border-color: var(--accent); }}
  .setup-toggle.off {{ opacity: 0.4; }}
  .setup-toggle input {{ accent-color: var(--accent); }}
  .chart-wrap {{ position: relative; height: 320px; }}
  .dir-btn {{ background: var(--panel2); border: 1px solid var(--border); color: var(--text); padding: 6px 12px; border-radius: 6px; cursor: pointer; font-size: 12px; }}
  .dir-btn.active {{ background: var(--accent); border-color: var(--accent); }}
  .caveat {{ background: rgba(255,204,0,0.05); border-left: 3px solid var(--yellow); padding: 10px 14px; border-radius: 4px; font-size: 12px; color: var(--muted); margin: 12px 0; }}
  .caveat strong {{ color: var(--yellow); }}
</style>
</head>
<body>
  <h1>AIdan Backtest H1 + M15 — Interactive Report</h1>
  <div class="sub">Generated from <code>{escape(os.path.basename(json_name))}</code> + <code>{escape(os.path.basename(csv_name))}</code> · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>

  <div class="caveat">
    <strong>Caveats:</strong> Solo trigger <code>structure</code> (sin news/calendar/pre_planned/smc-live). Sin spread variable, slippage, latency. AutoTuner params actuales sobre data vieja (mild leakage). Backtest infla metricas 20-30% vs real. <strong>Indicativo, no decisivo.</strong>
  </div>

  <div class="controls">
    <div class="control-row">
      <label>Min confidence:</label>
      <input type="range" id="minConf" min="0" max="100" step="1" value="60">
      <span class="val" id="minConfVal">60</span>

      <label style="margin-left: 24px;">Direccion:</label>
      <button class="dir-btn active" data-dir="both">Ambas</button>
      <button class="dir-btn" data-dir="CALL">CALL</button>
      <button class="dir-btn" data-dir="PUT">PUT</button>

      <button class="reset-btn" id="resetBtn" style="margin-left: auto;">Reset filtros</button>
    </div>
    <div class="control-row">
      <label>Setup types (click para toggle):</label>
      <div id="setupToggles" style="display: flex; flex-wrap: wrap; gap: 4px;"></div>
    </div>
  </div>

  <div class="grid">
    <div class="panel">
      <h2><span class="badge gold">M15</span> Track B</h2>
      <div class="stats-row" id="m15Stats"></div>
      <div class="chart-wrap"><canvas id="m15Chart"></canvas></div>
      <h2 style="margin-top: 24px; font-size: 14px;">Breakdown setup_type</h2>
      <table id="m15Table"></table>
    </div>
    <div class="panel">
      <h2><span class="badge purple">H1</span> Track C</h2>
      <div class="stats-row" id="h1Stats"></div>
      <div class="chart-wrap"><canvas id="h1Chart"></canvas></div>
      <h2 style="margin-top: 24px; font-size: 14px;">Breakdown setup_type</h2>
      <table id="h1Table"></table>
    </div>
  </div>

  <div class="panel" style="margin-top: 20px;">
    <h2>Comparativa M15 vs H1</h2>
    <div class="chart-wrap" style="height: 280px;"><canvas id="compareChart"></canvas></div>
  </div>

<script>
const DATA = {data_js};
let currentDir = 'both';
let currentMinConf = 60;
let enabledSetups = new Set();
let charts = {{}};

function init() {{
  const allSetups = new Set();
  DATA.signals.forEach(s => allSetups.add(s.setup_type));
  enabledSetups = new Set(allSetups);

  // Build setup toggles
  const togWrap = document.getElementById('setupToggles');
  togWrap.innerHTML = '';
  [...allSetups].sort().forEach(st => {{
    const lbl = document.createElement('label');
    lbl.className = 'setup-toggle';
    lbl.innerHTML = `<input type="checkbox" checked data-setup="${{st}}"> ${{st}}`;
    togWrap.appendChild(lbl);
    lbl.querySelector('input').addEventListener('change', e => {{
      if (e.target.checked) {{
        enabledSetups.add(st);
        lbl.classList.remove('off');
      }} else {{
        enabledSetups.delete(st);
        lbl.classList.add('off');
      }}
      recompute();
    }});
  }});

  // Slider
  const minConfEl = document.getElementById('minConf');
  const minConfVal = document.getElementById('minConfVal');
  minConfEl.addEventListener('input', e => {{
    currentMinConf = parseInt(e.target.value);
    minConfVal.textContent = currentMinConf;
    recompute();
  }});

  // Direction
  document.querySelectorAll('.dir-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      document.querySelectorAll('.dir-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      currentDir = btn.dataset.dir;
      recompute();
    }});
  }});

  // Reset
  document.getElementById('resetBtn').addEventListener('click', () => {{
    currentMinConf = 60;
    minConfEl.value = 60;
    minConfVal.textContent = '60';
    currentDir = 'both';
    document.querySelectorAll('.dir-btn').forEach(b => b.classList.toggle('active', b.dataset.dir === 'both'));
    enabledSetups = new Set(allSetups);
    document.querySelectorAll('#setupToggles input').forEach(cb => {{
      cb.checked = true;
      cb.closest('.setup-toggle').classList.remove('off');
    }});
    recompute();
  }});

  recompute();
}}

function filterSignals(tf) {{
  return DATA.signals.filter(s =>
    s.tf === tf &&
    s.confidence >= currentMinConf &&
    (currentDir === 'both' || s.direction === currentDir) &&
    enabledSetups.has(s.setup_type)
  );
}}

function computeStats(signals) {{
  const n = signals.length;
  if (n === 0) return {{ n: 0, wr: 0, pf: 0, total: 0, avg: 0, gw: 0, gl: 0 }};
  const wins = signals.filter(s => s.pips > 0).length;
  const total = signals.reduce((a, s) => a + s.pips, 0);
  const gw = signals.filter(s => s.pips > 0).reduce((a, s) => a + s.pips, 0);
  const gl = Math.abs(signals.filter(s => s.pips < 0).reduce((a, s) => a + s.pips, 0));
  return {{
    n, wr: (wins / n * 100), pf: gl > 0 ? gw / gl : Infinity,
    total, avg: total / n, gw, gl,
  }};
}}

function renderStats(elId, st) {{
  const el = document.getElementById(elId);
  const pfStr = isFinite(st.pf) ? st.pf.toFixed(2) : '∞';
  const verdict = st.pf >= 1.2 ? 'green' : st.pf >= 1.0 ? '' : 'red';
  el.innerHTML = `
    <div class="stat"><div class="label">Signals</div><div class="value">${{st.n}}</div></div>
    <div class="stat"><div class="label">WR%</div><div class="value">${{st.wr.toFixed(1)}}</div></div>
    <div class="stat"><div class="label">PF</div><div class="value ${{verdict}}">${{pfStr}}</div></div>
    <div class="stat"><div class="label">Total pips</div><div class="value ${{st.total > 0 ? 'green' : st.total < 0 ? 'red' : ''}}">${{st.total >= 0 ? '+' : ''}}${{st.total.toFixed(1)}}</div></div>
    <div class="stat"><div class="label">Avg/trade</div><div class="value">${{st.avg.toFixed(2)}}</div></div>
  `;
}}

function renderTable(elId, signals) {{
  const el = document.getElementById(elId);
  const bySetup = {{}};
  signals.forEach(s => {{
    if (!bySetup[s.setup_type]) bySetup[s.setup_type] = {{ count: 0, wins: 0, pips: 0 }};
    bySetup[s.setup_type].count++;
    if (s.pips > 0) bySetup[s.setup_type].wins++;
    bySetup[s.setup_type].pips += s.pips;
  }});
  const rows = Object.entries(bySetup)
    .sort((a, b) => b[1].count - a[1].count)
    .map(([st, d]) => {{
      const wr = d.count > 0 ? (d.wins / d.count * 100) : 0;
      const wrClass = wr >= 55 ? 'green' : wr <= 40 ? 'red' : '';
      const pipsClass = d.pips > 0 ? 'green' : d.pips < 0 ? 'red' : '';
      return `<tr>
        <td>${{st}}</td>
        <td class="num">${{d.count}}</td>
        <td class="num ${{wrClass}}">${{wr.toFixed(0)}}%</td>
        <td class="num ${{pipsClass}}">${{d.pips >= 0 ? '+' : ''}}${{d.pips.toFixed(1)}}</td>
      </tr>`;
    }}).join('');
  el.innerHTML = `<thead><tr><th>Setup type</th><th class="num">Count</th><th class="num">WR%</th><th class="num">Pips</th></tr></thead><tbody>${{rows || '<tr><td colspan="4" style="text-align:center;color:var(--muted)">Sin signals con estos filtros</td></tr>'}}</tbody>`;
}}

function renderEquityChart(elId, signals, color) {{
  const ctx = document.getElementById(elId).getContext('2d');
  const sorted = [...signals].sort((a, b) => a.step - b.step);
  let cum = 0;
  const equity = sorted.map(s => {{ cum += s.pips; return cum; }});
  const labels = sorted.map((_, i) => i + 1);

  if (charts[elId]) charts[elId].destroy();
  charts[elId] = new Chart(ctx, {{
    type: 'line',
    data: {{
      labels,
      datasets: [{{
        label: 'Cumulative pips', data: equity,
        borderColor: color, backgroundColor: color + '20',
        fill: true, tension: 0.1, pointRadius: 0, borderWidth: 2,
      }}]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: '#999', maxTicksLimit: 8 }}, grid: {{ color: '#1a1a1a' }}, title: {{ display: true, text: 'Signal #', color: '#999' }} }},
        y: {{ ticks: {{ color: '#999' }}, grid: {{ color: '#1a1a1a' }}, title: {{ display: true, text: 'Pips acumulados', color: '#999' }} }},
      }},
    }}
  }});
}}

function renderCompareChart() {{
  const ctx = document.getElementById('compareChart').getContext('2d');
  const m15 = computeStats(filterSignals('M15'));
  const h1 = computeStats(filterSignals('H1'));

  if (charts.compareChart) charts.compareChart.destroy();
  charts.compareChart = new Chart(ctx, {{
    type: 'bar',
    data: {{
      labels: ['Signals', 'WR %', 'PF', 'Total pips', 'Avg pips'],
      datasets: [
        {{ label: 'M15', data: [m15.n, m15.wr, m15.pf, m15.total, m15.avg * 100], backgroundColor: '#ffcc0080', borderColor: '#ffcc00', borderWidth: 1 }},
        {{ label: 'H1', data: [h1.n, h1.wr, h1.pf, h1.total, h1.avg * 100], backgroundColor: '#a78bfa80', borderColor: '#a78bfa', borderWidth: 1 }},
      ]
    }},
    options: {{
      responsive: true, maintainAspectRatio: false, indexAxis: 'y',
      plugins: {{ legend: {{ labels: {{ color: '#e8ecf2' }} }} }},
      scales: {{
        x: {{ ticks: {{ color: '#999' }}, grid: {{ color: '#1a1a1a' }} }},
        y: {{ ticks: {{ color: '#999' }}, grid: {{ color: '#1a1a1a' }} }},
      }},
    }}
  }});
}}

function recompute() {{
  const m15Signals = filterSignals('M15');
  const h1Signals = filterSignals('H1');
  renderStats('m15Stats', computeStats(m15Signals));
  renderStats('h1Stats', computeStats(h1Signals));
  renderTable('m15Table', m15Signals);
  renderTable('h1Table', h1Signals);
  renderEquityChart('m15Chart', m15Signals, '#ffcc00');
  renderEquityChart('h1Chart', h1Signals, '#a78bfa');
  renderCompareChart();
}}

const allSetups = new Set();
init();
</script>
</body>
</html>
"""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', default=None)
    parser.add_argument('--csv', default=None)
    parser.add_argument('--out', default=None)
    args = parser.parse_args()

    if args.json and args.csv:
        json_path, csv_path = args.json, args.csv
    else:
        json_path, csv_path = find_latest_pair()
        if not json_path:
            print("ERROR: no backtest JSON/CSV found in project root.")
            print("Run `python tools/backtest_h1_m15.py` first.")
            sys.exit(1)

    print(f"Loading stats from : {json_path}")
    print(f"Loading signals from: {csv_path}")

    with open(json_path, 'r', encoding='utf-8') as f:
        stats = json.load(f)
    signals = load_signals(csv_path)
    print(f"  Loaded {len(signals)} signals total")

    html = build_html(stats, signals, json_path, csv_path)

    out_path = args.out or os.path.join(
        ROOT,
        f'backtest_h1_m15_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html'
    )
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    size_kb = os.path.getsize(out_path) / 1024
    print(f"\nHTML report: {out_path}  ({size_kb:.1f} KB)")
    print(f"Abre en cualquier browser. Standalone, no requiere server.")


if __name__ == '__main__':
    main()
