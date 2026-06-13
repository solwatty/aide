"""Render a self-contained, interactive HTML dashboard.

Everything (data + app) is inlined into one file: it opens straight in a browser,
needs no server and makes no network calls, so the data stays on your machine.
All leaderboards are recomputed client-side as you change the filters.
"""
from __future__ import annotations

import html as _html
import json
from datetime import timedelta

from ..analyze.attribution import attribute_clients, attribute_people
from ..analyze.keywords import stress_keywords
from ..config import Config
from ..models import MeetingStress

_CSS = """
:root{--pos:#d1495b;--neg:#3a86ff;--ink:#1d1d1f;--mut:#86868b;--line:#e8e8ed;--bg:#f5f5f7}
*{box-sizing:border-box}
body{font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:var(--ink);background:var(--bg)}
header{background:#fff;border-bottom:1px solid var(--line);padding:18px 24px}
h1{font-size:20px;margin:0 0 2px}
.sub{color:var(--mut);font-size:12px}
.wrap{max-width:1080px;margin:0 auto;padding:20px 24px}
.controls{display:flex;flex-wrap:wrap;gap:14px;align-items:end;margin-top:14px}
.controls label{display:flex;flex-direction:column;font-size:11px;color:var(--mut);gap:4px;text-transform:uppercase;letter-spacing:.03em}
.controls input,.controls select{font:13px inherit;padding:6px 8px;border:1px solid var(--line);border-radius:8px;background:#fff;color:var(--ink)}
.kpis{display:flex;gap:14px;flex-wrap:wrap;margin:18px 0}
.kpi{background:#fff;border:1px solid var(--line);border-radius:12px;padding:14px 16px;min-width:150px;flex:1}
.kpi .v{font-size:22px;font-weight:650}
.kpi .l{color:var(--mut);font-size:12px}
nav{display:flex;gap:6px;margin:6px 0 14px;flex-wrap:wrap}
nav button{font:13px inherit;padding:7px 14px;border:1px solid var(--line);background:#fff;border-radius:20px;cursor:pointer;color:var(--ink)}
nav button.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.card{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px 18px;margin-bottom:16px}
.card h2{font-size:15px;margin:0 0 12px}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
th{font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:var(--mut);cursor:pointer;user-select:none}
td.num,th.num{text-align:right}
.pos{color:var(--pos);font-weight:600}.neg{color:var(--neg)}
.tag{font-size:10px;padding:1px 7px;border-radius:9px;background:var(--bg);color:var(--mut)}
.bar{height:10px;border-radius:5px;display:inline-block;vertical-align:middle}
.muted{color:var(--mut)}
.hint{color:var(--mut);font-size:12px;margin-top:10px}
.hidden{display:none}
svg text{font:10px -apple-system,sans-serif;fill:var(--mut)}
.dot:hover{stroke:#000;stroke-width:1}
.flex{display:flex;gap:16px;flex-wrap:wrap}.flex>*{flex:1;min-width:280px}
"""

_JS = r"""
const DATA = JSON.parse(document.getElementById("aide-data").textContent);
const M = DATA.meetings;
const scored = M.filter(m=>m.hasData);
const dates = scored.map(m=>m.date).sort();
const WD = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const $ = s=>document.querySelector(s);
const avg = a=>a.length? a.reduce((x,y)=>x+y,0)/a.length : 0;
const fmtS = v=> (v>=0?"+":"")+v.toFixed(2);

// Default window: the most recent 5 working days (Mon–Fri) in the data,
// clamped to the earliest available date. Widen via the date pickers.
function lastWorkdaysStart(endStr, n){
  const pad=x=>String(x).padStart(2,"0");
  const [y,m,d]=endStr.split("-").map(Number);
  let dt=new Date(y, m-1, d), count=0;
  while(true){
    const wd=dt.getDay();
    if(wd>=1 && wd<=5){ count++; if(count>=n) break; }
    dt.setDate(dt.getDate()-1);
  }
  return `${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())}`;
}
const _end = dates[dates.length-1];
let _defStart = lastWorkdaysStart(_end, 5);
if(_defStart < dates[0]) _defStart = dates[0];
const state = {start:_defStart, end:_end, minN:DATA.minMeetingsDefault||3,
               scope:"all", search:"", tab:"overview", sort:{key:"mean",dir:-1}};

function filtered(){
  return scored.filter(m=> m.date>=state.start && m.date<=state.end);
}
function aggregate(field){
  const ms = filtered(), map=new Map();
  for(const m of ms){
    let items;
    if(field==="people") items=m.people;
    else if(field==="clients") items=m.clients.map(c=>({key:c,label:c,internal:null}));
    else items=m.keywords.map(k=>({key:k,label:k,internal:null}));
    for(const it of items){
      let a=map.get(it.key);
      if(!a){a={label:it.label,internal:it.internal,scores:[],deltas:[]};map.set(it.key,a);}
      a.label=it.label; a.scores.push(m.stress); a.deltas.push(m.deltaHR);
    }
  }
  let rows=[...map.values()].map(a=>({label:a.label,internal:a.internal,n:a.scores.length,
            mean:avg(a.scores),meanDelta:avg(a.deltas),total:a.scores.reduce((x,y)=>x+y,0)}));
  if(field==="people" && state.scope!=="all")
     rows=rows.filter(r=> state.scope==="internal"? r.internal : r.internal===false);
  rows=rows.filter(r=> r.n>=state.minN);
  if(state.search) rows=rows.filter(r=> r.label.toLowerCase().includes(state.search.toLowerCase()));
  const k=state.sort.key, d=state.sort.dir;
  rows.sort((a,b)=> (a[k]<b[k]?-1:a[k]>b[k]?1:0)*d);
  return rows;
}

// ---- charts (inline SVG) -------------------------------------------------
function hbar(rows, n=12){
  const items=rows.slice(0,n), W=460, rh=22, H=items.length*rh+10;
  const max=Math.max(0.0001,...items.map(r=>Math.abs(r.mean)));
  const x0=150, sw=W-x0-30, mid=x0+sw/2;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">`;
  s+=`<line x1="${mid}" y1="0" x2="${mid}" y2="${H-10}" stroke="#ddd"/>`;
  items.forEach((r,i)=>{
    const y=i*rh+4, w=(Math.abs(r.mean)/max)*(sw/2);
    const x=r.mean>=0?mid:mid-w, col=r.mean>=0?"#d1495b":"#3a86ff";
    s+=`<rect x="${x}" y="${y}" width="${w}" height="13" rx="3" fill="${col}"/>`;
    s+=`<text x="${x0-6}" y="${y+10}" text-anchor="end" fill="#1d1d1f">${esc(r.label).slice(0,24)}</text>`;
    s+=`<text x="${(r.mean>=0?mid+w+3:mid-w-3)}" y="${y+10}" text-anchor="${r.mean>=0?'start':'end'}">${fmtS(r.mean)}</text>`;
  });
  return s+`</svg>`;
}
function scatter(){
  const ms=filtered(); if(!ms.length) return "<p class='muted'>No meetings in range.</p>";
  const W=900,H=260,pl=36,pb=22,pt=10,pr=10;
  const t=ms.map(m=>+new Date(m.start)), t0=Math.min(...t), t1=Math.max(...t);
  const ys=ms.map(m=>m.deltaHR), y0=Math.min(0,...ys), y1=Math.max(...ys);
  const X=v=> pl+( (v-t0)/((t1-t0)||1) )*(W-pl-pr);
  const Y=v=> H-pb-((v-y0)/((y1-y0)||1))*(H-pt-pb);
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">`;
  s+=`<line x1="${pl}" y1="${Y(0)}" x2="${W-pr}" y2="${Y(0)}" stroke="#ddd"/>`;
  [y0,(y0+y1)/2,y1].forEach(v=>{ s+=`<text x="2" y="${Y(v)+3}">${v.toFixed(0)}</text>`; });
  ms.forEach(m=>{
    const c = m.stress>0.5?"#d1495b":m.stress<-0.5?"#3a86ff":"#b0883a";
    s+=`<circle class="dot" cx="${X(+new Date(m.start))}" cy="${Y(m.deltaHR)}" r="4" fill="${c}" fill-opacity="0.75"><title>${esc(m.title)} — ${m.date}, ${m.deltaHR}bpm, z=${fmtS(m.stress)}</title></circle>`;
  });
  s+=`<text x="${pl}" y="${H-4}">${ms[0].date}</text><text x="${W-pr}" y="${H-4}" text-anchor="end">${ms[ms.length-1].date}</text>`;
  return s+`</svg>`;
}
function buckets(field){ // avg stress by weekday(0..6) or hour
  const ms=filtered(), groups={};
  for(const m of ms){ const k=m[field]; (groups[k]=groups[k]||[]).push(m.stress); }
  return groups;
}
function barChart(labels, vals){
  const W=460,n=labels.length,bw=(W-30)/n,H=150,base=H-22;
  const max=Math.max(0.0001,...vals.map(Math.abs));
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">`;
  s+=`<line x1="0" y1="${base/1.4}" x2="${W}" y2="${base/1.4}" stroke="#eee"/>`;
  labels.forEach((lb,i)=>{
    const v=vals[i]||0, h=(Math.abs(v)/max)*(base/2), x=15+i*bw;
    const y=v>=0? base/1.4-h : base/1.4, col=v>=0?"#d1495b":"#3a86ff";
    s+=`<rect x="${x}" y="${y}" width="${bw*0.7}" height="${h}" rx="2" fill="${col}"/>`;
    s+=`<text x="${x+bw*0.35}" y="${base+14}" text-anchor="middle">${esc(lb)}</text>`;
  });
  return s+`</svg>`;
}
function esc(x){return (""+x).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));}

// ---- tables --------------------------------------------------------------
function table(rows, withType){
  if(!rows.length) return "<p class='muted'>Nothing meets the current filters.</p>";
  const total=rows.length; rows=rows.slice(0,60);
  const max=Math.max(...rows.map(r=>Math.abs(r.mean)))||1;
  const th=(k,l,num)=>`<th class="${num?'num':''}" data-sort="${k}">${l}${state.sort.key===k?(state.sort.dir<0?' ▾':' ▴'):''}</th>`;
  let h=`<table><thead><tr>${th('label','Name')}${th('n','Mtgs',1)}${th('mean','Stress',1)}${th('meanDelta','ΔHR',1)}${withType?'<th>Type</th>':''}<th></th></tr></thead><tbody>`;
  for(const r of rows){
    const w=(Math.abs(r.mean)/max)*90, col=r.mean>=0?'#d1495b':'#3a86ff';
    h+=`<tr><td>${esc(r.label)}</td><td class="num">${r.n}</td>`+
       `<td class="num ${r.mean>=0?'pos':'neg'}">${fmtS(r.mean)}</td>`+
       `<td class="num">${(r.meanDelta>=0?'+':'')+r.meanDelta.toFixed(1)}</td>`+
       (withType?`<td><span class="tag">${r.internal?'internal':r.internal===false?'external':'—'}</span></td>`:'')+
       `<td><span class="bar" style="width:${w}px;background:${col}"></span></td></tr>`;
  }
  h+="</tbody></table>";
  if(total>rows.length) h+=`<div class="hint">Showing top ${rows.length} of ${total}. Use search to narrow.</div>`;
  return h;
}

// ---- render --------------------------------------------------------------
function renderKPIs(){
  const ms=filtered();
  const peak=ms.reduce((a,b)=> (a&&a.deltaHR>b.deltaHR)?a:b, null);
  $("#kpis").innerHTML=
    kpi(ms.length,"meetings in range")+
    kpi(avg(ms.map(m=>m.deltaHR)).toFixed(1)+" bpm","mean ΔHR over resting")+
    kpi(peak?("+"+peak.deltaHR+" bpm"):"–","peak: "+(peak?esc(peak.title).slice(0,28):""))+
    kpi(state.start+" → "+state.end,"date window");
}
const kpi=(v,l)=>`<div class="kpi"><div class="v">${v}</div><div class="l">${l}</div></div>`;

function render(){
  renderKPIs();
  document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("active",b.dataset.tab===state.tab));
  document.querySelectorAll("[data-pane]").forEach(p=>p.classList.toggle("hidden",p.dataset.pane!==state.tab));
  $("#peopleScope").style.display = state.tab==="people"?"flex":"none";
  if(state.tab==="overview"){
    $("#scatter").innerHTML=scatter();
    const wd=buckets("weekday"); $("#wdchart").innerHTML=barChart(WD, WD.map((_,i)=>avg(wd[i]||[])));
    const hb=buckets("hour"); const hours=[...Array(24).keys()].filter(h=>h>=7&&h<=20);
    $("#hrchart").innerHTML=barChart(hours.map(h=>h+""), hours.map(h=>avg(hb[h]||[])));
  }
  if(state.tab==="people"){ const r=aggregate("people"); $("#peopleChart").innerHTML=hbar(r); $("#peopleTable").innerHTML=table(r,true); }
  if(state.tab==="clients"){ const r=aggregate("clients"); $("#clientChart").innerHTML=hbar(r); $("#clientTable").innerHTML=table(r,false); }
  if(state.tab==="topics"){ const r=aggregate("keywords"); $("#topicChart").innerHTML=hbar(r,15); $("#topicTable").innerHTML=table(r,false); }
  if(state.tab==="meetings"){ renderMeetings(); }
}
function renderMeetings(){
  let ms=filtered().slice().sort((a,b)=>b.deltaHR-a.deltaHR);
  if(state.search) ms=ms.filter(m=>m.title.toLowerCase().includes(state.search.toLowerCase()));
  let h=`<table><thead><tr><th>When</th><th>Meeting</th><th class="num">ΔHR</th><th class="num">Stress</th><th>People / clients</th></tr></thead><tbody>`;
  for(const m of ms.slice(0,200)){
    const who=[...m.people.map(p=>p.label),...m.clients].slice(0,4).join(", ");
    h+=`<tr><td class="muted">${m.date} ${String(m.hour).padStart(2,'0')}:00</td>`+
       `<td>${esc(m.title).slice(0,60)}</td>`+
       `<td class="num">${(m.deltaHR>=0?'+':'')+m.deltaHR}</td>`+
       `<td class="num ${m.stress>=0?'pos':'neg'}">${fmtS(m.stress)}</td>`+
       `<td class="muted">${esc(who)}</td></tr>`;
  }
  $("#meetingTable").innerHTML=h+"</tbody></table>";
}

// ---- wire up -------------------------------------------------------------
function bind(){
  // progressive enhancement: reveal the interactive app, drop the static fallback
  const app=document.getElementById("app"); if(app) app.style.display="";
  const fb=document.getElementById("fallback"); if(fb) fb.remove();
  $("#start").value=state.start; $("#start").min=dates[0]; $("#start").max=dates[dates.length-1];
  $("#end").value=state.end; $("#end").min=dates[0]; $("#end").max=dates[dates.length-1];
  $("#minN").value=state.minN;
  $("#start").onchange=e=>{state.start=e.target.value;render();};
  $("#end").onchange=e=>{state.end=e.target.value;render();};
  $("#minN").onchange=e=>{state.minN=+e.target.value;render();};
  $("#scope").onchange=e=>{state.scope=e.target.value;render();};
  $("#search").oninput=e=>{state.search=e.target.value;render();};
  document.querySelectorAll("nav button").forEach(b=> b.onclick=()=>{state.tab=b.dataset.tab;state.search="";$("#search").value="";render();});
  document.body.addEventListener("click",e=>{
    const th=e.target.closest("th[data-sort]"); if(!th) return;
    const k=th.dataset.sort; state.sort.dir = state.sort.key===k? -state.sort.dir : -1; state.sort.key=k; render();
  });
}
bind(); render();
"""


def _default_window(stresses: list[MeetingStress]):
    """Mirror of the JS default: the last 5 working days present in the data."""
    days = sorted({s.meeting.start.date() for s in stresses if s.has_data})
    if not days:
        return None, None
    end, d, count = days[-1], days[-1], 0
    while True:
        if d.weekday() < 5:
            count += 1
            if count >= 5:
                break
        d -= timedelta(days=1)
    return max(d, days[0]), end


def _ssr_table(title: str, tallies, with_type: bool, limit: int = 15) -> str:
    rows = []
    for t in tallies[:limit]:
        cls = "pos" if t.mean_score >= 0 else "neg"
        typ = (
            f"<td><span class='tag'>{'internal' if t.internal else 'external'}</span></td>"
            if with_type else ""
        )
        rows.append(
            f"<tr><td>{_html.escape(t.label)}</td><td class='num'>{t.n}</td>"
            f"<td class='num {cls}'>{t.mean_score:+.2f}</td>"
            f"<td class='num'>{t.mean_hr_elevation:+.1f}</td>{typ}</tr>"
        )
    body = "".join(rows) or "<tr><td class='muted'>Not enough data in this window.</td></tr>"
    extra = "<th>type</th>" if with_type else ""
    return (
        f"<div class='card'><h2>{_html.escape(title)}</h2><table>"
        f"<tr><th>name</th><th class='num'>mtgs</th><th class='num'>stress</th>"
        f"<th class='num'>ΔHR</th>{extra}</tr>{body}</table></div>"
    )


def build_fallback_html(stresses: list[MeetingStress], config: Config) -> str:
    """Static, JS-free view of the default window — shown if scripts can't run
    (e.g. a sandboxed file preview). JavaScript removes it and takes over when
    the file is opened in a real browser."""
    start, end = _default_window(stresses)
    if start is None:
        return "<div class='card muted'>No scored meetings to display.</div>"
    sub = [s for s in stresses if s.has_data and start <= s.meeting.start.date() <= end]
    people = attribute_people(sub, config)
    clients = attribute_clients(sub, config)
    keywords = stress_keywords(sub, config, top=15)
    elev = [s.hr_elevation for s in sub]
    mean_elev = sum(elev) / len(elev) if elev else 0.0
    peak = max(sub, key=lambda s: s.hr_elevation) if sub else None
    kpis = (
        f"<div class='kpi'><div class='v'>{len(sub)}</div><div class='l'>meetings ({start} → {end})</div></div>"
        f"<div class='kpi'><div class='v'>{mean_elev:+.1f} bpm</div><div class='l'>mean ΔHR over resting</div></div>"
        + (f"<div class='kpi'><div class='v'>+{peak.hr_elevation:.0f} bpm</div>"
           f"<div class='l'>peak: {_html.escape(peak.meeting.title)[:28]}</div></div>" if peak else "")
    )
    return (
        "<div class='hint' style='margin-bottom:12px'>Static view of your last 5 working days. "
        "<b>Open this file in a web browser</b> for the full interactive dashboard "
        "(date-range, filters, charts).</div>"
        f"<div class='kpis'>{kpis}</div>"
        + _ssr_table("Colleagues — who raises your stress most", people, True)
        + _ssr_table("Clients / accounts — most stressful", clients, False)
        + _ssr_table("Topics & keywords — most stress-associated", keywords, False)
    )


def render_dashboard(data: dict, fallback_html: str = "") -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>aide · stress dashboard</title><style>{_CSS}</style></head><body>
<header>
  <h1>🫀 Stress dashboard</h1>
  <div class="sub">Generated {data.get('generated','')} · {len(data.get('meetings', []))} meetings · all filtering runs locally in your browser</div>
  <div class="controls">
    <label>From<input type="date" id="start"></label>
    <label>To<input type="date" id="end"></label>
    <label>Min meetings<input type="number" id="minN" min="1" max="20" style="width:70px"></label>
    <label id="peopleScope" style="display:none">People<select id="scope">
      <option value="all">everyone</option><option value="internal">colleagues</option><option value="external">external</option>
    </select></label>
    <label>Search<input type="search" id="search" placeholder="filter…" style="width:160px"></label>
  </div>
</header>
<div class="wrap">
  <div id="fallback">{fallback_html}</div>
  <div id="app" style="display:none">
  <div class="kpis" id="kpis"></div>
  <nav>
    <button data-tab="overview" class="active">Overview</button>
    <button data-tab="people">Colleagues</button>
    <button data-tab="clients">Clients</button>
    <button data-tab="topics">Topics</button>
    <button data-tab="meetings">Meetings</button>
  </nav>

  <div data-pane="overview">
    <div class="card"><h2>Every meeting — heart-rate elevation over time</h2><div id="scatter"></div>
      <div class="hint">Each dot is a meeting. Red = activating (z&gt;0.5), blue = calming, amber = neutral. Hover for details.</div></div>
    <div class="flex">
      <div class="card"><h2>Mean stress by weekday</h2><div id="wdchart"></div></div>
      <div class="card"><h2>Mean stress by hour of day</h2><div id="hrchart"></div>
        <div class="hint">Helps separate "the meeting" from time-of-day effects (mornings, post-lunch).</div></div>
    </div>
  </div>

  <div data-pane="people" class="hidden">
    <div class="card"><h2>Colleagues by mean stress</h2><div id="peopleChart"></div></div>
    <div class="card"><div id="peopleTable"></div>
      <div class="hint">Correlation, not causation — workload and back-to-back days travel with the people in the room.</div></div>
  </div>
  <div data-pane="clients" class="hidden">
    <div class="card"><h2>Clients / accounts by mean stress</h2><div id="clientChart"></div></div>
    <div class="card"><div id="clientTable"></div></div>
  </div>
  <div data-pane="topics" class="hidden">
    <div class="card"><h2>Topics &amp; keywords by mean stress</h2><div id="topicChart"></div></div>
    <div class="card"><div id="topicTable"></div></div>
  </div>
  <div data-pane="meetings" class="hidden">
    <div class="card"><h2>Meetings (most activating first)</h2><div id="meetingTable"></div></div>
  </div>
  </div><!-- /#app -->
</div>
<script id="aide-data" type="application/json">{payload}</script>
<script>{_JS}</script>
</body></html>"""
