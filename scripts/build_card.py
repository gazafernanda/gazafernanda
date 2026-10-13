"""Render the profile card: assets/card-dark.svg and assets/card-light.svg.

An editorial one-pager in the style of the portfolio (gazafernanda.github.io/Portfolio):
black and white, Outfit display type, Inter text, one orange accent. On load the
headline slides up out of its baseline, the rules draw across, the year of
contributions fills in as a dot matrix and the numbers roll into place like an
odometer. After that a slow ripple runs through the matrix now and then.
Everything is in its final place without the animation too (reduced motion, or
a viewer that ignores it).

The GitHub Action runs this every day so the numbers, the matrix, the language
mix and the recent repos stay current. It only needs the standard library and
a token that can read public data (the Action's GITHUB_TOKEN is enough):

    GITHUB_TOKEN=... python scripts/build_card.py

To preview without a token, pass the data yourself:

    python scripts/build_card.py --stats stats.json

where stats.json holds what fetch_stats() returns.

The words on the card are the constants just below. The fonts and their
metrics come from assets/fonts (see subset_fonts.py).
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
FONTS = ASSETS / "fonts"
LOGIN = "gazafernanda"

NAME = "Gaza Fernanda"
HEADLINE = ("Front End", "Developer.")
NOTE = "Full-stack in practice: Laravel, Go and ASP.NET Core behind the interfaces."
PHILOSOPHY = ("Great design is not when there is nothing left to add, "
              "but when there is nothing left to take away.")
EXPERTISE = ["Interface Design", "Frontend Architecture", "Technical Strategy"]
STACK = ["React · Next.js · Vue", "Tailwind CSS · Vite", "Laravel · Go · ASP.NET Core", "PostgreSQL · Docker"]

ACCENT = "#ff4f00"
PALETTES = {
    "dark": {
        "bg": "#000000", "frame": "#27272a", "rule": "#27272a", "ink": "#fafafa", "muted": "#a1a1aa",
        "faint": "#71717a", "track": "#27272a",
        "dots": ("#1f1f23", "#52525b", "#a1a1aa", "#f4f4f5", ACCENT),
    },
    "light": {
        "bg": "#ffffff", "frame": "#e4e4e7", "rule": "#e4e4e7", "ink": "#09090b", "muted": "#71717a",
        "faint": "#a1a1aa", "track": "#e4e4e7",
        "dots": ("#ececef", "#c4c4cc", "#71717a", "#09090b", ACCENT),
    },
}

W = 1080  # card width
M = 56  # side margin
GUTTER = 32  # between the four columns
COLUMN = (W - 2 * M - 3 * GUTTER) / 4

# Type: (font in metrics.json, css family, weight, style, size, letter-spacing in em).
TYPE = {
    "display": ("outfit-700", "CardDisplay", 700, "normal", 104, -0.045),
    "number": ("outfit-700", "CardDisplay", 700, "normal", 56, -0.02),
    "label": ("inter-600", "CardSans", 600, "normal", 11, 0.3),
    "body": ("inter-400", "CardSans", 400, "normal", 15, 0),
    "note": ("inter-400", "CardSans", 400, "normal", 13, 0),
    "quote": ("inter-300i", "CardSans", 300, "italic", 20, -0.01),
    "mono": ("mono-400", "CardMono", 400, "normal", 11, 0.04),
}
FALLBACKS = {"CardDisplay": "Outfit, Inter, Helvetica, Arial, sans-serif",
             "CardSans": "Inter, Helvetica, Arial, sans-serif", "CardMono": "ui-monospace, Menlo, monospace"}

METRICS = json.loads((FONTS / "metrics.json").read_text(encoding="utf-8"))

# Contribution matrix: a column per week, Sunday at the top.
PITCH = (W - 2 * M) / 53
RADII = (1.6, 2.6, 3.4, 4.2, 5.0)
# Odometer: distance between the digits on each strip.
ROLL_STEP = 72
LEVELS = {"NONE": 0, "FIRST_QUARTILE": 1, "SECOND_QUARTILE": 2, "THIRD_QUARTILE": 3, "FOURTH_QUARTILE": 4}


def measure(content, style):
    font, _, _, _, size, tracking = TYPE[style]
    m = METRICS[font]
    fallback = m["adv"].get("n", m["upm"] // 2)
    return sum(m["adv"].get(c, fallback) for c in content) * size / m["upm"] + tracking * size * len(content)


def wrap(content, style, width):
    lines, line = [], ""
    for word in content.split():
        trial = f"{line} {word}".strip()
        if line and measure(trial, style) > width:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + [line]


def fit(content, style, width):
    """Trim with an ellipsis until it fits."""
    if measure(content, style) <= width:
        return content
    while content and measure(content + "…", style) > width:
        content = content[:-1]
    return content.rstrip() + "…"


def text(x, y, content, style, cls="", anchor=None, delay=None):
    attrs = f'class="{(style + " " + cls).strip()}"'
    if anchor:
        attrs += f' text-anchor="{anchor}"'
    if delay is not None:
        attrs += f' style="animation-delay:{delay:.2f}s"'
    return f'<text {attrs} x="{x:.1f}" y="{y:.1f}">{escape(content)}</text>'


def label(x, y, content, **kw):
    return text(x, y, content.upper(), "label", "muted", **kw)


USER_QUERY = """
query($login: String!) {
  user(login: $login) {
    createdAt
    public: repositories(ownerAffiliations: OWNER, privacy: PUBLIC) { totalCount }
    sources: repositories(first: 100, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false,
                          orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        pushedAt
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
        "contributions_year": calendar["totalContributions"],
        "contributions_all": sum(c["contributionCalendar"]["totalContributions"] for c in per_year.values()),
        "weeks": [
            [{"date": d["date"], "count": d["contributionCount"], "level": d["contributionLevel"]}
             for d in week["contributionDays"]]
            for week in calendar["weeks"]
        ],
        "languages": languages,
        # The profile repo is pushed every day by the Action, so it would always top the list.
        "recent": [{"name": r["name"], "pushed_at": r["pushedAt"]}
                   for r in user["sources"]["nodes"] if r["name"] != LOGIN][:6],
    }


def ago(stamp, today):
    days = (today - dt.date.fromisoformat(stamp[:10])).days
    if days < 1:
        return "today"
    if days < 14:
        return f"{days}d"
    if days < 60:
        return f"{days // 7}w"
    if days < 365:
        return f"{days // 30}mo"
    return f"{days // 365}y"


def years_since(stamp, today):
    since = dt.date.fromisoformat(stamp[:10])
    return today.year - since.year - ((today.month, today.day) < (since.month, since.day))


def font_faces():
    rules, seen = [], set()
    for font, family, weight, style, _, _ in TYPE.values():
        if font in seen:
            continue
        seen.add(font)
        data = base64.b64encode((FONTS / f"{font}.woff2").read_bytes()).decode()
        rules.append(f"@font-face {{ font-family: {family}; font-weight: {weight}; font-style: {style};"
                     f" src: url(data:font/woff2;base64,{data}) format('woff2'); }}")
    return rules


def type_rules():
    return [
        f".{name} {{ font-family: {family}, {FALLBACKS[family]}; font-weight: {weight}; font-style: {style};"
        f" font-size: {size}px; letter-spacing: {tracking}em; }}"
        for name, (_, family, weight, style, size, tracking) in TYPE.items()
    ]


def render(theme, stats, today):
    p = PALETTES[theme]
    out = []

    # Vertical rhythm.
    mast_y = 52
    rule1 = 78
    line1 = 196
    line2 = 286
    rule2 = 330
    cols_label = 366
    cols_top = 400
    rule3 = 520
    act_label = 556
    dots_top = 584
    months_y = dots_top + 6 * PITCH + 30
    rule4 = months_y + 24
    num_y = rule4 + 86
    num_label = num_y + 30
    height = round(num_label + 44)

    # Masthead.
    stamp = f"Updated {today.strftime('%d.%m.%Y')}"
    live_x = W - M - measure(stamp.upper(), "label") - 12
    out += [
        '<g class="fade">',
        label(M, mast_y, NAME),
        label(W / 2, mast_y, f"Est. {stats['created_at'][:4]}", anchor="middle"),
        label(W - M, mast_y, stamp, anchor="end"),
        f'<circle cx="{live_x:.1f}" cy="{mast_y - 4}" r="3.5" fill="{ACCENT}"/>',
        f'<circle class="ring" cx="{live_x:.1f}" cy="{mast_y - 4}" r="3.5" fill="none" stroke="{ACCENT}"/>',
        "</g>",
        rule(rule1, p, 0.1),
    ]

    # Headline: each line rises out of its own baseline.
    cap = 0.72 * TYPE["display"][4]
    for i, (words, y) in enumerate(zip(HEADLINE, (line1, line2))):
        out.append(f'<clipPath id="h{i}"><rect x="{M - 10}" y="{y - cap - 14:.0f}" width="{W / 2 + 120:.0f}"'
                   f' height="{cap + 34:.0f}"/></clipPath>')
        out.append(f'<g clip-path="url(#h{i})"><g class="rise" style="animation-delay:{0.25 + i * 0.13:.2f}s">'
                   + text(M - 4, y, words.upper(), "display", "ink") + "</g></g>")

    # The philosophy and the full-stack note, in the right-hand column.
    col_x, col_w = W - M - 300, 300
    quote = wrap(f"“{PHILOSOPHY}”", "quote", col_w)
    note_y = line1 - 36 + len(quote) * 28 + 14
    out.append('<g class="fade" style="animation-delay:0.7s">')
    out.append(label(col_x, line1 - 72, "The Philosophy"))
    out += [text(col_x, line1 - 36 + i * 28, row, "quote", "ink") for i, row in enumerate(quote)]
    out += [text(col_x, note_y + i * 20, row, "note", "muted") for i, row in enumerate(wrap(NOTE, "note", col_w))]
    out.append("</g>")
    out.append(rule(rule2, p, 0.85))

    # Four columns.
    xs = [M + i * (COLUMN + GUTTER) for i in range(4)]
    titles = ("01 — Expertise", "02 — Stack", "03 — Languages", "04 — Recently pushed")
    for i, (x, title) in enumerate(zip(xs, titles)):
        out.append(f'<g class="fade" style="animation-delay:{1.0 + i * 0.1:.2f}s">{label(x, cols_label, title)}')
        if i == 0:
            out += [text(x, cols_top + j * 26, item, "body", "ink") for j, item in enumerate(EXPERTISE)]
        elif i == 1:
            out += [text(x, cols_top + j * 26, item, "body", "ink") for j, item in enumerate(STACK)]
        elif i == 2:
            out += languages(stats, x, cols_top, p, 1.3)
        else:
            for j, repo in enumerate(stats["recent"][:4]):
                when = ago(repo["pushed_at"], today)
                name = fit(repo["name"], "body", COLUMN - measure(when, "mono") - 16)
                out.append(text(x, cols_top + j * 26, name, "body", "ink"))
                out.append(text(x + COLUMN, cols_top + j * 26, when, "mono", "muted", anchor="end"))
        out.append("</g>")
    out.append(rule(rule3, p, 1.25))

    # The year as a dot matrix, with a legend.
    out.append('<g class="fade" style="animation-delay:1.35s">')
    out.append(label(M, act_label, "Activity — the last twelve months"))
    legend_x = W - M - measure("LESS", "mono") - measure("MORE", "mono") - 5 * 14 - 20
    swatch_x = legend_x + measure("LESS", "mono") + 12
    out.append(text(legend_x, act_label, "LESS", "mono", "muted"))
    out += [f'<circle cx="{swatch_x + i * 14:.1f}" cy="{act_label - 4}" r="{r:.1f}" fill="{c}"/>'
            for i, (r, c) in enumerate(zip(RADII, p["dots"]))]
    out.append(text(swatch_x + 5 * 14 - 2, act_label, "MORE", "mono", "muted"))
    out.append("</g>")
    out += matrix(stats["weeks"], dots_top, months_y, p, today, start=1.5)
    out.append(rule(rule4, p, 1.9))

    # The numbers, rolling into place.
    numbers = [
        (stats["contributions_year"], "Contributions, 12 mo"),
        (stats["contributions_all"], "Contributions, total"),
        (stats["active_days"], "Active days, 12 mo"),
        (years_since(stats["created_at"], today), "Years on GitHub"),
    ]
    for i, ((value, caption), x) in enumerate(zip(numbers, xs)):
        if measure(caption.upper(), "label") > COLUMN:
            print(f"warning: caption {caption!r} is wider than its column")
        out += odometer(x, num_y, f"{value:,}", f"n{i}", 2.0 + i * 0.12)
        out.append(text(x, num_label, caption.upper(), "label", "muted fade", delay=2.2 + i * 0.12))

    return document(p, height, out)


def rule(y, p, delay):
    return (f'<line class="draw" style="animation-delay:{delay:.2f}s" x1="{M}" y1="{y + 0.5}" x2="{W - M}"'
            f' y2="{y + 0.5}" stroke="{p["rule"]}"/>')


def languages(stats, x, top, p, start):
    """Top five languages by bytes: name, a hairline bar against the biggest, and its share."""
    total = sum(stats["languages"].values()) or 1
    ranked = sorted(stats["languages"].items(), key=lambda kv: -kv[1])[:5]
    name_w = 92
    bar_x, bar_w = x + name_w, COLUMN - name_w - 44
    out = []
    for j, (name, size) in enumerate(ranked):
        y = top + j * 21
        length = bar_w * size / ranked[0][1]
        out.append(text(x, y, fit(name, "note", name_w - 8), "note", "ink"))
        out.append(f'<line x1="{bar_x:.1f}" y1="{y - 4}" x2="{bar_x + bar_w:.1f}" y2="{y - 4}" stroke="{p["track"]}" stroke-width="2"/>')
        out.append(f'<line class="draw" style="animation-delay:{start + j * 0.08:.2f}s" x1="{bar_x:.1f}" y1="{y - 4}"'
                   f' x2="{bar_x + length:.1f}" y2="{y - 4}" stroke="{ACCENT if j == 0 else p["ink"]}" stroke-width="2"/>')
        out.append(text(x + COLUMN, y, f"{size / total * 100:.1f}%", "mono", "muted", anchor="end"))
    return out


def matrix(weeks, top, months_y, p, today, start):
    out, last_label = [], -9
    for w, week in enumerate(weeks):
        cx = M + PITCH / 2 + w * PITCH
        dots = []
        for d in week:
            row = (dt.date.fromisoformat(d["date"]).weekday() + 1) % 7
            level = LEVELS.get(d["level"], 0)
            cy = top + row * PITCH
            dots.append(f'<circle class="pop" style="animation-delay:{start + w * 0.012 + row * 0.035:.3f}s"'
                        f' cx="{cx:.1f}" cy="{cy:.1f}" r="{RADII[level]}" fill="{p["dots"][level]}"/>')
            if d["date"] == today.isoformat():
                dots.append(f'<g class="fade" style="animation-delay:{start + 1.2:.2f}s"><circle class="ring" cx="{cx:.1f}"'
                            f' cy="{cy:.1f}" r="5.5" fill="none" stroke="{ACCENT}"/></g>')
        # Once everything has landed, a ripple runs through the weeks every so often.
        out.append(f'<g class="ripple" style="animation-delay:{start + 2.5 + w * 0.03:.2f}s">{"".join(dots)}</g>')
        first = dt.date.fromisoformat(week[0]["date"])
        if (w == 0 or first.day <= 7) and w - last_label >= 3 and w < len(weeks) - 2:
            out.append(text(cx - 3, months_y, first.strftime("%b").upper(), "mono", "faint fade", delay=start + 0.4))
            last_label = w
    return out


def odometer(x, y, digits, clip_id, delay):
    """Each digit is a strip of 0-9 twice over, clipped to one line and resting on its own value."""
    size = TYPE["number"][4]
    cell = max(measure(str(d), "number") for d in range(10))
    cap = 0.74 * size
    out = [f'<clipPath id="{clip_id}"><rect x="{x - 4:.1f}" y="{y - cap - 6:.1f}" width="{COLUMN:.1f}"'
           f' height="{cap + 14:.1f}"/></clipPath>', f'<g clip-path="url(#{clip_id})">']
    cursor = x
    for k, ch in enumerate(digits):
        if not ch.isdigit():
            out.append(text(cursor, y, ch, "number", "ink"))
            cursor += measure(ch, "number")
            continue
        target = 10 + int(ch)
        strip = "".join(text(cursor + cell / 2, y + n * ROLL_STEP, str(n % 10), "number", "ink", anchor="middle")
                        for n in range(20))
        out.append(f'<g class="roll" style="transform:translateY(-{target * ROLL_STEP:.1f}px);'
                   f'animation-delay:{delay + k * 0.06:.2f}s">{strip}</g>')
        cursor += cell
    out.append("</g>")
    return out


def document(p, height, body):
    head = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}">',
        f"<title>{NAME}</title>",
        f"<desc>{NAME}, {' '.join(HEADLINE)} Expertise, stack, languages, recent work and a year of"
        " GitHub activity, refreshed daily.</desc>",
        "<style>",
        *font_faces(),
        *type_rules(),
        "text { white-space: pre; }",
        f".ink {{ fill: {p['ink']}; }} .muted {{ fill: {p['muted']}; }} .faint {{ fill: {p['faint']}; }}",
        "@keyframes fade { from { opacity: 0; transform: translateY(10px); } }",
        "@keyframes rise { from { transform: translateY(130px); } }",
        "@keyframes draw { from { transform: scaleX(0); } }",
        "@keyframes pop { from { opacity: 0; transform: scale(0); } }",
        # Start one step below the strip, so each digit rolls in from blank.
        f"@keyframes roll {{ from {{ transform: translateY({ROLL_STEP}px); }} }}",
        "@keyframes ripple { 0%, 10%, 100% { transform: none; } 5% { transform: translateY(-5px); } }",
        "@keyframes ring { from { opacity: 0.9; transform: scale(1); } to { opacity: 0; transform: scale(3.2); } }",
        ".fade { animation: fade 0.9s cubic-bezier(.16,1,.3,1) both; }",
        ".rise { animation: rise 1.1s cubic-bezier(.16,1,.3,1) both; }",
        ".draw { transform-box: fill-box; transform-origin: left center;"
        " animation: draw 1.1s cubic-bezier(.65,0,.35,1) both; }",
        ".pop { transform-box: fill-box; transform-origin: center; animation: pop 0.5s cubic-bezier(.34,1.56,.64,1) both; }",
        ".roll { animation: roll 1.8s cubic-bezier(.16,1,.3,1) both; }",
        ".ripple { animation: ripple 9s ease-in-out infinite; }",
        ".ring { transform-box: fill-box; transform-origin: center;"
        " animation: ring 2.2s cubic-bezier(.16,1,.3,1) infinite; }",
        "@media (prefers-reduced-motion: reduce) { * { animation: none !important; } .ring { display: none; } }",
        "</style>",
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="3" fill="{p["bg"]}" stroke="{p["frame"]}"/>',
    ]
    return "\n".join(head + body + ["</svg>"]) + "\n"


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
    stats["active_days"] = sum(1 for week in stats["weeks"] for d in week if d["count"])
    print(json.dumps({k: v for k, v in stats.items() if k != "weeks"}))

    today = dt.date.fromisoformat(stats["weeks"][-1][-1]["date"])
    for theme in ("dark", "light"):
        (ASSETS / f"card-{theme}.svg").write_text(render(theme, stats, today), encoding="utf-8")
    print(f"wrote {ASSETS / 'card-dark.svg'} and {ASSETS / 'card-light.svg'}")


if __name__ == "__main__":
    main()
