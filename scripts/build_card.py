"""Render the profile card: assets/card-dark.svg and assets/card-light.svg.

A terminal window that boots when the page loads: `neofetch` is typed, a 3D
"GF" monogram starts spinning beside the info, then `gh stats` draws the real
contribution graph and language mix, and the prompt comes back with a blinking
cursor. Everything is visible without the animation too (reduced motion, or a
viewer that ignores it).

The GitHub Action runs this every day so the numbers and the graph stay
current. It only needs the standard library and a token that can read public
data (the Action's GITHUB_TOKEN is enough):

    GITHUB_TOKEN=... python scripts/build_card.py

To preview without a token, pass the data yourself:

    python scripts/build_card.py --stats stats.json

where stats.json holds what fetch_stats() returns.

The text on the card lives in info_lines(). The monogram frames come from
assets/monogram.json (see monogram.py).
"""

import argparse
import base64
import datetime as dt
import json
import os
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
LOGIN = "gazafernanda"
USER, HOST = "gaza", "fernanda"
COMMAND = "gh stats --graph --langs"

# JetBrains Mono is embedded, so every character is exactly 0.6em wide everywhere.
FONT_STACK = "JBM, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
# Info column: 16px (9.6px per character), 20px per line, WIDTH characters wide.
INFO_FONT, INFO_LINE, INFO_CHAR, WIDTH = 16, 20, 9.6, 62
# Monogram: 12px (7.2px per character), 14.2px per line. Keep in step with monogram.py.
ART_FONT, ART_LINE, ART_CHAR, ART_COLS = 12, 14.2, 7.2, 52
# Labels around the graph and in the status line.
SMALL_FONT, SMALL_CHAR = 13, 7.8

MARGIN = 24  # transparent room around the window for the glow
BAR = 38  # title bar height
PAD = 24  # inner padding of the window
GAP = 28  # between the monogram and the info column
STATUS = 28  # status line height
CELL, PITCH = 11, 14  # contribution squares and their spacing

# Monogram playback: hold the face-on frame, then turn once.
HOLD, STEP = 2.6, 0.075

PALETTES = {
    "dark": {
        "bg": ("#151828", "#0a0c14"), "bar": "#0e1019", "rule": "#1f2335",
        "border": ("#7dcfff", "#272c45", "#bb9af7"), "halo": "#7aa2f7", "halo_opacity": 0.3, "halo_dy": 0,
        "title": "#565f89", "text": "#a9b1d6", "key": "#7dcfff", "value": "#c0caf5", "cc": "#353b57",
        "dim": "#6b7399", "user": "#bb9af7", "host": "#7dcfff", "prompt": "#9ece6a",
        "art": ("#a4e4ff", "#7aa2f7", "#bb9af7"),
        "heat": ("#1b1f31", "#1d3d5e", "#2b6ea6", "#4ea4e6", "#a4e4ff"),
        "langs": ("#7dcfff", "#bb9af7", "#9ece6a", "#e0af68", "#f7768e", "#414868"),
        "ansi": (
            ("#2a2f45", "#f7768e", "#9ece6a", "#e0af68", "#7aa2f7", "#bb9af7", "#7dcfff", "#a9b1d6"),
            ("#414868", "#ff899d", "#9fe044", "#faba4a", "#8db0ff", "#c7a9ff", "#a4daff", "#c0caf5"),
        ),
        "status_bg": "#13162a", "status_fg": "#6b7399", "accent": "#7aa2f7", "accent_fg": "#0e1019",
    },
    "light": {
        "bg": ("#ffffff", "#eef1f8"), "bar": "#e9ecf4", "rule": "#d5d9e7",
        "border": ("#2e7de9", "#cdd3e6", "#9854f1"), "halo": "#2f3654", "halo_opacity": 0.16, "halo_dy": 6,
        "title": "#7f86a8", "text": "#4c5374", "key": "#00668a", "value": "#252a40", "cc": "#c4c9db",
        "dim": "#6f7699", "user": "#7a3fd6", "host": "#1f66cc", "prompt": "#3f6b1f",
        "art": ("#0e8ab8", "#2e5fd9", "#7c3aed"),
        "heat": ("#e5e8f1", "#bcd5f2", "#7fb0ea", "#3f82db", "#1c51b0"),
        "langs": ("#2e7de9", "#9854f1", "#587539", "#b15c00", "#e8245a", "#a8aecb"),
        "ansi": (
            ("#343b58", "#f52a65", "#587539", "#8c6c3e", "#2e7de9", "#9854f1", "#007197", "#c4c8da"),
            ("#6c7394", "#ff4774", "#6a9a2b", "#b0812f", "#4f95f5", "#ad74ff", "#1a8fb5", "#e4e7f0"),
        ),
        "status_bg": "#e0e4ef", "status_fg": "#5f6788", "accent": "#2e7de9", "accent_fg": "#ffffff",
    },
}


def info_lines(s):
    return [
        title(USER, HOST),
        kv("OS", "macOS, Linux (Docker)"),
        kv("Uptime", uptime(s["created_at"])),
        kv("Host", "MacBook Air (M1)"),
        kv("Kernel", "Full-Stack Developer"),
        kv("Focus", "Frontend Architecture, Interface Design"),
        kv("Shell", "zsh"),
        kv("IDE", "VS Code, Claude Code"),
        [],
        kv("Languages.Programming", "TypeScript, JavaScript, PHP, Go, C#"),
        kv("Languages.Computer", "HTML, CSS, SQL, YAML"),
        kv("Languages.Real", "Indonesian, English"),
        [],
        kv("Stack.Frontend", "React, Next.js, Vue, Tailwind CSS"),
        kv("Stack.Backend", "Laravel, Go, ASP.NET Core"),
        kv("Stack.Data", "PostgreSQL, MySQL, SQL Server"),
        kv("Stack.Tools", "Docker, Git, Vite, Postman"),
        [],
        section("GitHub Stats"),
        pair(("Repos", s["repos"]), ("Followers", s["followers"])),
        kv("Contributions.PastYear", f"{s['contributions_year']:,}"),
        kv("Contributions.AllTime", f"{s['contributions_all']:,}"),
        pair(("Streak.Best", days(s["streak_best"])), ("Active.Days", s["active_days"])),
        [],
        [("ansi", 0)],
        [("ansi", 1)],
    ]


# A line is a list of (css class, text) segments; "" is the plain text colour.

def title(user, host):
    used = len(user) + 1 + len(host) + 1
    return [("user b", user), ("", "@"), ("host b", host), ("cc", " " + "─" * (WIDTH - used))]


def section(name):
    return [("cc", "─ "), ("value b", name), ("cc", " " + "─" * (WIDTH - len(name) - 3))]


def dotted(key, value, width):
    value = str(value)
    dots = max(1, width - len(key) - 1 - 2 - len(value))
    return [("key", key), ("", ":"), ("cc", " " + "." * dots + " "), ("value", value)]


def kv(key, value):
    return [("cc", ". ")] + dotted(key, value, WIDTH - 2)


def pair(left, right, left_width=29):
    return ([("cc", ". ")] + dotted(*left, left_width) + [("cc", " | ")]
            + dotted(*right, WIDTH - 2 - left_width - 3))


def prompt():
    return [("user b", USER), ("", "@"), ("host b", HOST), ("", ":"), ("key", "~"), ("prompt", "$ ")]


def days(n):
    return f"{n} day" + ("" if n == 1 else "s")


def uptime(created_at):
    since = dt.date.fromisoformat(created_at[:10])
    today = dt.datetime.now(dt.timezone.utc).date()
    years, months, d = today.year - since.year, today.month - since.month, today.day - since.day
    if d < 0:
        months -= 1
        d += (today.replace(day=1) - dt.timedelta(days=1)).day
    if months < 0:
        years -= 1
        months += 12
    plural = lambda n, word: f"{n} {word}" + ("" if n == 1 else "s")
    return ", ".join([plural(years, "year"), plural(months, "month"), plural(d, "day")])


USER_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    followers { totalCount }
    following { totalCount }
    public: repositories(ownerAffiliations: OWNER, privacy: PUBLIC) { totalCount }
    sources: repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false) {
      nodes {
        stargazerCount
        languages(first: 20) { edges { size node { name } } }
      }
    }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount contributionLevel } }
      }
    }
  }
}
"""


def graphql(token, query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": f"{LOGIN}-profile-card"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]


def fetch_stats(token):
    user = graphql(token, USER_QUERY, {"login": LOGIN})["user"]
    calendar = user["contributionsCollection"]["contributionCalendar"]
    languages = {}
    for repo in user["sources"]["nodes"]:
        for edge in repo["languages"]["edges"]:
            languages[edge["node"]["name"]] = languages.get(edge["node"]["name"], 0) + edge["size"]
    # A contributionsCollection spans at most a year, so ask for each year since joining.
    years = range(int(user["createdAt"][:4]), dt.datetime.now(dt.timezone.utc).year + 1)
    fields = "\n".join(
        f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z")'
        " { contributionCalendar { totalContributions } }"
        for y in years
    )
    per_year = graphql(token, f"query($login: String!) {{ user(login: $login) {{ {fields} }} }}", {"login": LOGIN})["user"]
    return {
        "created_at": user["createdAt"],
        "repos": user["public"]["totalCount"],
        "stars": sum(r["stargazerCount"] for r in user["sources"]["nodes"]),
        "followers": user["followers"]["totalCount"],
        "following": user["following"]["totalCount"],
        "contributions_year": calendar["totalContributions"],
        "contributions_all": sum(c["contributionCalendar"]["totalContributions"] for c in per_year.values()),
        "weeks": [
            [{"date": d["date"], "count": d["contributionCount"], "level": d["contributionLevel"]}
             for d in week["contributionDays"]]
            for week in calendar["weeks"]
        ],
        "languages": languages,
    }


def derive(stats):
    """Streaks and active days from the calendar."""
    days_ = [d for week in stats["weeks"] for d in week]
    best = run = 0
    for d in days_:
        run = run + 1 if d["count"] else 0
        best = max(best, run)
    return {**stats, "streak_best": best, "active_days": sum(1 for d in days_ if d["count"])}


def top_languages(languages, n=5):
    total = sum(languages.values()) or 1
    ranked = sorted(languages.items(), key=lambda kv: -kv[1])
    top = [(name, size / total) for name, size in ranked[:n]]
    rest = sum(size for _, size in ranked[n:]) / total
    return top + ([("Other", rest)] if rest > 0.0005 else [])


def font_face(weight, name):
    data = base64.b64encode((ASSETS / "fonts" / name).read_bytes()).decode()
    return (f"@font-face {{ font-family: JBM; font-weight: {weight};"
            f" src: url(data:font/woff2;base64,{data}) format('woff2'); }}")


def tspans(segments):
    """Coloured tspans for one line. No whitespace between them: white-space: pre would draw it."""
    return "".join(
        f'<tspan class="{cls}">{escape(text)}</tspan>' if cls else f"<tspan>{escape(text)}</tspan>"
        for cls, text in segments
    )


def render(theme, frames, lines, stats, today):
    p = PALETTES[theme]
    left = MARGIN + PAD
    art_w = ART_COLS * ART_CHAR
    info_x = left + art_w + GAP
    right = info_x + WIDTH * INFO_CHAR

    prompt_y = MARGIN + BAR + 34
    info_top = prompt_y + 36
    last_info = info_top + (len(lines) - 1) * INFO_LINE

    # Second command: the graph on the left, the language mix on the right.
    prompt2_y = last_info + 46
    grid_top = prompt2_y + 40
    weeks = stats["weeks"]
    grid_w = len(weeks) * PITCH - (PITCH - CELL)
    grid_bottom = grid_top + 7 * PITCH - (PITCH - CELL)
    summary_y = grid_bottom + 26
    lang_x = left + grid_w + 36
    lang_w = right - lang_x

    final_y = summary_y + 42
    status_top = final_y + 22
    win_w = round(right + PAD - MARGIN)
    win_h = round(status_top + STATUS - MARGIN)
    width, height = win_w + 2 * MARGIN, win_h + 2 * MARGIN

    # Centre the monogram on the info column.
    art_h = len(frames[0]) * ART_LINE
    art_top = (info_top - INFO_FONT + last_info) / 2 - art_h / 2
    art_base = art_top + ART_FONT * 0.8
    art_cols = max(len(row) for frame in frames for row in frame)
    if art_cols > ART_COLS:
        print(f"warning: the monogram is {art_cols} columns, wider than {ART_COLS}")

    # Boot timeline, in seconds.
    type_at, type_step = 0.35, 0.06
    boot = type_at + len("neofetch") * type_step + 0.25
    line_step = 0.045
    done1 = boot + len(lines) * line_step + 0.3
    type2_at, type2_step = done1 + 0.25, 0.035
    graph_at = type2_at + len(COMMAND) * type2_step + 0.25
    col_step = 0.016
    done2 = graph_at + len(weeks) * col_step + 0.45
    cycle = HOLD + (len(frames) - 1) * STEP

    stop = lambda off, color, op=1: f'<stop offset="{off}" stop-color="{color}" stop-opacity="{op}"/>'
    pct = lambda seconds: f"{seconds / cycle * 100:.3f}%"
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}"'
        f' font-family="{FONT_STACK}" font-size="{INFO_FONT}px">',
        "<title>Gaza Fernanda - profile card</title>",
        "<desc>A terminal running neofetch beside a spinning 3D GF monogram, then a contribution graph"
        " and top languages, refreshed daily.</desc>",
        "<defs>",
        f'<radialGradient id="bg" cx="0.1" cy="0" r="1.25">{stop(0, p["bg"][0])}{stop(1, p["bg"][1])}</radialGradient>',
        f'<linearGradient id="border" x1="0" y1="0" x2="1" y2="1">'
        f'{stop(0, p["border"][0])}{stop(0.5, p["border"][1])}{stop(1, p["border"][2])}</linearGradient>',
        f'<linearGradient id="art" gradientUnits="userSpaceOnUse" x1="{left}" y1="{art_top:.0f}"'
        f' x2="{left + art_w:.0f}" y2="{art_top + art_h:.0f}">'
        f'{stop(0, p["art"][0])}{stop(0.5, p["art"][1])}{stop(1, p["art"][2])}</linearGradient>',
        f'<clipPath id="win"><rect x="{MARGIN}" y="{MARGIN}" width="{win_w}" height="{win_h}" rx="14"/></clipPath>',
        f'<clipPath id="langbar"><rect x="{lang_x:.1f}" y="{grid_top}" width="{lang_w:.1f}" height="10" rx="5"/></clipPath>',
        '<filter id="blur" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="10"/></filter>',
        "</defs>",
        "<style>",
        font_face(400, "JetBrainsMono-Regular.subset.woff2"),
        font_face(700, "JetBrainsMono-Bold.subset.woff2"),
        "text { white-space: pre; }",
        ".b { font-weight: 700; }",
        f".art {{ font-size: {ART_FONT}px; }}",
        f".sm {{ font-size: {SMALL_FONT}px; }}",
        f".t {{ fill: {p['text']}; }}",
        *(f".{c} {{ fill: {p[c]}; }}" for c in ("key", "value", "cc", "dim", "user", "host", "prompt", "title")),
        "@keyframes show { from { opacity: 0; } to { opacity: 1; } }",
        "@keyframes slide { from { opacity: 0; transform: translateX(-10px); } to { opacity: 1; transform: none; } }",
        "@keyframes rise { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }",
        "@keyframes type { from { fill-opacity: 0; } to { fill-opacity: 1; } }",
        "@keyframes grow { from { transform: scaleX(0); } to { transform: none; } }",
        "@keyframes blink { 50% { opacity: 0; } }",
        "@keyframes pulse { 50% { stroke-opacity: 0.1; } }",
        # One frame of the turn: on for its slot, off for the rest of the cycle.
        f"@keyframes face {{ 0% {{ opacity: 1; }} {pct(HOLD)} {{ opacity: 0; }} 100% {{ opacity: 0; }} }}",
        f"@keyframes turn {{ 0% {{ opacity: 1; }} {pct(STEP)} {{ opacity: 0; }} 100% {{ opacity: 0; }} }}",
        f".f {{ opacity: 0; animation: turn {cycle:.3f}s step-end infinite; }}",
        f".f0 {{ animation: face {cycle:.3f}s step-end infinite; }}",
        ".show { animation: show .5s ease-out both; }",
        ".ln { animation: slide .45s cubic-bezier(.2,.7,.2,1) both; }",
        ".wk { animation: rise .4s cubic-bezier(.2,.7,.2,1) both; }",
        ".ch { animation: type .01s linear both; }",
        ".grow { transform-box: fill-box; transform-origin: left center;"
        " animation: grow 1s cubic-bezier(.2,.7,.2,1) both; }",
        ".cursor { animation: blink 1.1s step-end infinite; }",
        ".today { animation: pulse 1.6s ease-in-out infinite; }",
        "@media (prefers-reduced-motion: reduce) { * { animation: none !important; } }",
        "</style>",
        # Glow (dark) or soft shadow (light) behind the window.
        f'<rect x="{MARGIN + 8}" y="{MARGIN + 8 + p["halo_dy"]}" width="{win_w - 16}" height="{win_h - 16}" rx="16"'
        f' fill="{p["halo"]}" opacity="{p["halo_opacity"]}" filter="url(#blur)"/>',
        f'<g clip-path="url(#win)">',
        f'<rect x="{MARGIN}" y="{MARGIN}" width="{win_w}" height="{win_h}" fill="url(#bg)"/>',
        f'<rect x="{MARGIN}" y="{MARGIN}" width="{win_w}" height="{BAR}" fill="{p["bar"]}"/>',
        f'<line x1="{MARGIN}" y1="{MARGIN + BAR - 0.5}" x2="{MARGIN + win_w}" y2="{MARGIN + BAR - 0.5}" stroke="{p["rule"]}"/>',
        *(f'<circle cx="{MARGIN + 22 + i * 20}" cy="{MARGIN + BAR / 2}" r="6" fill="{c}"/>'
          for i, c in enumerate(("#ff5f57", "#febc2e", "#28c840"))),
        f'<text class="title" font-size="13" x="{MARGIN + win_w / 2}" y="{MARGIN + BAR / 2 + 4.5}"'
        f' text-anchor="middle">{USER}@{HOST}: ~ — zsh — {win_w // 9}×{win_h // 18}</text>',
    ]

    # $ neofetch, typed a character at a time.
    out.append(f'<text class="t" x="{left}" y="{prompt_y}">{tspans(prompt())}{typed("neofetch", type_at, type_step)}</text>')

    # The monogram: one <text> per frame, each shown for its slot of the cycle.
    out.append(f'<g class="art show" fill="url(#art)" style="animation-delay:{boot:.2f}s">')
    for i, frame in enumerate(frames):
        cls = "f0" if i == 0 else "f"
        delay = boot if i == 0 else boot + HOLD + (i - 1) * STEP
        rows = []
        for r, row in enumerate(frame):
            lead = len(row) - len(row.lstrip())
            if row.strip():
                rows.append(f'<tspan x="{left + lead * ART_CHAR:.1f}" y="{art_base + r * ART_LINE:.1f}">{escape(row.strip())}</tspan>')
        out.append(f'<text class="{cls}" style="animation-delay:{delay:.3f}s">{"".join(rows)}</text>')
    out.append("</g>")

    for i, segments in enumerate(lines):
        y = info_top + i * INFO_LINE
        delay = f'style="animation-delay:{boot + i * line_step:.2f}s"'
        if segments and segments[0][0] == "ansi":
            colors = p["ansi"][segments[0][1]]
            out.append(f'<g class="ln" {delay}>' + "".join(
                f'<rect x="{info_x + j * 3 * INFO_CHAR:.1f}" y="{y - 14}" width="{3 * INFO_CHAR - 3:.1f}" height="17" rx="3" fill="{c}"/>'
                for j, c in enumerate(colors)
            ) + "</g>")
            continue
        if not segments:
            continue
        cols = sum(len(text) for _, text in segments)
        if cols > WIDTH:
            print(f"warning: line {i + 1} is {cols} characters, wider than {WIDTH}")
        out.append(f'<text class="t ln" {delay} x="{info_x}" y="{y}">{tspans(segments)}</text>')

    # $ gh stats: the prompt comes back and the second command is typed.
    out.append(f'<g class="show" style="animation-delay:{done1:.2f}s"><text class="t" x="{left}" y="{prompt2_y}">'
               f'{tspans(prompt())}{typed(COMMAND, type2_at, type2_step)}</text></g>')
    out += graph(p, stats, weeks, left, grid_top, grid_w, summary_y, graph_at, col_step, today)
    out += language_panel(p, stats, lang_x, lang_w, grid_top, graph_at)

    # Back at the prompt, with a blinking cursor.
    cursor_x = left + sum(len(text) for _, text in prompt()) * INFO_CHAR
    out.append(
        f'<g class="show" style="animation-delay:{done2:.2f}s"><text class="t" x="{left}" y="{final_y}">{tspans(prompt())}</text>'
        f'<rect class="cursor" x="{cursor_x:.1f}" y="{final_y - INFO_FONT + 2}" width="{INFO_CHAR}" height="{INFO_FONT + 2}"'
        f' rx="1" fill="{p["user"]}"/></g>'
    )

    out += status_line(p, MARGIN, status_top, win_w, today)
    out.append("</g>")
    out.append(f'<rect x="{MARGIN + 0.6}" y="{MARGIN + 0.6}" width="{win_w - 1.2}" height="{win_h - 1.2}" rx="13.5"'
               f' fill="none" stroke="url(#border)" stroke-width="1.2"/>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def typed(text, start, step):
    return "".join(
        f'<tspan class="value ch" style="animation-delay:{start + i * step:.2f}s">{escape(c)}</tspan>'
        for i, c in enumerate(text)
    )


LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def graph(p, stats, weeks, left, top, grid_w, summary_y, start, col_step, today):
    """The contribution calendar: a column per week, Sunday at the top, rising in left to right."""
    out, last_label, prev_month = [], -9, None
    for w, week in enumerate(weeks):
        x = left + w * PITCH
        month = week[0]["date"][:7]
        cells = []
        if month != prev_month and w - last_label >= 3 and x + 3 * SMALL_CHAR < left + grid_w:
            label = dt.date.fromisoformat(week[0]["date"]).strftime("%b")
            cells.append(f'<text class="sm dim" x="{x}" y="{top - 9}">{label}</text>')
            last_label = w
        prev_month = month
        for d in week:
            weekday = (dt.date.fromisoformat(d["date"]).weekday() + 1) % 7
            y = top + weekday * PITCH
            fill = p["heat"][LEVELS.get(d["level"], 0)]
            cells.append(f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" fill="{fill}"/>')
            if d["date"] == today:
                cells.append(f'<rect class="today" x="{x - 2}" y="{y - 2}" width="{CELL + 4}" height="{CELL + 4}" rx="4"'
                             f' fill="none" stroke="{p["user"]}" stroke-width="1.5"/>')
        out.append(f'<g class="wk" style="animation-delay:{start + w * col_step:.3f}s">{"".join(cells)}</g>')

    # The numbers under the graph, and the legend at its right edge.
    year = stats["contributions_year"]
    summary = [("value b", f"{year:,}"), ("dim", f" contribution{'' if year == 1 else 's'} in the last year")]
    legend_x = left + grid_w - 4 * PITCH - CELL - (len("Less") + 1 + len("More") + 1) * SMALL_CHAR
    done = start + len(weeks) * col_step
    out.append(f'<g class="show" style="animation-delay:{done:.2f}s">'
               f'<text class="sm t" x="{left}" y="{summary_y}">{tspans(summary)}</text>'
               f'<text class="sm dim" x="{legend_x:.1f}" y="{summary_y}">Less</text>'
               + "".join(f'<rect x="{legend_x + 5 * SMALL_CHAR + i * PITCH:.1f}" y="{summary_y - CELL + 1}" width="{CELL}"'
                         f' height="{CELL}" rx="2.5" fill="{c}"/>' for i, c in enumerate(p["heat"]))
               + f'<text class="sm dim" x="{legend_x + 5 * SMALL_CHAR + 5 * PITCH + 2:.1f}" y="{summary_y}">More</text></g>')
    return out


def language_panel(p, stats, x, w, top, start):
    langs = top_languages(stats["languages"])
    out = [f'<text class="sm show" x="{x:.1f}" y="{top - 9}" style="animation-delay:{start:.2f}s">'
           f'{tspans([("key", "languages"), ("dim", " · public repos")])}</text>']
    # A stacked bar that sweeps open, then one legend line per language.
    seg_x, bar = x, []
    for i, (name, share) in enumerate(langs):
        seg_w = share * w
        bar.append(f'<rect x="{seg_x:.1f}" y="{top}" width="{seg_w + 0.5:.1f}" height="10" fill="{p["langs"][i % len(p["langs"])]}"/>')
        seg_x += seg_w
    out.append(f'<g clip-path="url(#langbar)"><g class="grow" style="animation-delay:{start + 0.1:.2f}s">{"".join(bar)}</g></g>')
    name_cols = int(w / SMALL_CHAR) - 2 - 6
    for i, (name, share) in enumerate(langs):
        y = top + 32 + i * 16
        color = p["langs"][i % len(p["langs"])]
        text = [("value", name[:name_cols].ljust(name_cols)), ("dim", f"{share * 100:5.1f}%")]
        out.append(f'<g class="ln" style="animation-delay:{start + 0.3 + i * 0.08:.2f}s">'
                   f'<circle cx="{x + 4:.1f}" cy="{y - 4.5}" r="4" fill="{color}"/>'
                   f'<text class="sm t" x="{x + 2 * SMALL_CHAR:.1f}" y="{y}">{tspans(text)}</text></g>')
    return out


def status_line(p, x, top, w, today):
    """A tmux-style status line across the bottom of the window."""
    base = top + STATUS / 2 + 4.5
    stamp = dt.date.fromisoformat(today).strftime("%d %b %Y")
    tag, chip = f" {USER} ", f" {stamp} "
    chip_w = len(chip) * SMALL_CHAR + 6
    windows = [("dim", "  0:"), ("dim", "neofetch  "), ("dim", "1:"), ("value", "gh-stats*")]
    return [
        f'<rect x="{x}" y="{top}" width="{w}" height="{STATUS}" fill="{p["status_bg"]}"/>',
        f'<line x1="{x}" y1="{top + 0.5}" x2="{x + w}" y2="{top + 0.5}" stroke="{p["rule"]}"/>',
        f'<rect x="{x}" y="{top}" width="{len(tag) * SMALL_CHAR + 22:.1f}" height="{STATUS}" fill="{p["accent"]}"/>',
        f'<text class="sm b" x="{x + 14}" y="{base}" fill="{p["accent_fg"]}">{tag}</text>',
        f'<text class="sm" x="{x + len(tag) * SMALL_CHAR + 22:.1f}" y="{base}">{tspans(windows)}</text>',
        f'<rect x="{x + w - chip_w - 8:.1f}" y="{top}" width="{chip_w + 8:.1f}" height="{STATUS}" fill="{p["accent"]}"/>',
        f'<text class="sm b" x="{x + w - chip_w - 2:.1f}" y="{base}" fill="{p["accent_fg"]}">{chip}</text>',
        f'<text class="sm dim" x="{x + w - chip_w - 18:.1f}" y="{base}" text-anchor="end">synced daily</text>',
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--stats", type=Path, help="JSON file with the data, instead of asking GitHub")
    args = parser.parse_args()

    if args.stats:
        stats = json.loads(args.stats.read_text(encoding="utf-8"))
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise SystemExit("set GITHUB_TOKEN, or pass --stats FILE")
        stats = fetch_stats(token)
    stats = derive(stats)
    print(json.dumps({k: v for k, v in stats.items() if k != "weeks"}))

    frames = json.loads((ASSETS / "monogram.json").read_text(encoding="utf-8"))["frames"]
    today = stats["weeks"][-1][-1]["date"]
    lines = info_lines(stats)
    for theme in ("dark", "light"):
        (ASSETS / f"card-{theme}.svg").write_text(render(theme, frames, lines, stats, today), encoding="utf-8")
    print(f"wrote {ASSETS / 'card-dark.svg'} and {ASSETS / 'card-light.svg'}")


if __name__ == "__main__":
    main()
