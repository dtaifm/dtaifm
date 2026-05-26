#!/usr/bin/env python3
"""Phase-0 PROTOTYPE — render a dtaifm audit bundle as a static, read-only HTML report.

Design issue: https://github.com/dtaifm/dtaifm/issues/17

This is a DEMO ARTIFACT, not a shipped feature and not a supported UI surface.
It only *visualizes* a `.dtaifm-review.json` bundle:

  * no teacher calls, no API keys
  * no mutation, no live config writes, no "deploy" controls
  * no new dependencies and no JavaScript — HTML is built with the standard
    library only. The single dtaifm import is the read-only `replay()` used to
    show verification status; if dtaifm is not importable the report still
    renders (replay status falls back to "not computed").

Usage:
    python generate_report.py [bundle.json] [out.html]

Both arguments default to the files checked in next to this script.
"""
from __future__ import annotations

import html
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_BUNDLE = HERE / "sample-review.dtaifm-review.json"
DEFAULT_OUT = HERE / "audit-report.html"


def esc(value: object) -> str:
    return html.escape(str(value))


def replay_status(bundle: dict) -> tuple[str, str]:
    """(label, css_class) for the bundle's deterministic replay. Read-only; never raises."""
    try:
        from dtaifm.bundle import replay
        result = replay(bundle)
        if result.success:
            return "PASSED — deterministic replay reproduced every hash", "ok"
        return "FAILED — " + "; ".join(result.issues), "bad"
    except Exception as exc:  # noqa: BLE001 - a prototype must never fail to render
        return f"not computed ({exc})", "muted"


def _rules_block(rules: list[dict]) -> str:
    out = []
    for r in rules:
        status = r["status"]
        cls = "ok" if status == "approved" else "bad"
        out.append(f'<div class="rule {cls}"><span class="badge {cls}">{esc(status.upper())}</span> '
                   f'<code>{esc(r["id"])}</code> &mdash; {esc(r["name"])}')
        if r.get("violations"):
            out.append('<ul class="violations">')
            for v in r["violations"]:
                out.append(f'<li><code>{esc(v["constraint_id"])}</code>: {esc(v["reason"])}</li>')
            out.append('</ul>')
        out.append('</div>')
    return "\n".join(out) or '<p class="muted">(none)</p>'


def _trace_block(trace: list[dict]) -> str:
    out = []
    for t in trace:
        cls = "ok" if t["fired"] else "muted"
        mark = "FIRED" if t["fired"] else "SKIPPED"
        out.append(f'<div class="trace {cls}"><span class="badge {cls}">{mark}</span> '
                   f'<code>{esc(t["rule_id"])}</code> &mdash; {esc(t["reason"])}')
        if t.get("conditions_evaluated"):
            out.append('<ul class="conds">')
            for c in t["conditions_evaluated"]:
                ok = "ok" if c["passed"] else "bad"
                out.append(f'<li><code>{esc(c["type"])}</code> {esc(dict(c["parameters"]))} '
                           f'&rarr; <span class="badge {ok}">{"PASS" if c["passed"] else "FAIL"}</span></li>')
            out.append('</ul>')
        out.append('</div>')
    return "\n".join(out) or '<p class="muted">(no trace)</p>'


def render(bundle: dict) -> str:
    dom = bundle["domain"]
    val = bundle["validation"]["result"]
    exe = bundle["execution"]["result"]
    rules = val.get("rules", [])
    approved = [r for r in rules if r["status"] == "approved"]
    rejected = [r for r in rules if r["status"] == "rejected"]
    label, rcls = replay_status(bundle)

    proposals = "".join(
        f'<li><code>{esc(p["proposal_id"])}</code> &middot; proposed_by '
        f'<strong>{esc(p["proposed_by"] or "(none)")}</strong> &middot; '
        f'{len(p["rule_ids"])} rule(s) &middot; {esc(p["created_at"] or "(none)")}</li>'
        for p in bundle.get("proposals", [])
    ) or '<li class="muted">(none)</li>'

    actions = "".join(
        f'<li><code>{esc(a["rule_id"])}</code> &rarr; {esc(a["device"])}.{esc(a["action"])} '
        f'{esc(a.get("parameters") or "")}</li>'
        for a in exe.get("actions_taken", [])
    ) or '<li class="muted">(no actions)</li>'

    def hash_row(label_, h):
        return f'<tr><td>{esc(label_)}</td><td><code>{esc(h)}</code></td></tr>'

    hashes = "".join([
        hash_row("constraints", bundle["inputs"]["constraints"]["hash"]),
        hash_row("rules", bundle["inputs"]["rules"]["hash"]),
        hash_row("state", bundle["inputs"]["state"]["hash"]),
        hash_row("validation", bundle["validation"]["hash"]),
        hash_row("execution", bundle["execution"]["hash"]),
    ])

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>dtaifm audit report &mdash; {esc(dom['id'])}</title>
<style>
  :root {{ --ok:#1a7f37; --bad:#b60205; --muted:#6e7781; --line:#d0d7de; --bg:#f6f8fa; }}
  * {{ box-sizing:border-box; }}
  body {{ font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif; margin:0; color:#1f2328; }}
  .wrap {{ max-width:920px; margin:0 auto; padding:24px; }}
  .proto {{ background:#fff8c5; border:1px solid #d4a72c; border-radius:6px; padding:10px 14px; font-size:13px; }}
  h1 {{ font-size:22px; margin:18px 0 2px; }}
  h2 {{ font-size:16px; margin:26px 0 8px; border-bottom:1px solid var(--line); padding-bottom:4px; }}
  .sub {{ color:var(--muted); font-size:13px; }}
  .card {{ background:var(--bg); border:1px solid var(--line); border-radius:6px; padding:12px 16px; margin:8px 0; }}
  .badge {{ display:inline-block; font-size:11px; font-weight:600; padding:1px 7px; border-radius:10px; color:#fff; }}
  .badge.ok {{ background:var(--ok); }} .badge.bad {{ background:var(--bad); }} .badge.muted {{ background:var(--muted); }}
  .rule, .trace {{ padding:6px 0; border-bottom:1px dashed var(--line); }}
  .violations, .conds {{ margin:4px 0 4px 18px; color:#57606a; font-size:13px; }}
  .muted {{ color:var(--muted); }}
  code {{ background:rgba(175,184,193,.2); padding:.1em .3em; border-radius:4px; font-size:12px; }}
  table {{ border-collapse:collapse; width:100%; font-size:13px; }}
  td {{ border-bottom:1px solid var(--line); padding:4px 6px; vertical-align:top; }}
  td:first-child {{ width:120px; color:var(--muted); }}
  .grid {{ display:flex; gap:18px; flex-wrap:wrap; }}
  .grid div {{ flex:1; min-width:140px; }}
  .num {{ font-size:22px; font-weight:700; }}
</style></head>
<body><div class="wrap">

<div class="proto"><strong>Static audit-viewer prototype</strong> &middot; design issue
  <a href="https://github.com/dtaifm/dtaifm/issues/17">#17</a>. Read-only visualization of a
  <code>.dtaifm-review.json</code> bundle &mdash; <strong>no execution, no teacher, no mutation</strong>.
  Not a supported UI surface.</div>

<h1>dtaifm audit report</h1>
<p class="sub">domain <strong>{esc(dom['id'])}</strong> v{esc(dom['version'])} &middot;
  bundle {esc(bundle.get('bundle_version'))} &middot; framework {esc(bundle.get('framework_version'))} &middot;
  schema {esc(bundle.get('schema_version'))} &middot; created {esc(bundle.get('created_at'))}</p>

<div class="card"><span class="badge {rcls}">REPLAY</span> {esc(label)}</div>

<div class="card grid">
  <div><div class="num">{val['approved_count']}</div><div class="sub">approved</div></div>
  <div><div class="num">{val['rejected_count']}</div><div class="sub">rejected</div></div>
  <div><div class="num">{len(exe.get('triggered_rule_ids', []))}</div><div class="sub">rules fired</div></div>
</div>

<h2>Proposals</h2><ul>{proposals}</ul>

<h2>Approved rules</h2>{_rules_block(approved)}
<h2>Rejected rules &amp; violations</h2>{_rules_block(rejected)}

<h2>Execution &mdash; {esc(exe['event']['device'])}.{esc(exe['event']['type'])}</h2>
<p class="sub">triggered: {esc(exe.get('triggered_rule_ids') or '(none)')}</p>
<strong>Actions taken</strong><ul>{actions}</ul>
<strong>Trace</strong>{_trace_block(exe.get('trace', []))}

<h2>Hashes (tamper-evident; <code>sha256</code> over canonical JSON)</h2>
<table>{hashes}</table>

<p class="sub" style="margin-top:28px">Generated by <code>generate_report.py</code> (stdlib only) from a
  checked-in bundle produced by <code>dtaifm demo smart_home</code>. Regenerate:
  <code>python generate_report.py</code>.</p>

</div></body></html>
"""


def main(argv: list[str]) -> int:
    bundle_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_BUNDLE
    out_path = Path(argv[2]) if len(argv) > 2 else DEFAULT_OUT
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    out_path.write_text(render(bundle), encoding="utf-8")
    print(f"wrote {out_path} from {bundle_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
