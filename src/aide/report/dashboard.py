"""Render a self-contained, interactive HTML dashboard.

Everything (data + app) is inlined into one file: it opens straight in a browser,
needs no server and makes no network calls, so the data stays on your machine.
All leaderboards are recomputed client-side as you change the filters.

Stress is shown as a 0–100 **stress index** (50 = your average meeting), a
monotonic transform of the underlying z-score, so non-analysts can read it at a
glance. A static, server-rendered fallback covers viewers that block JavaScript.
"""
from __future__ import annotations

import html as _html
import json
import math
from datetime import timedelta

from ..analyze.attribution import attribute_clients, attribute_people
from ..analyze.keywords import stress_keywords
from ..config import Config
from ..models import MeetingStress

# z-score -> 0..100 index (logistic, centred so z=0 -> 50). Shared with the JS.
_K = 0.85


def z_to_index(z: float) -> int:
    return round(100 / (1 + math.exp(-_K * z)))


# Calm -> hot colour ramp, mirrored in JS.
_STOPS = [(0, (42, 157, 143)), (50, (233, 196, 106)), (100, (231, 111, 81))]


def _idx_color(v: float) -> str:
    v = max(0, min(100, v))
    i = 1
    while i < len(_STOPS) and v > _STOPS[i][0]:
        i += 1
    a0, c0 = _STOPS[i - 1]
    a1, c1 = _STOPS[i]
    t = (v - a0) / ((a1 - a0) or 1)
    rgb = [round(c0[k] + (c1[k] - c0[k]) * t) for k in range(3)]
    return "#%02x%02x%02x" % tuple(rgb)


_CSS = """
:root{
  --ink:#15161a;--mut:#6b6f76;--line:#e9e9ee;--bg:#f6f7f9;--card:#fff;
  --shadow:0 1px 2px rgba(20,22,26,.04),0 6px 18px rgba(20,22,26,.05);
}
*{box-sizing:border-box}
body{font:14px/1.55 ui-sans-serif,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;color:var(--ink);
  background:var(--bg);-webkit-font-smoothing:antialiased}
header{background:linear-gradient(180deg,#fff,#fbfbfd);border-bottom:1px solid var(--line);padding:20px 24px}
.head-row{max-width:1120px;margin:0 auto;display:flex;justify-content:space-between;align-items:flex-end;gap:16px;flex-wrap:wrap}
h1{font-size:21px;margin:0;letter-spacing:-.01em}
.sub{color:var(--mut);font-size:12.5px;margin-top:3px}
.wrap{max-width:1120px;margin:0 auto;padding:22px 24px 60px}
.controls{display:flex;flex-wrap:wrap;gap:12px;align-items:end}
.controls label{display:flex;flex-direction:column;font-size:10.5px;color:var(--mut);gap:5px;
  text-transform:uppercase;letter-spacing:.05em;font-weight:600}
.controls input,.controls select{font:13px inherit;padding:7px 10px;border:1px solid var(--line);
  border-radius:9px;background:#fff;color:var(--ink);outline:none}
.controls input:focus,.controls select:focus{border-color:#c5c7cf;box-shadow:0 0 0 3px rgba(120,120,140,.1)}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px;margin:4px 0 20px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 17px;box-shadow:var(--shadow)}
.kpi .v{font-size:25px;font-weight:680;letter-spacing:-.02em;line-height:1.1}
.kpi .l{color:var(--mut);font-size:12px;margin-top:4px}
nav{display:flex;gap:6px;margin:2px 0 18px;flex-wrap:wrap}
nav button{font:13px inherit;font-weight:550;padding:8px 15px;border:1px solid var(--line);background:#fff;
  border-radius:999px;cursor:pointer;color:var(--mut);transition:.12s}
nav button:hover{color:var(--ink);border-color:#d6d8df}
nav button.active{background:var(--ink);color:#fff;border-color:var(--ink)}
.card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px 20px;
  margin-bottom:16px;box-shadow:var(--shadow)}
.card h2{font-size:14px;margin:0 0 4px;letter-spacing:-.01em}
.card .cap{color:var(--mut);font-size:12px;margin:0 0 14px}
table{border-collapse:collapse;width:100%}
th,td{text-align:left;padding:9px 8px;border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
tr:last-child td{border-bottom:0}
th{font-size:10.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--mut);cursor:pointer;user-select:none;font-weight:650}
td.num,th.num{text-align:right}
tbody tr:hover{background:#fafafb}
.rank{color:var(--mut);font-variant-numeric:tabular-nums;width:22px}
.pill{display:inline-block;min-width:34px;text-align:center;padding:2px 9px;border-radius:999px;
  font-weight:700;font-size:12.5px}
.tag{font-size:10px;padding:2px 8px;border-radius:999px;background:#f0f1f4;color:var(--mut);font-weight:600}
.track{height:7px;border-radius:4px;background:#eef0f3;position:relative;overflow:hidden;min-width:60px}
.track>span{position:absolute;left:0;top:0;bottom:0;border-radius:4px}
.delta{font-variant-numeric:tabular-nums;color:var(--mut)}
.muted{color:var(--mut)}
.hint{color:var(--mut);font-size:12px;margin-top:12px}
.legend{display:flex;align-items:center;gap:8px;font-size:11px;color:var(--mut)}
.legend .ramp{height:8px;width:120px;border-radius:4px;
  background:linear-gradient(90deg,#2a9d8f,#e9c46a,#e76f51)}
.hidden{display:none}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:720px){.grid2{grid-template-columns:1fr}}
svg text{font:10px ui-sans-serif,-apple-system,sans-serif;fill:var(--mut)}
.dot{transition:r .1s}.dot:hover{stroke:#15161a;stroke-width:1.5}
"""

_JS = r"""
const DATA = JSON.parse(document.getElementById("aide-data").textContent);
const M = DATA.meetings, scored = M.filter(m=>m.hasData);
const dates = scored.map(m=>m.date).sort();
const WD = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
const $ = s=>document.querySelector(s);
const avg = a=>a.length? a.reduce((x,y)=>x+y,0)/a.length : 0;
const K=0.85, zIdx=z=>Math.round(100/(1+Math.exp(-K*z)));
const fmtD=v=>(v>=0?"+":"")+v.toFixed(1);

// calm -> hot ramp
const STOPS=[[0,[42,157,143]],[50,[233,196,106]],[100,[231,111,81]]];
function color(v){v=Math.max(0,Math.min(100,v));let i=1;while(i<STOPS.length&&v>STOPS[i][0])i++;
  const[a0,c0]=STOPS[i-1],[a1,c1]=STOPS[i],t=(v-a0)/((a1-a0)||1);
  return "#"+[0,1,2].map(k=>("0"+Math.round(c0[k]+(c1[k]-c0[k])*t).toString(16)).slice(-2)).join("");}

function lastWorkdaysStart(endStr,n){const pad=x=>String(x).padStart(2,"0");
  const[y,m,d]=endStr.split("-").map(Number);let dt=new Date(y,m-1,d),c=0;
  while(true){const wd=dt.getDay();if(wd>=1&&wd<=5){c++;if(c>=n)break;}dt.setDate(dt.getDate()-1);}
  return `${dt.getFullYear()}-${pad(dt.getMonth()+1)}-${pad(dt.getDate())}`;}
const _end=dates[dates.length-1];let _def=lastWorkdaysStart(_end,5);if(_def<dates[0])_def=dates[0];
const state={start:_def,end:_end,minN:DATA.minMeetingsDefault||3,scope:"all",search:"",tab:"overview",
  sort:{key:"mean",dir:-1}};

const filtered=()=>scored.filter(m=>m.date>=state.start&&m.date<=state.end);
function aggregate(field){
  const ms=filtered(),map=new Map();
  for(const m of ms){
    let items=field==="people"?m.people:field==="clients"?m.clients.map(c=>({key:c,label:c,internal:null}))
              :m.keywords.map(k=>({key:k,label:k,internal:null}));
    for(const it of items){let a=map.get(it.key);
      if(!a){a={label:it.label,internal:it.internal,scores:[],deltas:[]};map.set(it.key,a);}
      a.label=it.label;a.scores.push(m.stress);a.deltas.push(m.deltaHR);}
  }
  let rows=[...map.values()].map(a=>{const mean=avg(a.scores);
    return {label:a.label,internal:a.internal,n:a.scores.length,mean,index:zIdx(mean),meanDelta:avg(a.deltas)};});
  if(field==="people"&&state.scope!=="all")
    rows=rows.filter(r=>state.scope==="internal"?r.internal:r.internal===false);
  rows=rows.filter(r=>r.n>=state.minN);
  if(state.search)rows=rows.filter(r=>r.label.toLowerCase().includes(state.search.toLowerCase()));
  const k=state.sort.key,d=state.sort.dir;
  rows.sort((a,b)=>(a[k]<b[k]?-1:a[k]>b[k]?1:0)*d);
  return rows;
}
const esc=x=>(""+x).replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
const pill=v=>`<span class="pill" style="background:${color(v)}26;color:${color(v)}">${v}</span>`;

// ---- charts --------------------------------------------------------------
function scatter(){
  const ms=filtered();if(!ms.length)return "<p class='muted'>No meetings in range.</p>";
  const W=920,H=280,pl=34,pb=26,pt=12,pr=12;
  const t=ms.map(m=>+new Date(m.start)),t0=Math.min(...t),t1=Math.max(...t);
  const ys=ms.map(m=>m.deltaHR),y0=Math.min(0,...ys),y1=Math.max(...ys)*1.05;
  const X=v=>pl+((v-t0)/((t1-t0)||1))*(W-pl-pr),Y=v=>H-pb-((v-y0)/((y1-y0)||1))*(H-pt-pb);
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none">`;
  for(let g=0;g<=4;g++){const v=y0+(y1-y0)*g/4,y=Y(v);
    s+=`<line x1="${pl}" y1="${y}" x2="${W-pr}" y2="${y}" stroke="${g===0?'#d8dade':'#f0f1f4'}"/>`;
    s+=`<text x="2" y="${y+3}">${v.toFixed(0)}</text>`;}
  ms.forEach(m=>{s+=`<circle class="dot" cx="${X(+new Date(m.start))}" cy="${Y(m.deltaHR)}" r="4.5" `+
    `fill="${color(zIdx(m.stress))}" fill-opacity="0.85"><title>${esc(m.title)}\n${m.date} ${String(m.hour).padStart(2,'0')}:00 · ${fmtD(m.deltaHR)} bpm · index ${zIdx(m.stress)}</title></circle>`;});
  s+=`<text x="${pl}" y="${H-6}">${ms[0].date}</text><text x="${W-pr}" y="${H-6}" text-anchor="end">${ms[ms.length-1].date}</text>`;
  return s+`</svg>`;
}
function barChart(labels,vals){ // vals are 0..100 indices
  const W=460,n=labels.length,bw=(W-10)/n,H=170,top=14,base=H-22;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">`;
  const mid=top+(base-top)*(1-50/100);
  s+=`<line x1="0" y1="${mid}" x2="${W}" y2="${mid}" stroke="#e3e4e8" stroke-dasharray="3 3"/>`;
  s+=`<text x="${W-2}" y="${mid-3}" text-anchor="end">avg 50</text>`;
  labels.forEach((lb,i)=>{const v=vals[i]||0,h=(v/100)*(base-top),x=8+i*bw;
    s+=`<rect x="${x}" y="${base-h}" width="${bw*0.66}" height="${h}" rx="3" fill="${color(v)}"/>`;
    s+=`<text x="${x+bw*0.33}" y="${base+14}" text-anchor="middle">${esc(lb)}</text>`;});
  return s+`</svg>`;
}
function buckets(field){const ms=filtered(),g={};for(const m of ms){(g[m[field]]=g[m[field]]||[]).push(zIdx(m.stress));}return g;}

// ---- tables --------------------------------------------------------------
function table(rows,withType){
  if(!rows.length)return "<p class='muted'>Nothing meets the current filters.</p>";
  const total=rows.length;rows=rows.slice(0,60);
  const th=(k,l,num)=>`<th class="${num?'num':''}" data-sort="${k}">${l}${state.sort.key===k?(state.sort.dir<0?' ↓':' ↑'):''}</th>`;
  let h=`<table><thead><tr><th class="rank"></th>${th('label','Name')}${th('index','Index',1)}${th('meanDelta','ΔHR',1)}${th('n','Mtgs',1)}${withType?'<th>Type</th>':''}<th style="width:90px">vs avg</th></tr></thead><tbody>`;
  rows.forEach((r,i)=>{const c=color(r.index),w=Math.max(2,r.index);
    h+=`<tr><td class="rank">${i+1}</td><td>${esc(r.label)}</td>`+
       `<td class="num">${pill(r.index)}</td>`+
       `<td class="num delta">${fmtD(r.meanDelta)}</td>`+
       `<td class="num">${r.n}</td>`+
       (withType?`<td><span class="tag">${r.internal?'internal':r.internal===false?'external':'—'}</span></td>`:'')+
       `<td><div class="track"><span style="width:${w}%;background:${c}"></span></div></td></tr>`;});
  h+="</tbody></table>";
  if(total>rows.length)h+=`<div class="hint">Showing top ${rows.length} of ${total}. Use search to narrow.</div>`;
  return h;
}
function renderMeetings(){
  let ms=filtered().slice().sort((a,b)=>b.stress-a.stress);
  if(state.search)ms=ms.filter(m=>m.title.toLowerCase().includes(state.search.toLowerCase()));
  let h=`<table><thead><tr><th>When</th><th>Meeting</th><th class="num">Index</th><th class="num">ΔHR</th><th>People / clients</th></tr></thead><tbody>`;
  for(const m of ms.slice(0,200)){const who=[...m.people.map(p=>p.label),...m.clients].slice(0,4).join(", ");
    h+=`<tr><td class="muted">${m.date} ${String(m.hour).padStart(2,'0')}:00</td>`+
       `<td>${esc(m.title).slice(0,62)}</td><td class="num">${pill(zIdx(m.stress))}</td>`+
       `<td class="num delta">${fmtD(m.deltaHR)}</td><td class="muted">${esc(who)}</td></tr>`;}
  $("#meetingTable").innerHTML=h+"</tbody></table>";
}

// ---- render --------------------------------------------------------------
const kpi=(v,l,c)=>`<div class="kpi"><div class="v" ${c?`style="color:${c}"`:''}>${v}</div><div class="l">${l}</div></div>`;
function renderKPIs(){
  const ms=filtered();const idx=ms.map(m=>zIdx(m.stress));const ai=Math.round(avg(idx));
  const peak=ms.reduce((a,b)=>(a&&a.deltaHR>b.deltaHR)?a:b,null);
  $("#kpis").innerHTML=
    kpi(ms.length,"meetings in range")+
    kpi(ai,"avg stress index (50 = your norm)",color(ai))+
    kpi(fmtD(avg(ms.map(m=>m.deltaHR)))+" bpm","mean heart-rate lift")+
    kpi(peak?("+"+peak.deltaHR.toFixed(0)+" bpm"):"–","peak · "+(peak?esc(peak.title).slice(0,26):""));
}
function render(){
  renderKPIs();
  document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("active",b.dataset.tab===state.tab));
  document.querySelectorAll("[data-pane]").forEach(p=>p.classList.toggle("hidden",p.dataset.pane!==state.tab));
  $("#peopleScope").style.display=state.tab==="people"?"flex":"none";
  if(state.tab==="overview"){
    $("#scatter").innerHTML=scatter();
    const wd=buckets("weekday");$("#wdchart").innerHTML=barChart(WD,WD.map((_,i)=>avg(wd[i]||[])));
    const hb=buckets("hour"),hrs=[...Array(24).keys()].filter(h=>h>=7&&h<=20);
    $("#hrchart").innerHTML=barChart(hrs.map(h=>h+""),hrs.map(h=>avg(hb[h]||[])));
  }
  if(state.tab==="people"){const r=aggregate("people");$("#peopleTable").innerHTML=table(r,true);}
  if(state.tab==="clients"){const r=aggregate("clients");$("#clientTable").innerHTML=table(r,false);}
  if(state.tab==="topics"){const r=aggregate("keywords");$("#topicTable").innerHTML=table(r,false);}
  if(state.tab==="meetings"){renderMeetings();}
}
function bind(){
  const app=document.getElementById("app");if(app)app.style.display="";
  const fb=document.getElementById("fallback");if(fb)fb.remove();
  $("#start").value=state.start;$("#start").min=dates[0];$("#start").max=dates[dates.length-1];
  $("#end").value=state.end;$("#end").min=dates[0];$("#end").max=dates[dates.length-1];
  $("#minN").value=state.minN;
  $("#start").onchange=e=>{state.start=e.target.value;render();};
  $("#end").onchange=e=>{state.end=e.target.value;render();};
  $("#minN").onchange=e=>{state.minN=+e.target.value;render();};
  $("#scope").onchange=e=>{state.scope=e.target.value;render();};
  $("#search").oninput=e=>{state.search=e.target.value;render();};
  document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>{state.tab=b.dataset.tab;state.search="";$("#search").value="";render();});
  document.body.addEventListener("click",e=>{const th=e.target.closest("th[data-sort]");if(!th)return;
    const k=th.dataset.sort;state.sort.dir=state.sort.key===k?-state.sort.dir:-1;state.sort.key=k;render();});
}
bind();render();
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


def _pill(idx: int) -> str:
    c = _idx_color(idx)
    return f"<span class='pill' style='background:{c}26;color:{c}'>{idx}</span>"


def _ssr_table(title: str, tallies, with_type: bool, limit: int = 12) -> str:
    rows = []
    for i, t in enumerate(tallies[:limit], 1):
        idx = z_to_index(t.mean_score)
        c = _idx_color(idx)
        typ = (
            f"<td><span class='tag'>{'internal' if t.internal else 'external'}</span></td>"
            if with_type else ""
        )
        rows.append(
            f"<tr><td class='rank'>{i}</td><td>{_html.escape(t.label)}</td>"
            f"<td class='num'>{_pill(idx)}</td>"
            f"<td class='num delta'>{t.mean_hr_elevation:+.1f}</td>"
            f"<td class='num'>{t.n}</td>{typ}"
            f"<td><div class='track'><span style='width:{max(2, idx)}%;background:{c}'></span></div></td></tr>"
        )
    body = "".join(rows) or "<tr><td class='muted'>Not enough data in this window.</td></tr>"
    extra = "<th>type</th>" if with_type else ""
    return (
        f"<div class='card'><h2>{_html.escape(title)}</h2><table>"
        f"<tr><th class='rank'></th><th>name</th><th class='num'>index</th>"
        f"<th class='num'>ΔHR</th><th class='num'>mtgs</th>{extra}<th style='width:90px'>vs avg</th></tr>"
        f"{body}</table></div>"
    )


def build_fallback_html(stresses: list[MeetingStress], config: Config) -> str:
    """Static, JS-free view of the default window — shown if scripts can't run."""
    start, end = _default_window(stresses)
    if start is None:
        return "<div class='card muted'>No scored meetings to display.</div>"
    sub = [s for s in stresses if s.has_data and start <= s.meeting.start.date() <= end]
    people = attribute_people(sub, config)
    clients = attribute_clients(sub, config)
    keywords = stress_keywords(sub, config, top=12)
    elev = [s.hr_elevation for s in sub]
    mean_elev = sum(elev) / len(elev) if elev else 0.0
    avg_idx = round(sum(z_to_index(s.stress_score) for s in sub) / len(sub)) if sub else 50
    peak = max(sub, key=lambda s: s.hr_elevation) if sub else None
    kpis = (
        f"<div class='kpi'><div class='v'>{len(sub)}</div><div class='l'>meetings · {start} → {end}</div></div>"
        f"<div class='kpi'><div class='v' style='color:{_idx_color(avg_idx)}'>{avg_idx}</div>"
        f"<div class='l'>avg stress index (50 = your norm)</div></div>"
        f"<div class='kpi'><div class='v'>{mean_elev:+.1f} bpm</div><div class='l'>mean heart-rate lift</div></div>"
        + (f"<div class='kpi'><div class='v'>+{peak.hr_elevation:.0f} bpm</div>"
           f"<div class='l'>peak · {_html.escape(peak.meeting.title)[:24]}</div></div>" if peak else "")
    )
    return (
        "<div class='hint' style='margin-bottom:14px'>Static view of your last 5 working days. "
        "<b>Open this file in a web browser</b> for the full interactive dashboard "
        "(date-range, filters, charts).</div>"
        f"<div class='kpis'>{kpis}</div>"
        + _ssr_table("Colleagues — who raises your stress most", people, True)
        + _ssr_table("Clients / accounts — most stressful", clients, False)
        + _ssr_table("Topics & keywords — most stress-associated", keywords, False)
    )


def render_dashboard(data: dict, fallback_html: str = "") -> str:
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    legend = ('<div class="legend">calm<span class="ramp"></span>activated · '
              'stress index 0–100, 50 = your average meeting</div>')
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>aide · stress dashboard</title><style>{_CSS}</style></head><body>
<header>
  <div class="head-row">
    <div>
      <h1>🫀 Stress dashboard</h1>
      <div class="sub">{len(data.get('meetings', []))} meetings · generated {data.get('generated','')} · runs entirely in your browser</div>
    </div>
    <div class="controls">
      <label>From<input type="date" id="start"></label>
      <label>To<input type="date" id="end"></label>
      <label>Min mtgs<input type="number" id="minN" min="1" max="20" style="width:64px"></label>
      <label id="peopleScope" style="display:none">People<select id="scope">
        <option value="all">everyone</option><option value="internal">colleagues</option><option value="external">external</option>
      </select></label>
      <label>Search<input type="search" id="search" placeholder="filter…" style="width:150px"></label>
    </div>
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
    <div class="card"><h2>Every meeting over time</h2>
      <p class="cap">Each dot is a meeting — height is heart-rate lift over resting, colour is the stress index. Hover for detail.</p>
      <div id="scatter"></div><div style="margin-top:8px">{legend}</div></div>
    <div class="grid2">
      <div class="card"><h2>Stress index by weekday</h2><p class="cap">Average across the window.</p><div id="wdchart"></div></div>
      <div class="card"><h2>Stress index by hour</h2><p class="cap">Separates the meeting from time-of-day effects.</p><div id="hrchart"></div></div>
    </div>
  </div>

  <div data-pane="people" class="hidden">
    <div class="card"><h2>Colleagues — who raises your stress most</h2>
      <p class="cap">Correlation, not causation — workload and back-to-back days travel with the people in the room.</p>
      <div id="peopleTable"></div></div>
  </div>
  <div data-pane="clients" class="hidden">
    <div class="card"><h2>Clients / accounts — most stressful</h2><p class="cap">By external attendee domain and meeting keywords.</p><div id="clientTable"></div></div>
  </div>
  <div data-pane="topics" class="hidden">
    <div class="card"><h2>Topics & keywords — most stress-associated</h2><p class="cap">Mined from meeting titles and Granola summaries.</p><div id="topicTable"></div></div>
  </div>
  <div data-pane="meetings" class="hidden">
    <div class="card"><h2>Meetings — most activating first</h2><div id="meetingTable"></div></div>
  </div>
  </div><!-- /#app -->
</div>
<script id="aide-data" type="application/json">{payload}</script>
<script>{_JS}</script>
</body></html>"""
