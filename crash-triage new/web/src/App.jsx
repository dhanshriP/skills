import { useState, useEffect, useRef } from "react";
import { api } from "./api.js";

const SAMPLE = `Fatal Exception: java.lang.NullPointerException
  at com.bank.payments.TransferReviewFragment.confirm(TransferReviewFragment.kt:214)
  at com.bank.payments.TransferViewModel.submit(TransferViewModel.kt:88)
--- Breadcrumbs ---
[t-3s] tap: recipient_select acct=4716 1234 5678 9012
[t-0s] tap: confirm_transfer (double-tap)`;

const STAGES = [
  ["ingest", "Ingest"], ["symbolicate", "Symbolicate"], ["redact", "Redact PII"],
  ["rootcause", "Root cause"], ["owners", "Owners"], ["solutions", "Solutions"], ["draftpr", "Draft PR"],
];

const reduced = () => window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const sleep = (ms) => new Promise((r) => setTimeout(r, reduced() ? 0 : ms));

function IdleHero() {
  return (
    <div className="idle">
      <div className="idle-glyph">⌘</div>
      <h2 className="idle-title">From crash to fix, triaged.</h2>
      <p className="idle-sub">Paste a stacktrace and run Analyze — symbolicate, redact PII, find the root cause, and route it to an owner in one pass.</p>
      <div className="pipe standby">
        {STAGES.map(([id, label], i) => (
          <div key={id} className="pipe-step pending">
            <div className="pipe-dot" style={{ animationDelay: `${i * 0.18}s` }} />
            <div className="pipe-label">{label}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

function Pipeline({ stages }) {
  return (
    <div className="pipe">
      {STAGES.map(([id, label]) => (
        <div key={id} className={`pipe-step ${stages[id] || "pending"}`}>
          <div className="pipe-dot">{stages[id] === "done" ? "✓" : stages[id] === "error" ? "!" : stages[id] === "skipped" ? "–" : ""}</div>
          <div className="pipe-label">{label}</div>
        </div>
      ))}
    </div>
  );
}

function Verdict({ ai }) {
  const sev = (ai.severity || "P3").toUpperCase();
  const exc = (ai.root_cause || "").split(".")[0] || "Crash analyzed";
  const halt = sev === "P1";
  return (
    <div className={`verdict ${sev}`}>
      <div className="sevbig">{sev}</div>
      <div className="vmain">
        <div className="vflow">{ai.flow || "unknown flow"} · {ai.internal_module || "module"}</div>
        <div className="vtitle">{exc}</div>
      </div>
      <div className={`vpill ${halt ? "halt" : "track"}`}>{halt ? "Halt-worthy" : "Track & fix"}</div>
    </div>
  );
}

function StatusChip({ label, status }) {
  const map = { ok: "ok", symbolicated: "ok", error: "halt", raw: "halt", skipped: "neutral", partial: "warn" };
  return <span className={`chip ${map[status] || "neutral"}`}>{label} {status}</span>;
}

function Confidence({ value }) {
  const [n, setN] = useState(0);
  const [w, setW] = useState(0);
  useEffect(() => {
    if (reduced()) { setN(value); setW(value); return; }
    setW(value);
    let cur = 0; const step = Math.max(1, Math.round(value / 28));
    const t = setInterval(() => { cur += step; if (cur >= value) { cur = value; clearInterval(t); } setN(cur); }, 24);
    return () => clearInterval(t);
  }, [value]);
  const color = value >= 70 ? "var(--ok)" : value >= 40 ? "var(--warn)" : "var(--halt)";
  return (
    <div className="field full">
      <div className="k">Confidence — <span className="conf-num">{n}%</span></div>
      <div className="conf-bar"><div className="conf-fill" style={{ width: `${w}%`, background: color }} /></div>
    </div>
  );
}

export default function App() {
  const [form, setForm] = useState({
    platform: "Android", version: "5.2.1", build: "5210", stacktrace: SAMPLE,
    android_mapping: "", ios_dsym_path: "", flow_hint: "Transfer", appd_crash_id: "",
  });
  const [stages, setStages] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [copied, setCopied] = useState(false);

  const [sol, setSol] = useState(null);
  const [solBusy, setSolBusy] = useState(false);
  const [picked, setPicked] = useState(null);
  const [alsoJira, setAlsoJira] = useState(true);
  const [prOut, setPrOut] = useState(null);
  const [prBusy, setPrBusy] = useState(false);
  const [decided, setDecided] = useState(false);
  const started = useRef(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  function softReset() { setSol(null); setPicked(null); setPrOut(null); setDecided(false); }

  async function cascade(updates) {
    for (const [id, st] of updates) {
      setStages((s) => ({ ...s, [id]: "running" }));
      await sleep(170);
      setStages((s) => ({ ...s, [id]: st }));
      await sleep(110);
    }
  }

  async function analyze() {
    setBusy(true); setErr(""); setResult(null); softReset();
    started.current = true;
    setStages({ ingest: "pending", symbolicate: "pending", redact: "pending", rootcause: "pending", owners: "pending", solutions: "pending", draftpr: "pending" });
    try {
      const data = await api.analyze(form);
      if (data.error) { setErr(data.error); setBusy(false); return; }
      const sec = data.sections || {}, git = data.git || {};
      await cascade([
        ["ingest", "done"],
        ["symbolicate", sec.symbolication ? (sec.symbolication.status === "raw" ? "error" : "done") : "done"],
        ["redact", "done"],
        ["rootcause", sec.llm ? (sec.llm.status === "ok" ? "done" : "error") : "done"],
        ["owners", git.status === "ok" ? "done" : "skipped"],
      ]);
      setResult(data);
    } catch (e) { setErr(String(e.message || e)); }
    finally { setBusy(false); }
  }

  async function findSolutions() {
    if (!result) return;
    setSolBusy(true); setPicked(null); setPrOut(null); setDecided(false);
    setStages((s) => ({ ...s, solutions: "running" }));
    const ai = result.ai || {};
    try {
      const data = await api.solutions({
        root_cause: ai.root_cause || "", exception: (form.stacktrace.split("\n")[0] || "").slice(0, 120),
        platform: form.platform, internal_module: ai.internal_module || "", suspected_file: ai.suspected_file || "",
      });
      setSol(data);
      if (typeof data.recommended_index === "number") setPicked(data.recommended_index);
      setStages((s) => ({ ...s, solutions: (data.solutions && data.solutions.length) ? "done" : "error" }));
    } catch (e) { setErr(String(e.message || e)); setStages((s) => ({ ...s, solutions: "error" })); }
    finally { setSolBusy(false); }
  }

  async function implement() {
    const ai = result.ai || {}, git = result.git || {};
    const chosen = sol.solutions[picked];
    const sources = (chosen.sources || []).map((i) => (sol.sources[i] || {}).link).filter(Boolean);
    setPrBusy(true); setDecided(true);
    setStages((s) => ({ ...s, draftpr: "running" }));
    try {
      const data = await api.implementPr({
        solution_title: chosen.title, solution_approach: chosen.approach, root_cause: ai.root_cause || "",
        platform: form.platform, suspected_file: ai.suspected_file || "", sources,
        reviewers: git.reviewers_to_loop_in || [], primary_owner_suspect: git.primary_owner_suspect || "",
        create_jira: alsoJira, severity: ai.severity || "", flow: ai.flow || "",
        version: form.version, build: form.build, internal_module: ai.internal_module || "",
      });
      setPrOut(data);
      setStages((s) => ({ ...s, draftpr: data.pr && data.pr.status === "ok" ? "done" : "error" }));
    } catch (e) { setPrOut({ status: "error", note: String(e.message || e) }); setStages((s) => ({ ...s, draftpr: "error" })); }
    finally { setPrBusy(false); }
  }

  function decline() { setDecided(true); setPrOut({ status: "declined" }); setStages((s) => ({ ...s, draftpr: "skipped" })); }
  function copyTrace() { navigator.clipboard && navigator.clipboard.writeText(form.stacktrace); setCopied(true); setTimeout(() => setCopied(false), 1200); }

  const ios = form.platform === "iOS";

  return (
    <div className="wrap">
      <div className="topbar">
        <span className="logo"><span className="mark" />Crash<b>Triage</b></span>
        <span className="sub">// appdynamics → ai → solutions → pr</span>
        <span className="tag">Local build</span>
        <span className="spacer" />
        <span className="sub">model: env LLM_MODEL</span>
      </div>
      <div className="notice"><span>⚠</span><span>Synthetic data only while testing. PII is redacted server-side before the model sees anything. PRs open as drafts for human review — nothing merges automatically.</span></div>

      <div className="grid">
        <div className="panel">
          <div className="panel-head">Crash input</div>
          <div className="form">
            <div className="row">
              <div><label>Platform</label><select value={form.platform} onChange={set("platform")}><option>Android</option><option>iOS</option></select></div>
              <div><label>Version</label><input value={form.version} onChange={set("version")} /></div>
              <div><label>Build</label><input value={form.build} onChange={set("build")} /></div>
            </div>
            <label>Stacktrace</label>
            <div className="trace-wrap">
              <textarea value={form.stacktrace} onChange={set("stacktrace")} spellCheck={false} />
              <button type="button" className="copy-btn" onClick={copyTrace}>{copied ? "copied" : "copy"}</button>
            </div>
            {ios ? (
              <div style={{ margin: "14px 0" }}>
                <label>iOS dSYM path (server-side — dSYM is binary)</label>
                <input value={form.ios_dsym_path} onChange={set("ios_dsym_path")} placeholder="/path/to/MyApp.app.dSYM" />
              </div>
            ) : (
              <div style={{ margin: "14px 0" }}>
                <label>Android mapping.txt (paste — for retrace)</label>
                <textarea style={{ minHeight: 84 }} value={form.android_mapping} onChange={set("android_mapping")} spellCheck={false} placeholder={"com.bank.payments.TransferReviewFragment -> a.b.c:"} />
              </div>
            )}
            <div className="row">
              <div><label>Flow hint</label><input value={form.flow_hint} onChange={set("flow_hint")} /></div>
              <div><label>AppD crash id</label><input value={form.appd_crash_id} onChange={set("appd_crash_id")} placeholder="optional" /></div>
            </div>
            <button className="btn-primary" onClick={analyze} disabled={busy} style={{ width: "100%" }}>{busy ? "Analyzing…" : "Analyze crash"}</button>
            <p className="disclaim">With an AppDynamics crash id and the server configured, the trace is pulled automatically; otherwise the pasted trace is used.</p>
          </div>
        </div>

        <div className="panel">
          <div className="panel-head"><span className="pip" />Analysis · auto-generated · human approval required</div>
          <div className="out">
            {started.current && <Pipeline stages={stages} />}
            {err && <div className="err">{err}</div>}
            {!started.current && !err && <IdleHero />}
            {result && <div className="reveal"><Verdict ai={result.ai || {}} /><Analysis result={result} /></div>}

            {result && (
              <>
                <div className="group-label lower">Possible solutions</div>
                {!sol && !solBusy && <button className="btn-ghost" onClick={findSolutions}>Search the web for solutions</button>}
                {solBusy && <div className="reveal"><div className="skel"><div className="skel-line" style={{ width: "60%" }} /><div className="skel-line" /><div className="skel-line" style={{ width: "80%" }} /></div><div className="skel"><div className="skel-line" style={{ width: "50%" }} /><div className="skel-line" /></div></div>}
                {sol && <div className="reveal"><Solutions sol={sol} picked={picked} setPicked={(i) => { setPicked(i); setDecided(false); setPrOut(null); }} /></div>}
              </>
            )}

            {sol && sol.solutions && sol.solutions.length > 0 && picked != null && !decided && (
              <div className="reveal">
                <div className="group-label lower">Implement?</div>
                <div className="prompt">
                  <span>Implement “{sol.solutions[picked].title}” in your lib and raise a PR?</span>
                  <label className="inline"><input type="checkbox" checked={alsoJira} onChange={(e) => setAlsoJira(e.target.checked)} /> also create Jira</label>
                  <div className="prompt-btns">
                    <button className="btn-primary" onClick={implement}>Yes — implement &amp; raise PR</button>
                    <button className="btn-ghost" onClick={decline}>No</button>
                  </div>
                </div>
              </div>
            )}

            {prBusy && <div className="loading"><div className="spinner" /><div>Generating patch & opening draft PR…</div></div>}
            {prOut && !prBusy && <div className="reveal"><PrResult out={prOut} /></div>}
          </div>
        </div>
      </div>
    </div>
  );
}

function Analysis({ result }) {
  const ai = result.ai || {}, git = result.git || {}, sec = result.sections || {};
  const conf = Math.max(0, Math.min(100, Number(ai.confidence) || 0));
  const sev = (ai.severity || "P3").toUpperCase();
  const red = (sec.redaction && sec.redaction.findings) || [];
  const reviewers = (git.reviewers_to_loop_in || []).join(", ") || "—";
  return (
    <>
      <div className="statusbar">
        {sec.symbolication && <StatusChip label="symbolication" status={sec.symbolication.status} />}
        {sec.llm && <StatusChip label="model" status={sec.llm.status} />}
        {git.status && <StatusChip label="git" status={git.status} />}
        {sec.appdynamics && <StatusChip label="appd" status={sec.appdynamics.status} />}
      </div>
      <div className="group-label">Inferred from the trace · AI</div>
      <div className="ev-grid">
        <div className="field"><div className="k">Severity</div><div className={`sev ${sev}`}>{sev}</div></div>
        <div className="field"><div className="k">Affected flow</div><div className="v mono">{ai.flow || "—"}</div></div>
        <div className="field"><div className="k">Is it our code?</div><div className="v">{ai.is_app_code === false ? <span className="chip neutral">no — {ai.internal_module || "third-party/OS"}</span> : <span className="chip ok">yes — app code</span>}</div></div>
        <div className="field"><div className="k">Internal module / lib</div><div className="v mono">{ai.internal_module || "—"}</div></div>
        <div className="field full"><div className="k">Root-cause hypothesis</div><p className="reason">{ai.root_cause || "—"}</p></div>
        <div className="field"><div className="k">Suspected file:line</div><div className="v mono">{ai.suspected_file || "—"}{ai.suspected_line ? `:${ai.suspected_line}` : ""}</div></div>
        <div className="field"><div className="k">Owner hint (team)</div><div className="v mono">{ai.owner_hint || "—"}</div></div>
        <div className="field full"><div className="k">Sensitive-data scan</div><div className="v">{red.length ? <span className="chip halt">⚠ redacted: {red.map((f) => `${f.type}×${f.count}`).join(", ")}</span> : <span className="chip ok">none detected</span>}</div></div>
        <Confidence value={conf} />
      </div>
      <div className="group-label lower">Resolved from git · suspect leads</div>
      <div className="ev-grid">
        <div className="field full"><div className="k">Suspect PR</div><div className="v">{git.pr ? <a className="lnk" href={git.pr.url} target="_blank" rel="noopener">PR #{git.pr.number}</a> : <span className="v mono" style={{ color: "var(--faint)" }}>{git.note || "not resolved"}</span>}</div></div>
        <div className="field"><div className="k">Primary owner — last committer (suspect)</div><div className="v mono">{git.primary_owner_suspect || "—"}</div></div>
        <div className="field"><div className="k">Reviewers to loop in</div><div className="v mono">{reviewers}</div></div>
      </div>
    </>
  );
}

function Solutions({ sol, picked, setPicked }) {
  const sec = sol.sections || {};
  if (!sol.solutions || sol.solutions.length === 0) return <div className="err">No solutions produced. {(sec.llm && sec.llm.note) || ""}</div>;
  return (
    <>
      {sec.search && <div className="statusbar"><StatusChip label="web search" status={sec.search.status} /></div>}
      {sol.solutions.map((s, i) => (
        <div key={i} className={`sol ${picked === i ? "sel" : ""}`} onClick={() => setPicked(i)}>
          <div className="sol-head">
            <span className="radio" />
            <span className="sol-title">{s.title}</span>
            {i === sol.recommended_index && <span className="badge best">recommended</span>}
            <span className={`badge risk-${(s.risk || "").toLowerCase()}`}>risk: {s.risk || "?"}</span>
          </div>
          <p>{s.approach}</p>
          {s.pros && <p><b>Pros:</b> {s.pros}</p>}
          {s.cons && <p><b>Cons:</b> {s.cons}</p>}
          {Array.isArray(s.sources) && s.sources.length > 0
            ? <p className="src">Sources: {s.sources.map((idx, k) => { const src = sol.sources[idx]; return src ? <a key={k} className="lnk" href={src.link} target="_blank" rel="noopener" style={{ marginRight: 6 }}>[{idx}]</a> : null; })}</p>
            : <p className="src" style={{ color: "var(--warn)" }}>general knowledge — not grounded in a source</p>}
        </div>
      ))}
    </>
  );
}

function PrResult({ out }) {
  if (out.status === "declined") return <p className="disclaim">No PR raised.</p>;
  if (out.status === "skipped") return <p className="disclaim">Skipped: {out.note}</p>;
  return (
    <div className="ev-grid">
      {out.jira && <div className="field"><div className="k">Jira</div><div className="v">{out.jira.status === "ok" ? <a className="lnk" href={out.jira.url} target="_blank" rel="noopener">{out.jira.key}</a> : <span className="v mono" style={{ color: "var(--faint)" }}>{out.jira.note}</span>}</div></div>}
      {out.pr && <div className="field full"><div className="k">Draft PR {out.applied === false ? "(patch attached — didn’t apply cleanly)" : "(change applied)"}</div><div className="v">{out.pr.status === "ok" ? <a className="lnk" href={out.pr.url} target="_blank" rel="noopener">{out.pr.branch}</a> : <span className="v mono" style={{ color: "var(--halt)" }}>{out.pr.note}</span>}</div></div>}
      {out.note && !out.pr && <div className="field full"><div className="v mono" style={{ color: "var(--faint)" }}>{out.note}</div></div>}
      <div className="field full"><p className="disclaim">Draft only. The change is AI-generated — review for correctness, security, and license against the cited sources before taking it out of draft.</p></div>
    </div>
  );
}
