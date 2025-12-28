from __future__ import annotations

from datetime import datetime
from html import unescape
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
UPDATES_DIR = ROOT / "private" / "updates"
TEMPLATE_PATH = ROOT / "private" / "dev" / "dashboard.template.html"
OUTPUT_PATH = ROOT / "private" / "dev" / "dashboard.html"


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


def _parse_update_file(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    section_html = _extract_section(raw)

    section_match = re.search(
        r'<section[^>]*data-repo="([^"]+)"[^>]*data-agent="([^"]+)"',
        section_html,
    )
    repo = section_match.group(1) if section_match else path.stem.replace("updates-", "")
    agent = section_match.group(2) if section_match else "unknown"

    article_match = re.search(
        r'<article[^>]*data-status="([^"]+)"[^>]*data-time="([^"]+)"[^>]*>(.*?)</article>',
        section_html,
        re.S,
    )
    status = "unknown"
    time_raw = ""
    summary = ""
    if article_match:
        status = article_match.group(1).strip()
        time_raw = article_match.group(2).strip()
        article_body = article_match.group(3)
        h4_match = re.search(r"<h4>(.*?)</h4>", article_body, re.S)
        if h4_match:
            summary = _strip_tags(unescape(h4_match.group(1)))

    parsed_time = _parse_iso(time_raw)
    if parsed_time:
        time_display = parsed_time.strftime("%Y-%m-%d %H:%M %z").strip()
    else:
        time_display = time_raw

    return {
        "repo": repo,
        "agent": agent,
        "status": status or "unknown",
        "time_raw": time_raw,
        "time_display": time_display,
        "summary": summary,
        "section_html": section_html,
        "sort_key": parsed_time or datetime.min,
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
                f"      <a class=\"server-dot\" href=\"repo-{item['repo']}.html\" title=\"{item['repo']}\">{badge_label(item['repo'])}</a>"
            )
            status_label = item["status"].capitalize()
            repo_slug = item["repo"]
            rows.append(
                "            <tr>\n"
                f"              <td data-label=\"Repo\"><a class=\"repo-link\" href=\"repo-{repo_slug}.html\">{repo_slug}</a></td>\n"
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

    template = TEMPLATE_PATH.read_text(encoding="utf-8")
    rendered = template.replace("{{STATUS_ROWS}}", "\n".join(rows))
    rendered = rendered.replace("{{HISTORY_BLOCKS}}", "\n".join(history_blocks))
    rendered = rendered.replace("{{SERVER_RAIL}}", "\n".join(server_rail))
    OUTPUT_PATH.write_text(rendered, encoding="utf-8")


if __name__ == "__main__":
    build_dashboard()
