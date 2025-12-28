from __future__ import annotations

from datetime import datetime
from html import unescape
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
UPDATES_DIR = ROOT / "private" / "updates"
TEMPLATE_PATH = ROOT / "private" / "dev" / "dashboard.template.html"
OUTPUT_PATH = ROOT / "private" / "dev" / "dashboard.html"
REPO_TEMPLATE_PATH = ROOT / "private" / "dev" / "repo.template.html"


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts)
    except ValueError:
        if ts.endswith("Z"):
            try:
                return datetime.fromisoformat(ts[:-1] + "+00:00")
            except ValueError:
                return None
    return None


def _strip_tags(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value).strip()


def _indent_block(text: str, spaces: int) -> str:
    pad = " " * spaces
    return "\n".join(pad + line if line.strip() else line for line in text.splitlines())


def _extract_section(html: str) -> str:
    match = re.search(r"(<section[^>]*>.*?</section>)", html, re.S)
    if match:
        return match.group(1).strip()
    return html.strip()


def _repo_page_filename(repo: str) -> str:
    if repo.startswith("repo-"):
        return f"{repo}.html"
    return f"repo-{repo}.html"


def _extract_articles(section_html: str) -> list[dict]:
    articles = []
    for status, time_raw, body in re.findall(
        r'<article[^>]*data-status="([^"]+)"[^>]*data-time="([^"]+)"[^>]*>(.*?)</article>',
        section_html,
        re.S,
    ):
        summary = ""
        stage = ""
        notes = ""
        h4_match = re.search(r"<h4>(.*?)</h4>", body, re.S)
        if h4_match:
            summary = _strip_tags(unescape(h4_match.group(1)))
        stage_match = re.search(r"<strong>Stage:</strong>\s*([^<]+)", body, re.S)
        if stage_match:
            stage = _strip_tags(unescape(stage_match.group(1)))
        notes_match = re.search(r"<strong>Notes:</strong>\s*([^<]+)", body, re.S)
        if notes_match:
            notes = _strip_tags(unescape(notes_match.group(1)))

        parsed_time = _parse_iso(time_raw)
        if parsed_time:
            time_display = parsed_time.strftime("%Y-%m-%d %H:%M %z").strip()
        else:
            time_display = time_raw

        articles.append(
            {
                "status": status.strip() or "unknown",
                "time_raw": time_raw.strip(),
                "time_display": time_display,
                "summary": summary,
                "stage": stage,
                "notes": notes,
                "sort_key": parsed_time or datetime.min,
            }
        )
    return articles


def _parse_update_file(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    section_html = _extract_section(raw)

    section_match = re.search(
        r'<section[^>]*data-repo="([^"]+)"[^>]*data-agent="([^"]+)"',
        section_html,
    )
    repo = section_match.group(1) if section_match else path.stem.replace("updates-", "")
    agent = section_match.group(2) if section_match else "unknown"

    articles = _extract_articles(section_html)
    latest = articles[0] if articles else {}
    status = latest.get("status", "unknown")
    time_raw = latest.get("time_raw", "")
    summary = latest.get("summary", "")
    parsed_time = latest.get("sort_key")
    time_display = latest.get("time_display", time_raw)

    return {
        "repo": repo,
        "agent": agent,
        "status": status or "unknown",
        "time_raw": time_raw,
        "time_display": time_display,
        "summary": summary,
        "section_html": section_html,
        "sort_key": parsed_time or datetime.min,
        "articles": articles,
    }


def build_dashboard() -> None:
    update_files = sorted(UPDATES_DIR.glob("updates-*.html"))
    updates = [_parse_update_file(path) for path in update_files]
    updates.sort(key=lambda item: item["sort_key"], reverse=True)

    rows = []
    history_blocks = []
    server_rail = [
        "      <a class=\"server-dot active\" href=\"dashboard.html\" title=\"Dashboard\">CD</a>"
    ]

    repo_template = REPO_TEMPLATE_PATH.read_text(encoding="utf-8")

    if not updates:
        rows.append(
            "            <tr>"
            "<td data-label=\"Repo\">-</td>"
            "<td data-label=\"Latest Status\"><span class=\"status-pill error\">Missing</span></td>"
            "<td data-label=\"Last Update\">-</td>"
            "<td data-label=\"Agent\">-</td>"
            "<td data-label=\"Summary\">No updates found</td>"
            "</tr>"
        )
    else:
        def badge_label(repo: str) -> str:
            parts = [part for part in re.split(r"[^A-Za-z0-9]+", repo) if part]
            if not parts:
                return "RP"
            if len(parts) == 1:
                token = parts[0][:2]
            else:
                token = "".join(part[0] for part in parts[:2])
            return token.upper()

        for item in updates:
            server_rail.append(
                f"      <a class=\"server-dot\" href=\"{_repo_page_filename(item['repo'])}\" title=\"{item['repo']}\">{badge_label(item['repo'])}</a>"
            )
            status_label = item["status"].capitalize()
            repo_slug = item["repo"]
            rows.append(
                "            <tr>\n"
                f"              <td data-label=\"Repo\"><a class=\"repo-link\" href=\"{_repo_page_filename(repo_slug)}\">{repo_slug}</a></td>\n"
                f"              <td data-label=\"Latest Status\"><span class=\"status-pill {item['status']}\">{status_label}</span></td>\n"
                f"              <td data-label=\"Last Update\">{item['time_display']}</td>\n"
                f"              <td data-label=\"Agent\">{item['agent']}</td>\n"
                f"              <td data-label=\"Summary\">{item['summary']}</td>\n"
                "            </tr>"
            )

            history_blocks.append(
                "          <div class=\"repo-block\">\n"
                "            <div class=\"repo-header\">\n"
                f"              <h3>{item['repo']}</h3>\n"
                f"              <span>Agent: {item['agent']}</span>\n"
                "            </div>\n"
                f"{_indent_block(item['section_html'], 12)}\n"
                "          </div>"
            )

            articles = item.get("articles", [])
            latest = articles[0] if articles else {}
            latest_status = latest.get("status", "unknown")
            latest_status_label = latest_status.capitalize()
            latest_summary = latest.get("summary", "No updates yet")
            latest_stage = latest.get("stage", "update")
            latest_time = latest.get("time_display", "-")
            recent_incident = next((a for a in articles if a.get("status") == "error"), None)
            recent_outcome_title = (
                recent_incident.get("summary") if recent_incident else "No incidents"
            )
            recent_outcome_note = (
                recent_incident.get("notes")
                if recent_incident and recent_incident.get("notes")
                else "Latest activity looks healthy."
            )

            activity_items = []
            for activity in articles[:3]:
                activity_items.append(
                    "          <li class=\"activity-item\">\n"
                    "            <div>\n"
                    f"              <strong>{activity.get('summary') or 'Update'}</strong>\n"
                    f"              <div class=\"item-meta\">Stage: {activity.get('stage') or 'update'}</div>\n"
                    "            </div>\n"
                    f"            <div class=\"item-meta\">{activity.get('time_display') or '-'}</div>\n"
                    "          </li>"
                )
            if not activity_items:
                activity_items.append(
                    "          <li class=\"activity-item\">\n"
                    "            <div>\n"
                    "              <strong>No activity recorded yet</strong>\n"
                    "              <div class=\"item-meta\">Add updates to populate this feed.</div>\n"
                    "            </div>\n"
                    "            <div class=\"item-meta\">-</div>\n"
                    "          </li>"
                )

            incident_items = []
            for incident in [a for a in articles if a.get("status") == "error"]:
                incident_items.append(
                    "          <li class=\"incident-item\">\n"
                    "            <div>\n"
                    f"              <strong>{incident.get('summary') or 'Incident'}</strong>\n"
                    f"              <div class=\"item-meta\">{incident.get('notes') or 'Details in update log.'}</div>\n"
                    "            </div>\n"
                    f"            <div class=\"item-meta\">{incident.get('time_display') or '-'}</div>\n"
                    "          </li>"
                )
            if not incident_items:
                incident_items.append(
                    "          <li class=\"incident-item\">\n"
                    "            <div>\n"
                    "              <strong>No incidents reported</strong>\n"
                    "              <div class=\"item-meta\">All clear in recent updates.</div>\n"
                    "            </div>\n"
                    "            <div class=\"item-meta\">-</div>\n"
                    "          </li>"
                )

            completed = len([a for a in articles if a.get("status") == "complete"])
            errors = len([a for a in articles if a.get("status") == "error"])
            total = completed + errors
            success_rate = f"{round((completed / total) * 100)}%" if total else "N/A"

            metric_cards = "\n".join(
                [
                    "          <div class=\"metric-card\">\n"
                    "            <span>Success rate</span>\n"
                    f"            <strong>{success_rate}</strong>\n"
                    "            <div class=\"item-meta\">Recent updates</div>\n"
                    "          </div>",
                    "          <div class=\"metric-card\">\n"
                    "            <span>Total updates</span>\n"
                    f"            <strong>{len(articles)}</strong>\n"
                    "            <div class=\"item-meta\">Logged entries</div>\n"
                    "          </div>",
                    "          <div class=\"metric-card\">\n"
                    "            <span>Open incidents</span>\n"
                    f"            <strong>{errors}</strong>\n"
                    "            <div class=\"item-meta\">Error entries</div>\n"
                    "          </div>",
                    "          <div class=\"metric-card\">\n"
                    "            <span>Last update</span>\n"
                    f"            <strong>{latest_time or '-'}</strong>\n"
                    "            <div class=\"item-meta\">Most recent entry</div>\n"
                    "          </div>",
                ]
            )

            experiment_items = "\n".join(
                [
                    "          <li class=\"experiment-item\">\n"
                    "            <div>\n"
                    "              <strong>Experiment backlog</strong>\n"
                    "              <div class=\"item-meta\">Status: pending · Capture experiments in updates.</div>\n"
                    "            </div>\n"
                    f"            <div class=\"item-meta\">Owner: {item['agent']}</div>\n"
                    "          </li>",
                    "          <li class=\"experiment-item\">\n"
                    "            <div>\n"
                    "              <strong>Automation improvements</strong>\n"
                    "              <div class=\"item-meta\">Status: planning · Track automation tweaks.</div>\n"
                    "            </div>\n"
                    "            <div class=\"item-meta\">Owner: engineering</div>\n"
                    "          </li>",
                ]
            )

            repo_server_rail = [
                "      <a class=\"server-dot\" href=\"dashboard.html\" title=\"Dashboard\">CD</a>"
            ]
            for rail_item in updates:
                active = " active" if rail_item["repo"] == item["repo"] else ""
                repo_server_rail.append(
                    f"      <a class=\"server-dot{active}\" href=\"{_repo_page_filename(rail_item['repo'])}\" title=\"{rail_item['repo']}\">{badge_label(rail_item['repo'])}</a>"
                )

            repo_page = repo_template
            repo_page = repo_page.replace("{{SERVER_RAIL}}", "\n".join(repo_server_rail))
            repo_page = repo_page.replace("{{REPO_NAME}}", item["repo"])
            repo_page = repo_page.replace("{{AGENT_NAME}}", item["agent"])
            repo_page = repo_page.replace("{{LATEST_STATUS_CLASS}}", latest_status)
            repo_page = repo_page.replace("{{LATEST_STATUS_LABEL}}", latest_status_label)
            repo_page = repo_page.replace("{{LATEST_SUMMARY}}", latest_summary or "Update")
            repo_page = repo_page.replace("{{LATEST_STAGE}}", latest_stage or "update")
            repo_page = repo_page.replace("{{LATEST_TIME_DISPLAY}}", latest_time or "-")
            repo_page = repo_page.replace("{{RECENT_OUTCOME_TITLE}}", recent_outcome_title or "No incidents")
            repo_page = repo_page.replace("{{RECENT_OUTCOME_NOTE}}", recent_outcome_note or "")
            repo_page = repo_page.replace("{{ACTIVITY_ITEMS}}", "\n".join(activity_items))
            repo_page = repo_page.replace("{{INCIDENT_ITEMS}}", "\n".join(incident_items))
            repo_page = repo_page.replace("{{METRIC_CARDS}}", metric_cards)
            repo_page = repo_page.replace("{{EXPERIMENT_ITEMS}}", experiment_items)
            repo_page = repo_page.replace(
                "{{HISTORY_SECTION}}", _indent_block(item["section_html"], 8)
            )

            repo_output = ROOT / "private" / "dev" / _repo_page_filename(item["repo"])
            repo_output.write_text(repo_page, encoding="utf-8")

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = template.replace("{{STATUS_ROWS}}", "\n".join(rows))
    rendered = rendered.replace("{{HISTORY_BLOCKS}}", "\n".join(history_blocks))
    rendered = rendered.replace("{{SERVER_RAIL}}", "\n".join(server_rail))
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    build_dashboard()
