"""Local web GUI for Paper2Protocol.

The published showcase site is a sandboxed static page and cannot run the
pipeline. THIS runs locally on your machine and wires the real thing: upload a
PDF, it ingests -> extracts a spec -> generates -> validates/repairs -> (optionally)
dispatches to a simulated OT-2, and hands back the validated protocol to download.

    paper2protocol serve            # then open http://127.0.0.1:8000

`/demo` runs the built-in chemotaxis run with the scripted generator (no API key,
no quota) so the GUI is usable/testable offline. `/run` does the real live thing
from an uploaded PDF (needs a generator key in .env).
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from .conformance import realized_final_concentration
from .loop import ScriptedProvider, run_loop

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "examples" / "chemotaxis_penstrep"

app = FastAPI(title="Paper2Protocol")


def _iterations(outcome) -> list[dict]:
    out = []
    for r in outcome.iterations:
        out.append({
            "n": r.iteration,
            "stage_reached": r.stage_reached,
            "passed": r.passed,
            "static": [{"rule": f.rule, "line": f.line, "message": f.message}
                       for f in r.static_findings if f.severity == "error"],
            "analyze": None if r.analyze_result is None else {
                "result": r.analyze_result.result,
                "n_commands": r.analyze_result.n_commands,
                "errors": [e.hint() for e in r.analyze_result.errors],
            },
            "conformance": None if r.conformance is None else {
                "ok": r.conformance.ok,
                "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail}
                           for c in r.conformance.checks],
            },
        })
    return out


def _realized(ir: dict) -> list[dict]:
    dil = ir.get("dilution", {})
    stock = (dil.get("stock_source") or {}).get("stock_conc")
    rows = []
    for t in dil.get("targets", []):
        row = {"well": t["well"], "vv": t["vv"]}
        if stock:
            row["conc"] = realized_final_concentration(t["vv"], stock)
        rows.append(row)
    return rows


def _result(outcome, ir: dict, *, do_dispatch: bool) -> dict:
    dil = ir.get("dilution", {}) or {}
    stock = dil.get("stock_source") or {}
    disp = None
    if do_dispatch and outcome.status == "converged" and outcome.final is not None:
        from .dispatch import dispatch_to_virtual
        d = dispatch_to_virtual(outcome.final.path)
        disp = {"status": d["status"], "run_id": d["run_id"]}
    return {
        "status": outcome.status,
        "reason": outcome.reason,
        "paper": ir.get("paper", {}),
        "clarifications": ir.get("open_clarifications", []),
        "spec": {
            "targets": dil.get("targets", []),
            "dest_labware": dil.get("dest_labware"),
            "total_vol_ul": dil.get("total_vol_ul"),
            "stock": {"liquid": stock.get("liquid"), "conc": stock.get("stock_conc"),
                      "labware": stock.get("labware"), "well": stock.get("well")},
        },
        "iterations": _iterations(outcome),
        "protocol": outcome.final.source if outcome.final else None,
        "realized": _realized(ir),
        "dispatch": disp,
    }


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return PAGE


@app.post("/demo")
def demo():
    try:
        ir = json.loads((EX / "ir.json").read_text())
        drafts = [EX / "iterations" / f"draft{i}.py" for i in (1, 2, 3, 4)]
        outcome = run_loop(ScriptedProvider(drafts), ir)
        return _result(outcome, ir, do_dispatch=True)
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "error", "message": str(e)[:400]}, status_code=500)


@app.post("/run")
def run(pdf: UploadFile = File(...), model: str = Form(""), dispatch: str = Form("true")):
    try:
        from .codegen import LLMDraftProvider
        from .extract import ingest as ingest_pdf
        from .providers.base import get_provider, load_env
        load_env(ROOT / ".env")
        prov = get_provider(None, model or None)
        tmp = Path(tempfile.mkdtemp()) / (pdf.filename or "paper.pdf")
        tmp.write_bytes(pdf.file.read())
        ir = ingest_pdf(tmp, prov)
        if not ir.get("dilution"):
            return {"status": "refused", "paper": ir.get("paper", {}),
                    "clarifications": ir.get("open_clarifications", []),
                    "message": "No automatable aqueous dilution/concentration series found."}
        outcome = run_loop(LLMDraftProvider(prov, ir, EX / "out" / "web_drafts"), ir)
        return _result(outcome, ir, do_dispatch=(dispatch == "true"))
    except Exception as e:  # noqa: BLE001
        return JSONResponse({"status": "error", "message": str(e)[:400]}, status_code=500)


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Paper2Protocol</title>
<style>
:root{--bg:#070b0d;--panel:#0e1719;--line:rgba(120,214,205,.14);--ink:#e6f2f1;--muted:#8aa3a3;--faint:#5c7574;
--teal:#34e3cc;--teal-d:#159c8a;--amber:#ffb45c;--pass:#3fe392;--fail:#ff6b6b;
--mono:"SF Mono",ui-monospace,Menlo,Consolas,monospace;--sans:system-ui,-apple-system,"Segoe UI",sans-serif}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--sans);
background-image:radial-gradient(800px 400px at 80% -10%,rgba(52,227,204,.09),transparent 60%)}
.wrap{max-width:1000px;margin:0 auto;padding:36px 22px 80px}
h1{font-size:34px;letter-spacing:-.02em;margin:0}.dot{display:inline-block;width:10px;height:10px;border-radius:50%;
background:var(--teal);box-shadow:0 0 12px var(--teal);margin-right:10px}
.sub{color:var(--muted);margin:8px 0 26px;max-width:64ch}
.card{background:linear-gradient(180deg,rgba(16,29,31,.6),rgba(9,16,18,.5));border:1px solid var(--line);
border-radius:16px;padding:22px;margin-bottom:18px}
.drop{border:1.5px dashed var(--line);border-radius:14px;padding:30px;text-align:center;transition:.2s;cursor:pointer}
.drop.over{border-color:var(--teal);background:rgba(52,227,204,.05)}
.drop b{color:var(--teal)}.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:16px}
.btn{font-family:var(--mono);font-size:13.5px;font-weight:600;padding:12px 20px;border-radius:10px;cursor:pointer;
border:1px solid var(--line);background:transparent;color:var(--ink);transition:.15s}
.btn:hover{border-color:var(--teal)}.btn.p{background:linear-gradient(180deg,var(--teal),var(--teal-d));color:#04110c;border:0}
.btn:disabled{opacity:.5;cursor:default}
input[type=text]{font-family:var(--mono);font-size:12.5px;background:#060d0e;border:1px solid var(--line);
border-radius:8px;color:var(--ink);padding:9px 11px;width:210px}
label.ck{font-family:var(--mono);font-size:12px;color:var(--muted);display:flex;gap:7px;align-items:center}
.mono{font-family:var(--mono)}.hidden{display:none}
.pipe{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin:6px 0 18px}
.st{border:1px solid var(--line);border-radius:10px;padding:10px 8px;font-family:var(--mono);font-size:10px;
color:var(--faint);text-align:center;transition:.3s}
.st.on{border-color:var(--teal);color:var(--teal);box-shadow:0 0 0 1px var(--teal)}
.st.ok{border-color:var(--pass);color:var(--pass)}.st.bad{border-color:var(--fail);color:var(--fail)}
.log{background:#060d0e;border:1px solid var(--line);border-radius:12px;padding:14px 16px;font-family:var(--mono);
font-size:12.5px;line-height:1.7;max-height:280px;overflow:auto}
.log .ok{color:var(--pass)}.log .bad{color:var(--fail)}.log .t{color:var(--teal)}.log .dim{color:var(--faint)}
.banner{font-family:var(--mono);font-weight:700;padding:12px 16px;border-radius:10px;margin:16px 0;letter-spacing:.03em}
.banner.ok{background:rgba(63,227,146,.12);color:var(--pass);border:1px solid rgba(63,227,146,.35)}
.banner.bad{background:rgba(255,107,107,.12);color:var(--fail);border:1px solid rgba(255,107,107,.35)}
.banner.warn{background:rgba(255,180,92,.12);color:var(--amber);border:1px solid rgba(255,180,92,.35)}
pre{background:#060d0e;border:1px solid var(--line);border-radius:12px;padding:16px;overflow:auto;
font-family:var(--mono);font-size:12px;line-height:1.6;color:#cfe0df;max-height:340px}
.clar{font-family:var(--mono);font-size:12px;color:var(--amber);padding:6px 0;border-bottom:1px solid var(--line)}
.small{font-family:var(--mono);font-size:11px;color:var(--faint);margin-top:8px}
.spin{width:15px;height:15px;border:2px solid var(--line);border-top-color:var(--teal);border-radius:50%;
display:inline-block;animation:s .8s linear infinite;vertical-align:-2px}@keyframes s{to{transform:rotate(360deg)}}
</style></head><body><div class="wrap">
<h1><span class="dot"></span>Paper2Protocol</h1>
<p class="sub">Upload a paper (PDF). It extracts the spec, a model writes the Opentrons protocol, the real engine validates and repairs it, and it dispatches to a simulated OT-2. The validated protocol is yours to download.</p>

<div class="card">
  <div class="drop" id="drop"><input type="file" id="file" accept="application/pdf" class="hidden">
    <div id="dropmsg">Drop a PDF here, or <b>click to choose</b></div></div>
  <div class="row">
    <button class="btn p" id="runbtn" disabled>Run pipeline</button>
    <button class="btn" id="demobtn">Run built-in demo (no key)</button>
    <input type="text" id="model" placeholder="model (optional)">
    <label class="ck"><input type="checkbox" id="dispatch" checked> dispatch to OT-2</label>
  </div>
  <div class="small">Live runs need a generator key in <span class="mono">.env</span>. The demo runs offline with the scripted generator.</div>
</div>

<div id="out" class="hidden">
  <div class="card">
    <div id="paper" class="mono" style="color:var(--teal);margin-bottom:12px"></div>
    <div class="pipe" id="pipe"></div>
    <div class="log" id="log"></div>
    <div id="banner"></div>
    <div id="clars"></div>
  </div>
  <div class="card hidden" id="protocard">
    <div class="mono" style="color:var(--faint);font-size:11px;margin-bottom:10px">VALIDATED PROTOCOL</div>
    <pre id="proto"></pre>
    <div class="row"><button class="btn p" id="dl">Download protocol.py</button>
      <span id="realized" class="mono" style="font-size:12px;color:var(--muted)"></span></div>
  </div>
</div>

<script>
const STAGES=["01 PAPER","02 EXTRACT","03 GENERATE","04 PROTOCOL","05 VERIFY","06 DISPATCH"];
const $=id=>document.getElementById(id);
let chosen=null;
const drop=$("drop"),file=$("file");
drop.onclick=()=>file.click();
drop.ondragover=e=>{e.preventDefault();drop.classList.add("over")};
drop.ondragleave=()=>drop.classList.remove("over");
drop.ondrop=e=>{e.preventDefault();drop.classList.remove("over");if(e.dataTransfer.files[0])pick(e.dataTransfer.files[0])};
file.onchange=()=>{if(file.files[0])pick(file.files[0])};
function pick(f){chosen=f;$("dropmsg").innerHTML="<b>"+f.name+"</b> ready";$("runbtn").disabled=false}
function sleep(ms){return new Promise(r=>setTimeout(r,ms))}
function pipe(states){$("pipe").innerHTML=STAGES.map((s,i)=>`<div class="st ${states[i]||''}" id="st${i}">${s}</div>`).join("")}
function log(html,cls){const d=document.createElement("div");if(cls)d.className=cls;d.innerHTML=html;$("log").appendChild(d);$("log").scrollTop=1e9}

$("demobtn").onclick=()=>go("/demo",null);
$("runbtn").onclick=()=>{if(!chosen)return;const fd=new FormData();fd.append("pdf",chosen);
  fd.append("model",$("model").value);fd.append("dispatch",$("dispatch").checked?"true":"false");go("/run",fd)};

async function go(url,body){
  $("out").classList.remove("hidden");$("protocard").classList.add("hidden");
  $("log").innerHTML="";$("banner").innerHTML="";$("clars").innerHTML="";$("paper").textContent="";
  pipe(["on","","","","",""]);
  $("runbtn").disabled=true;$("demobtn").disabled=true;
  log('<span class="spin"></span> '+(url==="/demo"?"running built-in demo…":"ingesting PDF, extracting spec, generating…"),"dim");
  let r;
  try{ r=await fetch(url,{method:"POST",body}); }catch(e){ log('<span class="bad">network error: '+e+'</span>',"bad"); reset(); return; }
  let d; try{ d=await r.json(); }catch(e){ log('<span class="bad">bad response</span>',"bad"); reset(); return; }
  await render(d); reset();
}
function reset(){$("runbtn").disabled=!chosen;$("demobtn").disabled=false}

async function render(d){
  $("log").innerHTML="";
  if(d.status==="error"){pipe(["bad","","","","",""]);banner("bad","ERROR");log('<span class="bad">'+ (d.message||"error") +'</span>',"bad");return}
  $("paper").textContent=d.paper&&d.paper.title?d.paper.title:"";
  if(d.status==="refused"){pipe(["ok","bad","","","",""]);
    log('<span class="t">paper</span> ingested');await sleep(300);
    log('<span class="bad">extract → no automatable aqueous dilution series in this paper</span>',"bad");
    banner("warn","REFUSED — nothing to automate (honest, not a guess)");clars(d.clarifications);return}
  // converged / blocked: animate the real iterations
  pipe(["ok","ok","on","","",""]);
  log('<span class="t">paper</span> ingested → <span class="t">spec</span> extracted');
  if(d.spec&&d.spec.targets&&d.spec.targets.length){
    log('<span class="dim">dilution '+d.spec.targets.map(t=>t.well+"="+Math.round(t.vv*100)+"%").join(", ")+' in '+d.spec.dest_labware+'</span>',"dim");}
  await sleep(500);
  for(const it of d.iterations){
    pipe(["ok","ok","on","","",""]);
    log('<span class="t">iter '+it.n+'</span> — generate → verify');
    await sleep(400);
    let bad=false;
    for(const s of it.static){log('<span class="bad">✗ static</span> ['+s.rule+' L'+s.line+'] '+s.message,"bad");bad=true}
    if(it.analyze){ if(it.analyze.result==="ok"){log('<span class="ok">✓ analyze</span> '+it.analyze.n_commands+' commands, 0 errors',"ok")}
      else{it.analyze.errors.forEach(e=>log('<span class="bad">✗ analyze</span> '+e.slice(0,120),"bad"));bad=true} }
    if(it.conformance){ if(it.conformance.ok){log('<span class="ok">✓ conformance</span> realized dilution matches spec',"ok")}
      else{it.conformance.checks.filter(c=>!c.ok).forEach(c=>log('<span class="bad">✗ conformance</span> '+c.detail,"bad"));bad=true} }
    pipe(["ok","ok","ok","ok",bad?"bad":"on",""]);
    await sleep(650);
  }
  if(d.status==="converged"){
    pipe(["ok","ok","ok","ok","ok",d.dispatch?"on":""]);
    if(d.dispatch){log('<span class="t">dispatch</span> → OT-2 · upload → run → play');await sleep(500);
      const ok=d.dispatch.status==="succeeded";pipe(["ok","ok","ok","ok","ok",ok?"ok":"bad"]);
      log((ok?'<span class="ok">✓ RUN '+d.dispatch.status.toUpperCase()+'</span>':'<span class="bad">run '+d.dispatch.status+'</span>')+' on the simulated OT-2',ok?"ok":"bad");}
    banner("ok","CONVERGED"+(d.dispatch&&d.dispatch.status==="succeeded"?" · DISPATCHED · RUN SUCCEEDED":""));
    showProto(d);
  }else{
    pipe(["ok","ok","ok","ok","bad",""]);banner("bad","BLOCKED — "+(d.reason||"hit iteration cap")+" (refused to fake it)");
    if(d.protocol)showProto(d);
  }
  clars(d.clarifications);
}
function banner(cls,txt){$("banner").innerHTML='<div class="banner '+cls+'">'+txt+'</div>'}
function clars(cs){if(!cs||!cs.length)return;$("clars").innerHTML='<div class="small" style="margin-bottom:6px">CLARIFICATIONS THE EXTRACTOR RAISED</div>'+cs.map(c=>'<div class="clar">⚑ '+esc(c)+'</div>').join("")}
function esc(s){return (s||"").replace(/</g,"&lt;").replace(/>/g,"&gt;")}
function showProto(d){if(!d.protocol)return;$("protocard").classList.remove("hidden");$("proto").textContent=d.protocol;
  const rz=(d.realized||[]).filter(r=>r.conc).map(r=>r.well+" "+Math.round(r.vv*100)+"%").join(" · ");
  $("realized").textContent=rz;
  $("dl").onclick=()=>{const b=new Blob([d.protocol],{type:"text/x-python"});const u=URL.createObjectURL(b);
    const a=document.createElement("a");a.href=u;a.download="protocol.py";a.click();setTimeout(()=>URL.revokeObjectURL(u),1500)}}
</script></div></body></html>
"""
