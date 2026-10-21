"""Generate a self-contained HTML report from an EvalReport."""

from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .evaluate import EvalReport


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x * 100:.0f}%"


def generate_html_report(
    report: EvalReport,
    min_trigger: float = 0.8,
    max_false: float = 0.2,
    model: str | None = None,
    date: str | None = None,
) -> str:
    """Return a standalone HTML document summarizing an evaluation run."""
    passed = report.passed(min_trigger, max_false)
    verdict_text = "PASS" if passed else "FAIL"
    verdict_class = "pass" if passed else "fail"
    report_date = date or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    model_str = model or "default"

    tr_pct = _pct(report.trigger_rate)
    fr_pct = _pct(report.false_trigger_rate)
    min_tr_pct = _pct(min_trigger)
    max_fr_pct = _pct(max_false)

    rows = []
    for idx, r in enumerate(report.results, 1):
        prompt_escaped = html.escape(r.prompt)
        expected_str = "Trigger" if r.expected else "Do Not Trigger"

        if r.triggered is None:
            got_str = f"Error: {html.escape(r.error or 'failed')}"
            status_text = "ERROR"
            row_class = "row-error"
        elif r.triggered == r.expected:
            got_str = "Triggered" if r.triggered else "Did Not Trigger"
            status_text = "MATCH"
            row_class = "row-pass"
        elif r.expected and not r.triggered:
            got_str = "Did Not Trigger"
            status_text = "MISSED"
            row_class = "row-miss"
        else:
            got_str = "Triggered"
            status_text = "FALSE TRIGGER"
            row_class = "row-false"

        calls_str = html.escape(", ".join(r.skill_calls)) if r.skill_calls else "—"

        rows.append(
            f"""        <tr class="{row_class}">
          <td>{idx}</td>
          <td class="prompt-cell">{prompt_escaped}</td>
          <td>{expected_str}</td>
          <td>{got_str}</td>
          <td><code>{calls_str}</code></td>
          <td><span class="badge {row_class}">{status_text}</span></td>
        </tr>"""
        )

    rows_html = "\n".join(rows)

    cost_info = f"<div><strong>Cost:</strong> ${report.cost_usd:.4f}</div>" if report.cost_usd else ""
    error_info = (
        f"<div class='warning-box'>⚠️ {report.errors} prompt(s) failed with runtime errors.</div>"
        if report.errors
        else ""
    )
    loaded_info = (
        "<div class='warning-box'>⚠️ The agent did not list this skill as loaded; check frontmatter.</div>"
        if report.skill_not_loaded
        else ""
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>stb eval: {html.escape(report.skill)} ({verdict_text})</title>
  <style>
    :root {{
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #0f172a;
      --text-muted: #64748b;
      --border: #e2e8f0;
      --pass: #16a34a;
      --pass-bg: #f0fdf4;
      --fail: #dc2626;
      --fail-bg: #fef2f2;
      --warn: #d97706;
      --warn-bg: #fffbeb;
    }}
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.5;
      padding: 1.5rem;
    }}
    .container {{
      max-width: 1000px;
      margin: 0 auto;
    }}
    header {{
      background: var(--card-bg);
      padding: 1.5rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      margin-bottom: 1.5rem;
    }}
    .header-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      flex-wrap: wrap;
      gap: 1rem;
      margin-bottom: 1rem;
    }}
    h1 {{
      font-size: 1.5rem;
      font-weight: 700;
      word-break: break-word;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 0.75rem;
      font-size: 0.9rem;
      color: var(--text-muted);
    }}
    .verdict-badge {{
      display: inline-block;
      font-weight: 700;
      font-size: 1.1rem;
      padding: 0.35rem 0.85rem;
      border-radius: 6px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .verdict-badge.pass {{ background: var(--pass-bg); color: var(--pass); border: 1px solid var(--pass); }}
    .verdict-badge.fail {{ background: var(--fail-bg); color: var(--fail); border: 1px solid var(--fail); }}
    .stats-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
      margin-bottom: 1.5rem;
    }}
    .stat-card {{
      background: var(--card-bg);
      padding: 1.25rem;
      border-radius: 8px;
      border: 1px solid var(--border);
    }}
    .stat-label {{
      font-size: 0.85rem;
      color: var(--text-muted);
      margin-bottom: 0.25rem;
    }}
    .stat-val {{
      font-size: 1.75rem;
      font-weight: 700;
    }}
    .stat-sub {{
      font-size: 0.8rem;
      color: var(--text-muted);
    }}
    .warning-box {{
      background: var(--warn-bg);
      color: var(--warn);
      padding: 0.75rem 1rem;
      border-radius: 6px;
      border: 1px solid #fde68a;
      margin-top: 1rem;
      font-size: 0.9rem;
    }}
    .table-container {{
      background: var(--card-bg);
      border-radius: 8px;
      border: 1px solid var(--border);
      overflow-x: auto;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.9rem;
      text-align: left;
    }}
    th, td {{
      padding: 0.75rem 1rem;
      border-bottom: 1px solid var(--border);
    }}
    th {{
      background: #f1f5f9;
      font-weight: 600;
      color: var(--text-muted);
    }}
    .prompt-cell {{
      max-width: 400px;
      word-break: break-word;
    }}
    code {{
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 0.85em;
      background: #f1f5f9;
      padding: 0.15rem 0.35rem;
      border-radius: 4px;
    }}
    .badge {{
      display: inline-block;
      font-size: 0.75rem;
      font-weight: 600;
      padding: 0.2rem 0.5rem;
      border-radius: 4px;
      text-transform: uppercase;
      white-space: nowrap;
    }}
    .badge.row-pass {{ background: var(--pass-bg); color: var(--pass); }}
    .badge.row-miss {{ background: var(--fail-bg); color: var(--fail); }}
    .badge.row-false {{ background: var(--fail-bg); color: var(--fail); }}
    .badge.row-error {{ background: #fef3c7; color: #b45309; }}
    tr.row-miss, tr.row-false {{ background: #fff5f5; }}
    tr.row-error {{ background: #fffbeb; }}
    tr:last-child td {{ border-bottom: none; }}
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div class="header-top">
        <div>
          <h1>Skill: {html.escape(report.skill)}</h1>
        </div>
        <div>
          <span class="verdict-badge {verdict_class}">{verdict_text}</span>
        </div>
      </div>
      <div class="meta">
        <div><strong>Runner:</strong> {html.escape(report.runner)}</div>
        <div><strong>Model:</strong> {html.escape(model_str)}</div>
        <div><strong>Date:</strong> {html.escape(report_date)}</div>
        {cost_info}
      </div>
      {error_info}
      {loaded_info}
    </header>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-label">Trigger Rate</div>
        <div class="stat-val">{tr_pct}</div>
        <div class="stat-sub">Threshold: &ge; {min_tr_pct}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">False Trigger Rate</div>
        <div class="stat-val">{fr_pct}</div>
        <div class="stat-sub">Threshold: &le; {max_fr_pct}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">Evaluated Prompts</div>
        <div class="stat-val">{len(report.results)}</div>
        <div class="stat-sub">{report.errors} error(s)</div>
      </div>
    </div>

    <div class="table-container">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Prompt</th>
            <th>Expected</th>
            <th>Result</th>
            <th>Skill Calls</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
{rows_html}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""
