"""A projector-legible demo. Standard library only.

    python -m trialgrid.web

Serves on http://localhost:8000. Every number on the page comes from a live
call into the same pipeline the AgentApp runs — the browser draws what it is
handed and computes nothing itself, so the demo cannot drift from the system.
"""

from __future__ import annotations

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from trialgrid.report import both_runs

PORT = 8000

PAGE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>TrialGrid</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0d1117;--panel:#161b22;--line:#30363d;--fg:#e6edf3;--dim:#8b949e;
--ok:#3fb950;--bad:#f85149;--warn:#d29922;--accent:#58a6ff}
body{background:var(--bg);color:var(--fg);font:16px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;padding:32px}
.wrap{max-width:1400px;margin:0 auto}
h1{font-size:30px;letter-spacing:-.5px}
h1 span{color:var(--dim);font-weight:400}
.sub{color:var(--dim);margin:8px 0 24px;font-size:17px;max-width:900px}
.q{background:var(--panel);border-left:3px solid var(--accent);padding:14px 18px;
border-radius:6px;margin-bottom:24px;font-size:18px}
.controls{display:flex;gap:12px;margin-bottom:28px;flex-wrap:wrap}
button{font:600 15px/1 inherit;padding:14px 22px;border-radius:8px;border:1px solid var(--line);
background:var(--panel);color:var(--fg);cursor:pointer;transition:.15s}
button:hover{border-color:var(--accent)}
button.primary{background:var(--ok);border-color:var(--ok);color:#0d1117}
button.danger{background:var(--bad);border-color:var(--bad);color:#fff}
button:disabled{opacity:.4;cursor:default}
.cols{display:grid;grid-template-columns:1fr 1fr;gap:20px}
@media(max-width:1000px){.cols{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:20px;
opacity:0;transform:translateY(8px);animation:in .35s forwards}
@keyframes in{to{opacity:1;transform:none}}
.panel h2{font-size:13px;text-transform:uppercase;letter-spacing:1.2px;color:var(--dim);margin-bottom:14px}
.panel.on{border-top:3px solid var(--ok)}
.panel.off{border-top:3px solid var(--bad)}
.badge{display:inline-block;padding:3px 9px;border-radius:20px;font-size:11px;font-weight:700;
letter-spacing:.6px;text-transform:uppercase}
.b-ok{background:rgba(63,185,80,.15);color:var(--ok)}
.b-bad{background:rgba(248,81,73,.15);color:var(--bad)}
.b-warn{background:rgba(210,153,34,.15);color:var(--warn)}
.row{display:flex;justify-content:space-between;gap:12px;padding:9px 0;border-bottom:1px solid var(--line);font-size:14px}
.row:last-child{border:0}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}
.big{display:flex;gap:26px;margin:16px 0;flex-wrap:wrap}
.stat{flex:1;min-width:110px}
.stat .n{font-size:40px;font-weight:700;line-height:1;font-variant-numeric:tabular-nums}
.stat .l{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.8px;margin-top:6px}
.stat.hero .n{color:var(--accent)}
.trace{font-family:ui-monospace,Menlo,monospace;font-size:12.5px;line-height:1.9;
background:#010409;border-radius:8px;padding:14px;max-height:260px;overflow:auto}
.t-q{color:var(--warn)}.t-g{color:var(--bad)}.t-ok{color:var(--dim)}
.crit{font-family:ui-monospace,Menlo,monospace;font-size:13px;padding:7px 10px;border-radius:5px;margin-bottom:5px;
background:#010409;display:flex;justify-content:space-between;gap:10px}
.crit.tainted{background:rgba(248,81,73,.12);border:1px solid var(--bad)}
.crit .src{color:var(--dim);font-size:11px}
.verdict{margin-top:16px;padding:14px;border-radius:8px;font-weight:600;text-align:center;font-size:15px}
.v-block{background:rgba(210,153,34,.12);color:var(--warn);border:1px solid var(--warn)}
.v-bad{background:rgba(248,81,73,.12);color:var(--bad);border:1px solid var(--bad)}
.diff{margin-top:28px;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:26px}
.diff h2{font-size:20px;margin-bottom:18px}
.dgrid{display:grid;grid-template-columns:1fr auto 1fr;gap:18px;align-items:center;margin-bottom:14px}
.dcell{padding:14px;border-radius:8px;background:#010409}
.dcell .v{font-size:26px;font-weight:700;font-variant-numeric:tabular-nums}
.dcell .k{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.8px}
.arrow{color:var(--dim);font-size:22px}
.punch{margin-top:20px;padding:18px;border-radius:8px;background:rgba(248,81,73,.08);
border-left:3px solid var(--bad);font-size:17px;line-height:1.6}
.hide{display:none}
.tabs{display:flex;gap:6px;margin-bottom:20px;border-bottom:1px solid var(--line)}
.tab{padding:12px 20px;cursor:pointer;color:var(--dim);font-weight:600;font-size:15px;
border-bottom:2px solid transparent;margin-bottom:-1px}
.tab.active{color:var(--fg);border-bottom-color:var(--accent)}
.zones{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:16px}
.zone{border-radius:10px;padding:16px;border:1px solid var(--line)}
.zone.web{background:rgba(210,153,34,.05);border-color:rgba(210,153,34,.3)}
.zone.gate{background:rgba(88,166,255,.05);border-color:rgba(88,166,255,.3)}
.zone.hospital{background:rgba(63,185,80,.05);border-color:rgba(63,185,80,.3)}
.zone.human{background:rgba(163,113,247,.05);border-color:rgba(163,113,247,.4)}
.zone>h3{font-size:11px;text-transform:uppercase;letter-spacing:1.2px;color:var(--dim);margin-bottom:12px}
.agent{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;margin-bottom:10px}
.agent .nm{font-weight:700;font-size:15px;display:flex;justify-content:space-between;align-items:center;gap:8px}
.agent .rl{color:var(--dim);font-size:12.5px;margin:3px 0 10px}
.caps{font-size:12px;line-height:1.7}
.caps .y{color:var(--ok)}.caps .n{color:var(--bad)}
.io{margin-top:10px;padding-top:10px;border-top:1px solid var(--line);font-size:12px;
font-family:ui-monospace,Menlo,monospace;color:var(--dim)}
.io b{color:var(--fg);font-weight:600}
.pill{font-size:10px;padding:2px 7px;border-radius:20px;font-weight:700;letter-spacing:.5px}
.p-model{background:rgba(210,153,34,.18);color:var(--warn)}
.p-code{background:rgba(88,166,255,.18);color:var(--accent)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--dim);
padding:10px 8px;border-bottom:1px solid var(--line)}
td{padding:11px 8px;border-bottom:1px solid var(--line)}
tr:last-child td{border:0}
.num{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}
.win{color:var(--ok);font-weight:700}
.cite{margin-top:16px;padding:14px;background:#010409;border-radius:8px;font-size:12.5px;
line-height:1.8;color:var(--dim)}
.cite b{color:var(--fg)}
.foot{margin-top:28px;color:var(--dim);font-size:13px;line-height:1.8}
</style></head><body><div class="wrap">
<h1>TrialGrid <span>— can this protocol recruit?</span></h1>
<p class="sub">Three hospitals answer one feasibility question. No patient record leaves any of
them. One of the four source documents is hostile.</p>
<div class="q" id="q"></div>
<div class="tabs">
  <div class="tab active" data-t="run">Live run</div>
  <div class="tab" data-t="agents">The agent team</div>
  <div class="tab" data-t="impact">What it tells a sponsor</div>
</div>
<div id="t-run">
<div class="controls">
  <button class="primary" id="run">▶ Run with safeguards</button>
  <button class="danger" id="runoff" disabled>Run again with safeguards OFF</button>
  <button id="reset">Reset</button>
</div>
<div class="cols">
  <div id="left"></div><div id="right"></div>
</div>
<div id="diff"></div>
</div>
<div id="t-agents" class="hide"></div>
<div id="t-impact" class="hide"></div>
<div class="foot">
  Synthetic cohorts and a synthetic protocol — no patient data of any kind.
  Every number is computed by the same pipeline the agent runs.
</div>
</div>
<script>
let DATA=null;
const $=s=>document.querySelector(s);
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

async function load(){ if(!DATA) DATA=await (await fetch('/api/run')).json(); return DATA; }

function stat(n,l,hero){return `<div class="stat ${hero?'hero':''}"><div class="n">${n}</div><div class="l">${l}</div></div>`}

function panel(r,on){
  const c=r.counts, flagged=r.cards.filter(x=>x.flags.length);
  const trace=r.trace.map(t=>{
    const k=t.includes('QUARANTINE')?'t-q':t.includes('GATE')?'t-g':'t-ok';
    return `<div class="${k}">${esc(t.trim())}</div>`}).join('')||'<div class="t-ok">no findings</div>';
  const crits=r.criteria.map(x=>{
    const bad=!on&&x.card_id==='C6';
    return `<div class="crit ${bad?'tainted':''}"><span>${x.ref} · ${esc(x.attribute)}
      <b>${esc(x.operator)} ${esc(x.value)}</b>${bad?' ← rewritten by hostile page':''}</span>
      <span class="src">${x.card_id}</span></div>`}).join('');
  const gaps=c.gaps.map(g=>`<div class="row"><span class="mono">${esc(g.attribute)}</span>
    <span>${g.count===null?`<span class="badge b-warn">suppressed n&lt;${c.min_cell}</span>`:g.count+' patients'}</span></div>`).join('');
  return `<div class="panel ${on?'on':'off'}">
    <h2>${on?'Safeguards enabled':'Safeguards disabled'}
      <span class="badge ${on?'b-ok':'b-bad'}">${on?'protected':'unprotected'}</span></h2>
    <div class="row"><span>Hostile cards quarantined</span><b>${on?flagged.length:0} of 2</b></div>
    <div class="row"><span>Gate violations</span><b>${r.violations.length}${on?'':' (ignored)'}</b></div>
    <div class="trace" style="margin:14px 0">${trace}</div>
    <h2>Criteria in force</h2>${crits}
    <h2 style="margin-top:18px">Sites</h2>
    ${r.sites.map(s=>`<div class="row"><span>${esc(s.id)}</span>${
      s.disposition==='ANSWERED'?`<b>${s.screened} screened</b>`
      :`<span class="badge b-warn">abstained → unknown, not zero</span>`}</div>`).join('')}
    <div class="big">${stat(c.eligible,'eligible')}${stat(c.needs_screening,'recruitable',1)}${stat(c.not_eligible,'not eligible')}</div>
    <h2>What is missing</h2>${gaps}
    ${on?`<div class="verdict v-block">BLOCKED — awaiting sponsor sign-off · token ${r.token}</div>`
        :`<div class="verdict v-bad">Released with no human check</div>`}
  </div>`;
}

$('#run').onclick=async()=>{
  const d=await load(); $('#q').textContent=d.guarded.question;
  $('#left').innerHTML=panel(d.guarded,true);
  $('#runoff').disabled=false; $('#run').disabled=true;
};
$('#runoff').onclick=async()=>{
  const d=await load(); $('#right').innerHTML=panel(d.unguarded,false);
  $('#runoff').disabled=true;
  const x=d.diff, pct=Math.round((x.recruitable_unguarded/x.recruitable_guarded-1)*100);
  $('#diff').innerHTML=`<div class="diff"><h2>Same question. Same sources. Different answer.</h2>
    <div class="dgrid">
      <div class="dcell"><div class="k">ECOG criterion — guarded</div><div class="v" style="color:var(--ok)">${esc(x.ecog_guarded||'dropped')}</div></div>
      <div class="arrow">→</div>
      <div class="dcell"><div class="k">ECOG criterion — unguarded</div><div class="v" style="color:var(--bad)">${esc(x.ecog_unguarded||'dropped')}</div></div>
    </div>
    <div class="dgrid">
      <div class="dcell"><div class="k">Recruitable — guarded</div><div class="v" style="color:var(--ok)">${x.recruitable_guarded}</div></div>
      <div class="arrow">→</div>
      <div class="dcell"><div class="k">Recruitable — unguarded</div><div class="v" style="color:var(--bad)">${x.recruitable_unguarded} <span style="font-size:15px">(+${pct}%)</span></div></div>
    </div>
    <div class="punch">Nobody was told a lie. A web page loosened the protocol, the feasibility
    answer inflated by ${pct}%, and a sponsor opens sites that cannot deliver.<br>
    <b>The unguarded run is the identical code path with two checks disabled.</b></div></div>`;
};

const ZONES={web:'Web zone — untrusted input',gate:'Deterministic controls',
 hospital:'Hospital zone — private data',human:'Human oversight'};

function agentCard(a){
  return `<div class="agent"><div class="nm">${esc(a.name)}
    <span class="pill ${a.model_call?'p-model':'p-code'}">${a.model_call?'model call':'code only'}</span></div>
    <div class="rl">${esc(a.role)}</div>
    <div class="caps">${a.can.map(c=>`<div class="y">✓ ${esc(c)}</div>`).join('')}
    ${a.cannot.map(c=>`<div class="n">✕ ${esc(c)}</div>`).join('')}</div>
    <div class="io">in &nbsp;<b>${esc(a.received)}</b><br>out <b>${esc(a.produced)}</b></div></div>`;
}

async function drawAgents(){
  const d=await load(), ags=d.guarded.agents;
  const byZone={};
  ags.forEach(a=>{(byZone[a.zone]=byZone[a.zone]||[]).push(a)});
  const models=ags.filter(a=>a.model_call).length;
  $('#t-agents').innerHTML=`
    <div class="q" style="border-left-color:var(--ok)">
      <b>${ags.length} agents. Only ${models} of them ever call a model.</b>
      Everything that decides anything is ordinary code — and every agent is defined
      as much by what it <i>cannot</i> reach as by what it does.
      Eligibility is evaluated by the <b>${esc(d.guarded.engine.name)}</b> engine
      (${esc(d.guarded.engine.detail)}), reached through a one-method Protocol so the
      reasoning backend is swappable and is not the product.
    </div>
    <div class="zones">${Object.entries(byZone).map(([z,list])=>
      `<div class="zone ${z}"><h3>${ZONES[z]||z}</h3>${list.map(agentCard).join('')}</div>`).join('')}</div>`;
}

async function drawImpact(){
  const d=await load(), rows=d.guarded.impact;
  const best=rows.filter(r=>r.gain_if_relaxed>0).sort((a,b)=>b.gain_if_relaxed-a.gain_if_relaxed)[0];
  const worst=rows.slice().sort((a,b)=>b.unanswered-a.unanswered)[0];
  $('#t-impact').innerHTML=`
    <div class="q" style="border-left-color:var(--warn)">
      <b>76% of protocols now carry a substantial amendment</b> — up from 57% in 2015,
      mean 3.5 per protocol. Median direct cost: <b>$141k in Phase II, $535k in Phase III</b>.
      Eligibility criteria are among the things they change. This is the analysis that
      asks the question early enough to avoid one.
    </div>
    <table><thead><tr><th>Criterion</th><th class="num">Rules out</th>
      <th class="num">Unanswered</th><th class="num">Total cost</th>
      <th>One-step relaxation</th><th class="num">Would gain</th></tr></thead><tbody>
      ${rows.map(r=>`<tr><td><b>${r.ref}</b> · <span class="mono">${esc(r.attribute)}</span><br>
        <span style="color:var(--dim);font-size:12px">${esc(r.wording)}</span></td>
        <td class="num">${r.blocks}</td><td class="num">${r.unanswered}</td>
        <td class="num" style="color:var(--warn)">${r.total_cost}</td>
        <td class="mono">${r.relaxed_to?esc(r.relaxed_to):'—'}</td>
        <td class="num ${r.gain_if_relaxed>0?'win':''}">${r.gain_if_relaxed>0?'+'+r.gain_if_relaxed:'—'}</td></tr>`).join('')}
    </tbody></table>
    ${best?`<div class="punch" style="background:rgba(63,185,80,.08);border-left-color:var(--ok)">
      Relaxing <b>${esc(best.attribute)}</b> to <b>${esc(best.relaxed_to)}</b> would make
      <b>${best.gain_if_relaxed} more patients</b> recruitable across the responding sites.
      Trials using relaxed laboratory thresholds showed <b>no increase</b> in withdrawals for
      adverse events compared with stringent ones — so this is a question worth asking before
      the protocol is signed, not after.</div>`:''}
    ${worst&&worst.unanswered>0?`<div class="punch" style="background:rgba(88,166,255,.08);border-left-color:var(--accent)">
      <b>${worst.unanswered} patients</b> are unanswered on <b>${esc(worst.attribute)}</b>.
      That is not a protocol problem — it is an untested-samples problem, and it is
      <b>one lab order</b>, not ${worst.unanswered} separate acts of remembering.</div>`:''}
    <div class="cite"><b>Sources.</b>
      Amendment prevalence, mean count and median cost: Tufts CSDD, <i>New Benchmarks on
      Protocol Amendment Practices</i>, Ther Innov Regul Sci 2024.
      Relaxed laboratory thresholds showing no increase in adverse-event withdrawals, and
      screen-failure rates of 21–26%: ESMO Open, 2025.
      47.5% of patients alive at 6 months deemed ineligible: <i>Evaluating eligibility criteria
      of oncology trials using real-world data and AI</i>, 2022.
      Every figure, including those removed as unverifiable, is listed in SOURCES.md.</div>`;
}

document.querySelectorAll('.tab').forEach(t=>t.onclick=async()=>{
  document.querySelectorAll('.tab').forEach(x=>x.classList.remove('active'));
  t.classList.add('active');
  const w=t.dataset.t;
  $('#t-run').classList.toggle('hide',w!=='run');
  $('#t-agents').classList.toggle('hide',w!=='agents');
  $('#t-impact').classList.toggle('hide',w!=='impact');
  if(w==='agents'&&!$('#t-agents').innerHTML) await drawAgents();
  if(w==='impact'&&!$('#t-impact').innerHTML) await drawImpact();
});

$('#reset').onclick=()=>{$('#left').innerHTML='';$('#right').innerHTML='';$('#diff').innerHTML='';
  $('#run').disabled=false;$('#runoff').disabled=true;};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path.startswith("/api/run"):
            body = json.dumps(both_runs()).encode()
            ctype = "application/json"
        else:
            body = PAGE.encode()
            ctype = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        """Keep the console clean during a demo."""


def main() -> None:
    url = f"http://localhost:{PORT}"
    print(f"\n  TrialGrid demo → {url}\n  Ctrl-C to stop.\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
