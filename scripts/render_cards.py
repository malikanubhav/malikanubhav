#!/usr/bin/env python3
"""Draw the README cards: hero, three linked tiles, activity, heatmap, repos.

    python scripts/render_cards.py            # scrape, write cards/*.svg, update README
    STATIC=1 python scripts/render_cards.py   # end state only, no animation
    OFFLINE=1 python scripts/render_cards.py  # reuse data/*.json, no network

GitHub shows each card through <img>: the SVG's own <style> runs (CSS
keyframes), scripts and external loads don't. So fonts are embedded as
subset WOFF data URIs (fonts/*.woff.b64), every element sits at its final
state in the markup and animates *from* its start, and prefers-reduced-motion
switches the motion off. Standard library only, so the daily Action needs
no installs.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import urllib.request
from collections import defaultdict
from pathlib import Path

USER = "malikanubhav"
SITE = "https://www.anubhavmalik.com"
ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "cards"
DATA = ROOT / "data"
README = ROOT / "README.md"
STATIC = os.environ.get("STATIC") == "1"
OFFLINE = os.environ.get("OFFLINE") == "1"

W = 880.0
TILE_W = 293.333

INK, MUTED, FAINT, LINE = "#141414", "#5F5F5A", "#8F8F89", "#DEDDD8"
PAPER, BLUE, RED, YELLOW, EMPTY = "#F2F1EE", "#2F54FF", "#EE3B2F", "#FFC61E", "#C9C9C3"
HEAT = ["#E3E3DE", "#C7D1FF", "#8FA3FF", "#5675FF", "#2F54FF"]

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()

# ------------------------------------------------------------------ content
# From the portfolio (src/content.ts). Keep claims word for word.

HERO = dict(
    eyebrow="AI ENGINEER AT WEXA · HYDERABAD",
    first="Anubhav", last="Malik",
    bio=["I build production AI agents: the orchestration, memory",
         "and browser automation that keep them reliable."],
    link="anubhavmalik.com",
)

TILES = [
    dict(key="build", label="BUILD", colour=BLUE, ink="#FFFFFF",
         value=25, fmt="{}+", word=" apps", href=SITE,
         lines=["Wired into one agent platform at", "Wexa, with graph memory recalled", "in under 300 ms."]),
    dict(key="scale", label="SCALE", colour=RED, ink="#FFFFFF",
         value=50, fmt="{}K+", word=" learners", href=SITE,
         lines=["Served by the Python and Node.js", "services I built at Ixambee."]),
    dict(key="ship", label="SHIP", colour=YELLOW, ink=INK,
         value=None, fmt="{}", word=" repos", href=f"https://github.com/{USER}?tab=repositories",
         lines=["Public on GitHub, from a graph", "hackathon build to side projects."]),
]

REPOS = [
    dict(name="actron", title="Actron", lang="Python",
         lines=["Checks what a team already", "decided before an AI writes", "code. Built at Graph Hacks."]),
    dict(name="rishikeshin", title="rishikeshin", lang="TypeScript",
         lines=["Everything you need to know", "about Rishikesh."]),
    dict(name="Filmflix", title="Filmflix", lang="JavaScript",
         lines=["Movies and shows streaming", "web application."]),
]
LANG_COLOUR = {"Python": "#3572A5", "TypeScript": "#3178C6", "JavaScript": "#E3B100"}

# --------------------------------------------------------------------- data


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "readme-cards"})
    return urllib.request.urlopen(req, timeout=30).read().decode()


def scrape_days() -> list[dict]:
    page = fetch(f"https://github.com/users/{USER}/contributions")
    # Cells carry date + id + level; counts live in <tool-tip for="id">.
    # Cells come out row by row (weekday), so sort by date afterwards.
    cells = {i: (d, int(lv)) for d, i, lv in re.findall(
        r'data-date="(\d{4}-\d{2}-\d{2})"\s+id="([^"]+)"\s+data-level="(\d)"', page)}
    tips = {}
    for for_id, text in re.findall(r'<tool-tip[^>]*\bfor="([^"]+)"[^>]*>([^<]*)', page):
        m = re.match(r"\s*([\d,]+)\s+contribution", text)
        tips[for_id] = int(m.group(1).replace(",", "")) if m else 0
    days = sorted(({"date": d, "count": tips.get(i, 0), "level": lv} for i, (d, lv) in cells.items()),
                  key=lambda x: x["date"])
    m = re.search(r"([\d,]+)\s+contributions?\s+in the last year", page)
    if m:
        expected, got = int(m.group(1).replace(",", "")), sum(x["count"] for x in days)
        if got != expected:
            raise SystemExit(f"scrape mismatch: cells sum to {got}, header says {expected}")
    if len(days) < 300:
        raise SystemExit(f"scrape looks wrong: only {len(days)} days")
    return days


def load() -> tuple[list[dict], dict]:
    DATA.mkdir(exist_ok=True)
    cfile, pfile = DATA / "contributions.json", DATA / "profile.json"
    profile = json.loads(pfile.read_text()) if pfile.exists() else {"public_repos": 21}
    if OFFLINE and cfile.exists():
        return json.loads(cfile.read_text())["days"], profile
    days = scrape_days()
    cfile.write_text(json.dumps({"user": USER, "days": days}, indent=1) + "\n")
    try:  # a failed API call keeps the last count rather than failing the job
        profile["public_repos"] = json.loads(fetch(f"https://api.github.com/users/{USER}"))["public_repos"]
        pfile.write_text(json.dumps(profile, indent=1) + "\n")
    except Exception as e:  # noqa: BLE001
        print(f"repo count unavailable, keeping {profile['public_repos']}: {e}")
    return days, profile


def summarise(days: list[dict]) -> dict:
    counts = [d["count"] for d in days]
    total, active = sum(counts), sum(1 for c in counts if c)
    streak = longest = 0
    for c in counts:
        streak = streak + 1 if c else 0
        longest = max(longest, streak)
    current = 0  # today not counted against the streak until it's over
    for c in reversed(counts[:-1] if counts and counts[-1] == 0 else counts):
        if not c:
            break
        current += 1
    peak = max(days, key=lambda d: (d["count"], d["date"]))
    months: dict[tuple, int] = defaultdict(int)
    for d in days:
        y, m, _ = map(int, d["date"].split("-"))
        months[(y, m)] += d["count"]
    return dict(total=total, active=active, longest=longest, current=current,
                best=peak["count"], best_date=peak["date"], n=len(days),
                avg=round(total / active, 1) if active else 0,
                months=sorted(months.items())[-12:], first=days[0]["date"], last=days[-1]["date"])


# ------------------------------------------------------------------- styles

FONT_FILES = {"serif": ("Instrument Serif", "normal", 400, "serif-400"),
              "serif-i": ("Instrument Serif", "italic", 400, "serif-400-italic"),
              "sans": ("Geist", "normal", 400, "geist-400"),
              "mono": ("JetBrains Mono", "normal", 400, "mono-400")}
SERIF = "'Instrument Serif',Georgia,serif"
SANS = "Geist,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif"
MONO = "'JetBrains Mono',ui-monospace,Menlo,Consolas,monospace"

MOTION = """
.a{animation-fill-mode:backwards;animation-timing-function:cubic-bezier(.2,.8,.2,1)}
.up{animation-name:up;animation-duration:.8s}
.fade{animation-name:fade;animation-duration:.7s}
.row{animation-name:fade;animation-duration:.25s;animation-timing-function:linear}
.swing{transform-box:fill-box;transform-origin:50% 100%;animation-name:swing;animation-duration:1s;animation-timing-function:cubic-bezier(.3,1.5,.5,1)}
.bar{transform-box:fill-box;transform-origin:50% 100%;animation-name:grow;animation-duration:.9s}
.pop{transform-box:fill-box;transform-origin:center;animation-name:pop;animation-duration:.5s;animation-timing-function:cubic-bezier(.3,1.6,.5,1)}
.f{opacity:0;animation-name:on;animation-timing-function:linear;animation-fill-mode:none}
.hold{animation-name:off;animation-timing-function:linear;animation-fill-mode:none}
.ring{opacity:0;transform-box:fill-box;transform-origin:center;animation:ring 2.8s ease-out infinite}
.shine{animation:shine 7s cubic-bezier(.4,0,.2,1) infinite}
@keyframes up{from{opacity:0;transform:translateY(18px)}}
@keyframes fade{from{opacity:0}}
@keyframes swing{from{opacity:0;transform:translateY(46px) rotate(-5deg)}60%{opacity:1;transform:translateY(-6px) rotate(1.2deg)}80%{transform:translateY(2px) rotate(-.4deg)}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes pop{from{opacity:0;transform:scale(.2)}}
@keyframes on{from,to{opacity:1}}
@keyframes off{from,to{opacity:0}}
@keyframes ring{0%{opacity:.8;transform:scale(1)}60%,100%{opacity:0;transform:scale(2.2)}}
@keyframes shine{0%{transform:translateX(-140%) skewX(-20deg)}22%,100%{transform:translateX(260%) skewX(-20deg)}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.fx{display:none}}
"""


def style(*fonts: str) -> str:
    faces = []
    for key in fonts:
        family, fstyle, weight, file = FONT_FILES[key]
        b64 = (ROOT / "fonts" / f"{file}.woff.b64").read_text().strip()
        faces.append(f"@font-face{{font-family:'{family}';font-style:{fstyle};font-weight:{weight};"
                     f"src:url(data:font/woff;base64,{b64}) format('woff')}}")
    css = "".join(faces) + ("" if STATIC else MOTION.strip())
    return f"<style>{css}</style>"


def anim(cls: str, delay: float) -> str:
    """class + delay, or nothing when rendering the static end state."""
    return "" if STATIC else f' class="a {cls}" style="animation-delay:{delay:.2f}s"'


def svg(w: float, h: int, label: str, fonts: tuple, body: list[str]) -> str:
    return "".join([
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.3f}" height="{h}" viewBox="0 0 {w:.3f} {h}" '
        f'role="img" aria-label="{html.escape(label)}"><title>{html.escape(label)}</title>',
        style(*fonts), *body, "</svg>"])


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def counter(x: float, y: float, value: int, fmt: str, word: str, size: int, fill: str,
            start: float, dur: float = 1.2, extra: str = "", tail: str = "") -> str:
    """Serif number + italic word that counts up from zero, CSS only.

    Intermediate frames are stacked texts, each shown for one slice of the
    count. The real number is visible by default and only hidden until the
    count ends, so static and reduced-motion renders show it straight away.
    """
    def text(v: int, attrs: str) -> str:
        w = f'<tspan font-style="italic">{esc(word)}</tspan>' if word else ""
        return (f'<text x="{x:.1f}" y="{y:.1f}" font-family="{SERIF}" font-size="{size}" fill="{fill}"'
                f'{extra}{attrs}>{esc(fmt.format(f"{v:,}"))}{w}{tail}</text>')
    if STATIC or not value:
        return text(value, "")
    n = 18
    slice_ = dur / n
    out = [text(round(value * (1 - (1 - i / n) ** 3)),
                f' class="fx f" style="animation-duration:{slice_ + .02:.3f}s;animation-delay:{start + i * slice_:.3f}s"')
           for i in range(n)]
    out.append(text(value, f' class="hold" style="animation-duration:{start + dur:.3f}s"'))
    return "".join(out)


def card_bg(w: float, h: int, fill: str = PAPER) -> str:
    return f'<rect x="0" y="0" width="{w:.3f}" height="{h}" rx="16" fill="{fill}"/>'


def write(name: str, content: str) -> None:
    CARDS.mkdir(exist_ok=True)
    (CARDS / f"{name}.svg").write_text(content)


# -------------------------------------------------------------------- cards


def hero() -> str:
    h = 432
    b = [card_bg(W, h)]
    b.append(f'<g{anim("fade", .1)}><rect x="48" y="58" width="8" height="8" rx="1.5" fill="{BLUE}"/>'
             f'<text x="66" y="66" font-family="{MONO}" font-size="12" letter-spacing="1.2" fill="{MUTED}">'
             f'{esc(HERO["eyebrow"])}</text></g>')
    # Name: two serif lines, the second in italic, with a blue shine that
    # sweeps across the letters now and then (a band clipped to the text).
    name = (f'<text x="44" y="200" font-family="{SERIF}" font-size="118" letter-spacing="-2">'
            f'{esc(HERO["first"])}</text>'
            f'<text x="50" y="300" font-family="{SERIF}" font-style="italic" font-size="118" '
            f'letter-spacing="-2">{esc(HERO["last"])}</text>')
    b.append(f'<defs><clipPath id="nm">{name}</clipPath>'
             '<linearGradient id="sh" x1="0" x2="1"><stop offset="0" stop-color="#7F95FF" stop-opacity="0"/>'
             f'<stop offset=".5" stop-color="{BLUE}" stop-opacity=".95"/>'
             '<stop offset="1" stop-color="#7F95FF" stop-opacity="0"/></linearGradient></defs>')
    b.append(f'<g fill="{INK}"{anim("up", .2)}>{name}</g>')
    if not STATIC:
        b.append('<g class="fx" clip-path="url(#nm)"><rect class="shine" x="0" y="90" width="150" height="230" '
                 'fill="url(#sh)" style="animation-delay:1.6s"/></g>')
    bio = "".join(f'<tspan x="48" dy="{0 if i == 0 else 25}">{esc(t)}</tspan>' for i, t in enumerate(HERO["bio"]))
    b.append(f'<text x="48" y="346" font-family="{SANS}" font-size="17" fill="#2B2B28"{anim("fade", .7)}>{bio}</text>')
    b.append(f'<text x="48" y="402" font-family="{MONO}" font-size="12.5" fill="{INK}"{anim("fade", .9)}>'
             f'{esc(HERO["link"])}<tspan fill="{BLUE}" font-family="{SANS}" dx="8">↗</tspan></text>')
    # Portrait: ASCII rows printed one after another, top to bottom.
    rows = (DATA / "portrait.txt").read_text().rstrip("\n").split("\n")
    px, py, pw, ph = 548, 44, 292, 344
    lh = ph / len(rows)
    cols = max(len(r) for r in rows)
    b.append(f'<g font-family="{MONO}" font-size="{lh * 1.08:.2f}" fill="#8A8A83">')
    for i, r in enumerate(rows):
        if r.strip():
            b.append(f'<text x="{px}" y="{py + (i + 1) * lh:.2f}" xml:space="preserve" textLength="{pw}" '
                     f'lengthAdjust="spacingAndGlyphs"{anim("row", .5 + i * .03)}>{esc(r.ljust(cols))}</text>')
    b.append("</g>")
    return svg(W, h, f"Anubhav Malik. AI engineer at Wexa in Hyderabad. {' '.join(HERO['bio'])}",
               ("serif", "serif-i", "sans", "mono"), b)


def tile(t: dict, repos: int) -> str:
    h = 222
    value = repos if t["value"] is None else t["value"]
    b = [f"<g{anim('swing', .25)}>", card_bg(TILE_W, h, t["colour"])]
    b.append(f'<text x="24" y="40" font-family="{MONO}" font-size="11.5" letter-spacing="1.4" '
             f'fill="{t["ink"]}">{t["label"]}</text>')
    # Arrow with a ring that pulses now and then.
    b.append(f'<text x="{TILE_W - 28:.1f}" y="40" font-family="{SANS}" font-size="14" fill="{t["ink"]}" '
             f'text-anchor="middle">→</text>')
    if not STATIC:
        b.append(f'<circle class="fx ring" cx="{TILE_W - 28:.1f}" cy="35.5" r="10" fill="none" '
                 f'stroke="{t["ink"]}" stroke-width="1.2" style="animation-delay:2.4s"/>')
    b.append(counter(22, 112, value, t["fmt"], t["word"], 46, t["ink"], .7, 1.2, extra=' letter-spacing="-1"'))
    lines = "".join(f'<tspan x="24" dy="{0 if i == 0 else 19.5}">{esc(s)}</tspan>' for i, s in enumerate(t["lines"]))
    b.append(f'<text x="24" y="150" font-family="{SANS}" font-size="14" fill="{t["ink"]}"'
             f'{anim("fade", 1.1)}>{lines}</text>')
    if not STATIC:  # a soft light band crosses the tile every few seconds
        b.append(f'<defs><clipPath id="tc"><rect width="{TILE_W:.3f}" height="{h}" rx="16"/></clipPath>'
                 '<linearGradient id="tg" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
                 '<stop offset=".5" stop-color="#fff" stop-opacity=".28"/>'
                 '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>'
                 f'<g class="fx" clip-path="url(#tc)"><rect class="shine" x="0" y="-20" width="90" height="{h + 40}" '
                 f'fill="url(#tg)" style="animation-delay:3s"/></g>')
    b.append("</g>")
    word = t["fmt"].format(f"{value:,}") + t["word"]
    return svg(TILE_W, h, f"{t['label']}: {word}. {' '.join(t['lines'])}", ("serif", "serif-i", "sans", "mono"), b)


def activity(s: dict) -> str:
    h = 352
    b = [card_bg(W, h)]
    b.append(f'<text x="40" y="56" font-family="{MONO}" font-size="12" letter-spacing="1.2" fill="{MUTED}"'
             f'{anim("fade", .1)}>THE LAST 12 MONTHS ON GITHUB</text>')
    b.append(counter(38, 116, s["total"], "{}", " contributions", 54, INK, .3, 1.3, extra=' letter-spacing="-1.5"'))
    vals = [v for _, v in s["months"]]
    top = max(vals) or 1
    best = max(range(len(vals)), key=lambda i: vals[i])
    x0, slot, bw, base, ph = 40, 47.5, 37, 296, 140
    for i, ((y, m), v) in enumerate(s["months"]):
        x = x0 + i * slot
        bh = max(ph * v / top, 6)
        fill = BLUE if i == best else (EMPTY if v < top * 0.04 else INK)
        b.append(f'<rect x="{x:.1f}" y="{base - bh:.1f}" width="{bw}" height="{bh:.1f}" rx="2" fill="{fill}"'
                 f'{anim("bar", .6 + i * .06)}><title>{MONTHS[m - 1]} {y}: {v}</title></rect>')
        b.append(f'<text x="{x + bw / 2:.1f}" y="{base + 22}" font-family="{MONO}" font-size="11" fill="{MUTED}" '
                 f'text-anchor="middle">{MONTHS[m - 1]}</text>')
        if i == best:
            b.append(f'<text x="{x + bw / 2:.1f}" y="{base - bh - 10:.1f}" font-family="{MONO}" font-size="11" '
                     f'fill="{BLUE}" text-anchor="middle"{anim("pop", 1.5)}>{v:,}</text>')
    # Right column: three facts, each a serif figure over a one-line caption.
    rx = 610
    streak_cap = "longest streak" + (f", {s['current']} running now" if s["current"] else "")
    facts = [(s["longest"], " days", streak_cap), (s["active"], "", "days with a commit"),
             (s["best"], "", "on the busiest day")]
    for i, (v, word, cap) in enumerate(facts):
        y = 112 + i * 92
        tail = f'<tspan fill="{FAINT}"> / {s["n"]}</tspan>' if i == 1 else ""  # "194 / 368"
        b.append(counter(rx, y, v, "{}", word, 40, INK, .9 + i * .2, 1.0, extra=' letter-spacing="-1"', tail=tail))
        b.append(f'<text x="{rx}" y="{y + 26}" font-family="{SANS}" font-size="13.5" fill="{MUTED}"'
                 f'{anim("fade", 1.0 + i * .2)}>{esc(cap)}</text>')
        if i < 2:
            b.append(f'<line x1="{rx}" y1="{y + 50}" x2="840" y2="{y + 50}" stroke="{LINE}" stroke-width="1"/>')
    label = (f"{s['total']:,} contributions in the last year, longest streak {s['longest']} days, "
             f"{s['active']} of {s['n']} days with a commit, {s['best']} on the busiest day")
    return svg(W, h, label, ("serif", "serif-i", "sans", "mono"), b)


def heatmap(days: list[dict], s: dict) -> str:
    h = 257
    b = [card_bg(W, h)]
    b.append(f'<text x="40" y="66" font-family="{SERIF}" font-size="34" fill="{INK}" letter-spacing="-.5"'
             f'{anim("up", .1)}>Every day, <tspan font-style="italic" fill="{BLUE}">in blue</tspan></text>')
    b.append(f'<text x="840" y="62" font-family="{MONO}" font-size="11.5" letter-spacing="1.2" fill="{MUTED}" '
             f'text-anchor="end"{anim("fade", .3)}>REFRESHED DAILY</text>')
    lead = (dt.date.fromisoformat(days[0]["date"]).weekday() + 1) % 7  # rows start on Sunday
    ncols = (len(days) + lead + 6) // 7
    x0, y0 = 40, 92
    step = (840 - x0) / ncols
    sz = step - 3
    weeks: dict[int, list[str]] = defaultdict(list)
    labels, seen = [], None
    for i, d in enumerate(days):
        col, row = divmod(i + lead, 7)
        x, y = x0 + col * step, y0 + row * step
        date = dt.date.fromisoformat(d["date"])
        if row == 0 and date.month != seen:
            seen = date.month
            labels.append((x, MONTHS[date.month - 1]))
        weeks[col].append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{sz:.1f}" height="{sz:.1f}" rx="2.5" '
                          f'fill="{HEAT[d["level"]]}"><title>{d["count"]} on {d["date"]}</title></rect>')
    for col in range(ncols):  # squares pop in a week at a time, left to right
        b.append(f"<g{anim('pop', .35 + col * 1.5 / ncols)}>" + "".join(weeks[col]) + "</g>")
    ly = y0 + 7 * step + 16
    lx = 840 - 5 * 15 - 34
    # Month labels, skipping any that would crowd the next one or the legend.
    kept = [m for j, m in enumerate(labels)
            if (j + 1 == len(labels) or labels[j + 1][0] - m[0] >= 40) and m[0] < lx - 80]
    for x, name in kept:
        b.append(f'<text x="{x:.1f}" y="{ly:.1f}" font-family="{MONO}" font-size="11" fill="{MUTED}">{name}</text>')
    b.append(f'<text x="{lx - 8}" y="{ly:.1f}" font-family="{MONO}" font-size="11" fill="{MUTED}" '
             f'text-anchor="end">less</text>')
    for k, c in enumerate(HEAT):
        b.append(f'<rect x="{lx + k * 15}" y="{ly - 10:.1f}" width="11" height="11" rx="2" fill="{c}"/>')
    b.append(f'<text x="{lx + 5 * 15 + 4}" y="{ly:.1f}" font-family="{MONO}" font-size="11" fill="{MUTED}">more</text>')
    return svg(W, h, f"Contribution graph: {s['total']:,} contributions in the last year",
               ("serif", "serif-i", "mono"), b)


def repo(r: dict, i: int) -> str:
    h = 168
    b = [f"<g{anim('up', .15 + i * .12)}>", card_bg(TILE_W, h)]
    b.append(f'<text x="24" y="38" font-family="{MONO}" font-size="11.5" letter-spacing="1.4" fill="{MUTED}">'
             f'REPO</text>')
    b.append(f'<circle cx="{TILE_W - 24 - 6.6 * len(r["lang"]) - 10:.1f}" cy="34" r="4.5" '
             f'fill="{LANG_COLOUR.get(r["lang"], FAINT)}"/>'
             f'<text x="{TILE_W - 24:.1f}" y="38" font-family="{MONO}" font-size="11" fill="{MUTED}" '
             f'text-anchor="end">{esc(r["lang"])}</text>')
    b.append(f'<text x="22" y="80" font-family="{SERIF}" font-size="34" letter-spacing="-.5" fill="{INK}">'
             f'{esc(r["title"])} <tspan font-family="{SANS}" font-size="14" dy="-14">↗</tspan></text>')
    lines = "".join(f'<tspan x="24" dy="{0 if k == 0 else 19}">{esc(s)}</tspan>' for k, s in enumerate(r["lines"]))
    b.append(f'<text x="24" y="108" font-family="{SANS}" font-size="13.5" fill="#2B2B28">{lines}</text>')
    b.append("</g>")
    return svg(TILE_W, h, f"{r['title']} ({r['lang']}): {' '.join(r['lines'])}", ("serif", "sans", "mono"), b)


# ------------------------------------------------------------------- readme


def img(name: str, alt: str, width: str = "100%") -> str:
    return f'<img src="./cards/{name}.svg" width="{width}" alt="{html.escape(alt)}">'


def readme(s: dict, repos: int) -> None:
    tiles = " ".join(f'<a href="{t["href"]}">{img(t["key"], t["label"].title(), "32.5%")}</a>' for t in TILES)
    repo_row = " ".join(f'<a href="https://github.com/{USER}/{r["name"]}">'
                        f'{img("repo-" + r["name"].lower(), r["title"], "32.5%")}</a>' for r in REPOS)
    cards = "\n\n".join([
        f'<a href="{SITE}">{img("hero", "Anubhav Malik, AI engineer at Wexa")}</a>',
        tiles,
        img("activity", f"{s['total']:,} contributions in the last year, longest streak {s['longest']} days"),
        img("heatmap", f"Contribution graph: {s['total']:,} contributions in the last year"),
        repo_row,
    ])
    month_rows = "\n".join(f"| {MONTHS[m - 1]} {y} | {v} |" for (y, m), v in s["months"])
    numbers = (
        "<details>\n<summary>The numbers behind the cards</summary>\n\n"
        f"| Month | Contributions |\n|---|---|\n{month_rows}\n\n"
        f"{s['total']:,} contributions over {s['n']} days ({s['first']} to {s['last']}) ·\n"
        f"{s['active']} days with a commit · longest streak **{s['longest']}** days ·\n"
        f"busiest day **{s['best_date']}** with **{s['best']}** ·\n"
        f"average on an active day **{s['avg']}** · {repos} public repos\n\n</details>"
    )
    text = README.read_text()
    for tag, body in (("cards", cards), ("numbers", numbers)):
        pat = re.compile(rf"(<!-- {tag}:start -->\n)(?:.*?\n)?(<!-- {tag}:end -->)", re.S)
        if not pat.search(text):
            raise SystemExit(f"README is missing the <!-- {tag}:start/end --> markers")
        text = pat.sub(lambda m: m.group(1) + body + "\n" + m.group(2), text)
    README.write_text(text)


def main() -> None:
    days, profile = load()
    s = summarise(days)
    repos = profile["public_repos"]
    write("hero", hero())
    for t in TILES:
        write(t["key"], tile(t, repos))
    write("activity", activity(s))
    write("heatmap", heatmap(days, s))
    for i, r in enumerate(REPOS):
        write("repo-" + r["name"].lower(), repo(r, i))
    readme(s, repos)
    print(f"{s['total']} contributions · {s['active']} active days · longest {s['longest']} · "
          f"current {s['current']} · best {s['best']} on {s['best_date']} · {repos} repos")


if __name__ == "__main__":
    main()
