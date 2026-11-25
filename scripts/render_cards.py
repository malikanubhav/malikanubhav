#!/usr/bin/env python3
"""Redraw the animated README cards from the live contribution calendar.

    python scripts/render_cards.py            # scrape, write SVGs, update README
    STATIC=1 python scripts/render_cards.py   # same, but no animation (end state only)
    OFFLINE=1 python scripts/render_cards.py  # reuse data/contributions.json

Animations are CSS keyframes inside each SVG. GitHub shows the SVGs through
<img>, which runs an SVG's own <style> but no scripts and no external loads.
Every element sits at its final state in the markup and animates *from* its
start state, so a renderer that ignores CSS still shows a complete card, and
prefers-reduced-motion turns everything off.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

USER = "malikanubhav"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "contributions.json"
README = ROOT / "README.md"
STATIC = os.environ.get("STATIC") == "1"
OFFLINE = os.environ.get("OFFLINE") == "1"

W = 1000
FONT = "ui-monospace,'JetBrains Mono','Cascadia Mono','Courier New',monospace"
CH = 0.6  # monospace advance per em

PALETTES = {
    "dark": dict(bg="#000000", frame="#00C62F", prompt="#00FF41", grid="#16331D",
                 num="#1FD64A", dim="#4E7F5C", label="#8CFFA9", peak="#D6FFE1",
                 bar="#0B4D1A", hi="#1FD64A", edge="#0B4D1A",
                 levels=["#07240D", "#0B6B22", "#12A233", "#1FD64A", "#4DFF6E"]),
    "light": dict(bg="#F4FBF5", frame="#0B7D28", prompt="#046A1C", grid="#DCE8DF",
                  num="#1F7034", dim="#5C8A6B", label="#0C3F1A", peak="#08300F",
                  bar="#A5DCB2", hi="#1F7034", edge="#9AD3A8",
                  levels=["#DCEFE0", "#9AD3A8", "#4E9A66", "#0B7D28", "#046A1C"]),
}

MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
WEEKDAYS = "Mon Tue Wed Thu Fri Sat Sun".split()
WEEKDAY_NAMES = "Monday Tuesday Wednesday Thursday Friday Saturday Sunday".split()


# --------------------------------------------------------------------- data

def scrape() -> list[dict]:
    url = f"https://github.com/users/{USER}/contributions"
    req = urllib.request.Request(url, headers={"User-Agent": "readme-cards"})
    page = urllib.request.urlopen(req, timeout=30).read().decode()

    # Cells carry date + id; counts live in <tool-tip for="id">. Cells come
    # out row by row (weekday), so sort by date afterwards.
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
        expected = int(m.group(1).replace(",", ""))
        got = sum(x["count"] for x in days)
        if got != expected:
            raise SystemExit(f"scrape mismatch: cells sum to {got}, header says {expected}")
    if len(days) < 300:
        raise SystemExit(f"scrape looks wrong: only {len(days)} days")
    return days


def load() -> list[dict]:
    if OFFLINE and DATA.exists():
        return json.loads(DATA.read_text())["days"]
    days = scrape()
    DATA.parent.mkdir(exist_ok=True)
    DATA.write_text(json.dumps({"user": USER, "days": days}, indent=1) + "\n")
    return days


def summarise(days: list[dict]) -> dict:
    counts = [d["count"] for d in days]
    total = sum(counts)
    active = sum(1 for c in counts if c)
    streak = best_streak = 0
    for c in counts:
        streak = streak + 1 if c else 0
        best_streak = max(best_streak, streak)
    peak = max(days, key=lambda d: (d["count"], d["date"]))

    months: dict[tuple, int] = defaultdict(int)
    for d in days:
        y, m, _ = map(int, d["date"].split("-"))
        months[(y, m)] += d["count"]
    weekdays = Counter()
    for d in days:
        weekdays[dt.date.fromisoformat(d["date"]).weekday()] += d["count"]

    return dict(total=total, active=active, streak=best_streak,
                best=peak["count"], best_date=peak["date"],
                avg=round(total / active, 1) if active else 0,
                months=sorted(months.items()),
                weekdays=[weekdays[i] for i in range(7)],
                first=days[0]["date"], last=days[-1]["date"], n=len(days))


# ------------------------------------------------------------------ helpers

def nice_ticks(top: int, n: int = 4) -> list[int]:
    top = max(top, 1)
    return [round(top * i / n) for i in range(n + 1)]


def bar_path(x: float, y0: float, w: float, h: float, r: float = 4) -> str:
    r = min(r, h, w / 2)
    t = y0 - h
    return (f"M{x:.1f},{y0:.1f} L{x:.1f},{t + r:.1f} Q{x:.1f},{t:.1f} {x + r:.1f},{t:.1f} "
            f"L{x + w - r:.1f},{t:.1f} Q{x + w:.1f},{t:.1f} {x + w:.1f},{t + r:.1f} "
            f"L{x + w:.1f},{y0:.1f} Z")


BASE_CSS = """
.a{animation-fill-mode:backwards;animation-timing-function:cubic-bezier(.2,.8,.2,1)}
.fx{pointer-events:none}
.wipe{transform-box:fill-box;transform-origin:right;animation:wipe var(--d,.6s) steps(var(--n,20)) var(--t,0s) both}
.cur{animation:blink 1.1s steps(1) infinite}
.bar{transform-box:fill-box;transform-origin:50% 100%;animation-name:grow;animation-duration:.8s}
.pop{transform-box:fill-box;transform-origin:center;animation-name:pop;animation-duration:.45s;animation-timing-function:cubic-bezier(.3,1.6,.5,1)}
.fade{animation-name:fade;animation-duration:.6s}
.rise{transform-box:fill-box;transform-origin:0 100%;animation-name:rise;animation-duration:.75s}
.f{opacity:0;animation-name:on;animation-timing-function:linear;animation-fill-mode:none}
.hold{animation-name:off;animation-timing-function:linear;animation-fill-mode:none}
.ring{opacity:0;transform-box:fill-box;transform-origin:center;animation:ring 2.4s ease-out var(--t,2s) infinite}
.draw{animation:draw 1.8s cubic-bezier(.45,0,.2,1) var(--t,.4s) backwards}
@keyframes wipe{from{transform:scaleX(1)}to{transform:scaleX(0)}}
@keyframes blink{50%{opacity:0}}
@keyframes grow{from{transform:scaleY(0)}}
@keyframes pop{from{opacity:0;transform:scale(.2)}}
@keyframes fade{from{opacity:0}}
@keyframes rise{from{opacity:0;transform:translateY(22px) rotate(-2.5deg)}70%{opacity:1;transform:translateY(-3px) rotate(.4deg)}}
@keyframes on{from,to{opacity:1}}
@keyframes off{from,to{opacity:0}}
@keyframes ring{0%{opacity:.9;transform:scale(1)}70%,100%{opacity:0;transform:scale(2.4)}}
@keyframes draw{from{stroke-dashoffset:1}}
@media (prefers-reduced-motion:reduce){*{animation:none!important}.fx{display:none}}
"""


def style_block() -> str:
    return "" if STATIC else f"<style>{BASE_CSS.strip()}</style>"


def anim(cls: str, delay: float, extra: str = "") -> str:
    """class + inline delay, or nothing when rendering the static end state."""
    if STATIC:
        return ""
    return f' class="a {cls}" style="animation-delay:{delay:.2f}s{";" + extra if extra else ""}"'


def frame(p: dict, h: int, prompt: str, right: str, label: str, fs: int = 14,
          py: int = 58, inner_stroke: str | None = None) -> list[str]:
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {h}" width="{W}" height="{h}" '
        f'font-family="{FONT}" role="img" aria-label="{html.escape(label)}">',
        f"<title>{html.escape(label)}</title>",
        style_block(),
        f'<rect x="0" y="0" width="{W}" height="{h}" fill="{p["bg"]}"/>',
        f'<rect x="14" y="14" width="972" height="{h - 28}" fill="none" stroke="{p["frame"]}" '
        f'stroke-width="1.6" stroke-dasharray="7 6" opacity="0.85"/>',
        f'<rect x="26" y="26" width="948" height="{h - 52}" fill="{p["bg"]}" '
        f'stroke="{inner_stroke or p["grid"]}" stroke-width="1"/>',
        f'<text x="48" y="{py}" font-size="{fs}" fill="{p["prompt"]}">{html.escape(prompt)}</text>',
        f'<text x="952" y="{py}" font-size="{fs}" fill="{p["label"]}" text-anchor="end"'
        f'{anim("fade", 0.7)}>{html.escape(right)}</text>',
    ]
    if not STATIC:
        # Type the prompt in: a background-coloured cover shrinks in steps,
        # then a block cursor blinks after the command.
        chars = len(prompt)
        tw = chars * CH * fs
        dur = min(0.9, 0.025 * chars)
        out.append(f'<rect class="fx wipe" x="46" y="{py - fs}" width="{tw + 6:.1f}" '
                   f'height="{fs + 6}" fill="{p["bg"]}" style="--d:{dur:.2f}s;--n:{chars}"/>')
        out.append(f'<rect class="fx cur" x="{48 + tw + 4:.1f}" y="{py - fs + 2}" '
                   f'width="{fs * 0.6:.1f}" height="{fs}" fill="{p["prompt"]}" opacity="0.8"/>')
    return out


def write(name: str, theme: str, parts: list[str]) -> None:
    parts.append("</svg>")
    (ROOT / f"{name}-{theme}.svg").write_text("".join(x for x in parts if x))


# -------------------------------------------------------------------- cards

def contrib(p: dict, theme: str, days: list[dict], s: dict, levels: list[int]) -> None:
    h = 278
    label = f"Contribution calendar: {s['total']:,} contributions, {s['active']} active days"
    out = frame(p, h, "anubhav@matrix:~$ git log --graph --all",
                f"{s['total']:,} contributions · last 12 months", label,
                fs=15, py=60, inner_stroke=p["edge"])

    first = dt.date.fromisoformat(days[0]["date"])
    lead = (first.weekday() + 1) % 7  # rows start on Sunday
    x0, y0, step, sz = 96, 92, 16, 13
    weeks: dict[int, list[str]] = defaultdict(list)
    seen_month = None
    month_labels = []
    peak_xy = None
    for i, d in enumerate(days):
        slot = i + lead
        col, row = divmod(slot, 7)
        x, y = x0 + col * step, y0 + row * step
        date = dt.date.fromisoformat(d["date"])
        if row == 0 and date.month != seen_month:
            seen_month = date.month
            month_labels.append((x, MONTHS[date.month - 1]))
        lvl = levels[i]
        weeks[col].append(f'<rect x="{x}" y="{y}" width="{sz}" height="{sz}" rx="2" '
                          f'fill="{p["levels"][lvl]}"><title>{d["count"]} on {d["date"]}</title></rect>')
        if d["date"] == s["best_date"]:
            peak_xy = (x, y)

    # Drop a month label that would collide with the next one.
    kept = [m for j, m in enumerate(month_labels)
            if j + 1 == len(month_labels) or month_labels[j + 1][0] - m[0] >= 40]
    for x, name in kept:
        out.append(f'<text x="{x}" y="80" font-size="12" fill="{p["label"]}"{anim("fade", .5)}>{name}</text>')
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        out.append(f'<text x="84" y="{y0 + row * step + 12}" font-size="12" fill="{p["label"]}" '
                   f'text-anchor="end">{name}</text>')

    # Squares pop in a week at a time, left to right.
    ncols = max(weeks) + 1
    for col in range(ncols):
        out.append(f"<g{anim('pop', 0.55 + col * 1.4 / ncols)}>" + "".join(weeks[col]) + "</g>")

    if peak_xy and not STATIC:
        x, y = peak_xy
        out.append(f'<rect class="fx ring" x="{x}" y="{y}" width="{sz}" height="{sz}" rx="2" '
                   f'fill="none" stroke="{p["peak"]}" stroke-width="1.5" style="--t:2.3s"/>')

    ly = 230
    out.append(f'<text x="96" y="{ly + 12}" font-size="12" fill="{p["label"]}">Less</text>')
    for k, c in enumerate(p["levels"]):
        out.append(f'<rect x="{138 + 17 * k}" y="{ly}" width="13" height="13" rx="2" fill="{c}"/>')
    out.append(f'<text x="231" y="{ly + 12}" font-size="12" fill="{p["label"]}">More</text>')
    out.append(f'<text x="952" y="{ly + 12}" font-size="12" fill="{p["dim"]}" text-anchor="end"'
               f'{anim("fade", 2.0)}>{s["active"]} active days · peak {s["best"]} on {s["best_date"]} · '
               f'{s["first"]} → {s["last"]}</text>')
    write("contrib", theme, out)


def counter(x: float, y: float, value: int, fs: int, fill: str, start: float, dur: float) -> str:
    """A number that counts up from zero, CSS only.

    Intermediate values are stacked texts, each visible for one slice of the
    count. The final text is visible by default and only hidden until the
    count ends, so reduced-motion and static renders show the real number.
    """
    final = f"{value:,}"
    if STATIC or value == 0:
        return f'<text x="{x}" y="{y}" font-size="{fs}" fill="{fill}">{final}</text>'
    n = 18
    slice_ = dur / n
    vals, out = [], []
    for i in range(n):
        t = i / n
        v = round(value * (1 - (1 - t) ** 3))
        vals.append(v)
    for i, v in enumerate(vals):
        out.append(f'<text class="fx f" x="{x}" y="{y}" font-size="{fs}" fill="{fill}" '
                   f'style="animation-duration:{slice_:.3f}s;animation-delay:{start + i * slice_:.3f}s">{v:,}</text>')
    out.append(f'<text class="hold" x="{x}" y="{y}" font-size="{fs}" fill="{fill}" '
               f'style="animation-duration:{start + dur:.3f}s">{final}</text>')
    return "".join(out)


def stats(p: dict, theme: str, s: dict) -> None:
    h = 150
    tiles = [(s["total"], "contributions"), (s["active"], "active days"),
             (s["streak"], "longest streak"), (s["best"], "best single day")]
    label = (f"{s['total']:,} contributions, {s['active']} active days, "
             f"longest streak {s['streak']}, best day {s['best']}")
    out = frame(p, h, "anubhav@matrix:~$ stat --summary", "last 12 months", label)
    for i, (v, name) in enumerate(tiles):
        x = 48 + i * 230
        t0 = 0.45 + i * 0.15
        out.append(f"<g{anim('rise', t0)}>")
        out.append(f'<rect x="{x}" y="76" width="214" height="52" fill="none" stroke="{p["grid"]}" stroke-width="1"/>')
        fs = 30 if len(f"{v:,}") <= 4 else 24
        out.append(counter(x + 14, 108, v, fs, p["num"], t0 + 0.2, 1.1))
        out.append(f'<text x="{x + 200}" y="108" font-size="12" fill="{p["dim"]}" text-anchor="end">{name}</text>')
        out.append("</g>")
    write("stats", theme, out)


def bars(p: dict, theme: str, name: str, h: int, prompt: str, right: str, label: str,
         labels: list[str], values: list[int], base: float, highlight: set[int],
         lfs: int, bar_w_ratio: float, colour_all: bool, coloured: set[int] = frozenset()) -> None:
    out = frame(p, h, prompt, right, label)
    top = max(values) or 1
    ticks = nice_ticks(top)
    plot_top, plot_bot = 92.0, base
    for k, tv in enumerate(ticks):
        y = plot_bot - (plot_bot - plot_top) * k / 4
        out.append(f'<line x1="76" y1="{y:.1f}" x2="952" y2="{y:.1f}" stroke="{p["grid"]}" stroke-width="1"/>')
        out.append(f'<text x="66" y="{y + 4:.1f}" font-size="11" fill="{p["dim"]}" text-anchor="end">{tv}</text>')
    n = len(values)
    slot = (952 - 76) / n
    bw = slot * bar_w_ratio
    for i, v in enumerate(values):
        cx = 76 + slot * (i + 0.5)
        bh = (plot_bot - plot_top) * v / top
        fill = p["hi"] if (colour_all or i in coloured) else p["bar"]
        if bh > 0.5:
            out.append(f'<path d="{bar_path(cx - bw / 2, plot_bot, bw, bh)}" fill="{fill}"'
                       f'{anim("bar", 0.5 + i * 0.07)}><title>{labels[i]}: {v}</title></path>')
        out.append(f'<text x="{cx:.1f}" y="{plot_bot + 20:.0f}" '
                   f'font-size="{lfs}" fill="{p["dim"]}" text-anchor="middle">{labels[i].split(" ")[0]}</text>')
        if i in highlight:
            out.append(f'<text x="{cx:.1f}" y="{plot_bot - bh - 8:.1f}" font-size="13" fill="{p["peak"]}" '
                       f'text-anchor="middle"{anim("pop", 0.9 + n * 0.07)}>{v}</text>')
    write(name, theme, out)


def months_card(p: dict, theme: str, s: dict) -> None:
    labels = [f"{MONTHS[m - 1]} {y}" for (y, m), _ in s["months"]]
    vals = [v for _, v in s["months"]]
    best = max(range(len(vals)), key=lambda i: vals[i])
    bars(p, theme, "months", 300, "anubhav@matrix:~$ git log --since=1.year | by-month",
         "contributions per month",
         f"Contributions per month, busiest {labels[best]} with {vals[best]}",
         labels, vals, 234.0, {best}, 11, 0.66, True)


def weekdays_card(p: dict, theme: str, s: dict) -> None:
    vals = s["weekdays"]
    hi = max(range(7), key=lambda i: vals[i])
    lo = min(range(7), key=lambda i: vals[i])
    bars(p, theme, "weekdays", 270, "anubhav@matrix:~$ by-weekday", "when the commits land",
         f"Contributions by weekday — {WEEKDAY_NAMES[hi]} highest at {vals[hi]}, "
         f"{WEEKDAY_NAMES[lo]} lowest at {vals[lo]}",
         WEEKDAYS, vals, 210.0, {hi, lo}, 12, 0.42, False, coloured={hi})


def cumulative_card(p: dict, theme: str, days: list[dict], s: dict) -> None:
    h = 280
    out = frame(p, h, "anubhav@matrix:~$ cumulative", "total accrued over the year",
                f"Cumulative contributions, {s['total']:,} over the year")
    top, plot_top, plot_bot = max(s["total"], 1), 92.0, 220.0
    for k, tv in enumerate(nice_ticks(top)):
        y = plot_bot - (plot_bot - plot_top) * k / 4
        out.append(f'<line x1="76" y1="{y:.1f}" x2="952" y2="{y:.1f}" stroke="{p["grid"]}" stroke-width="1"/>')
        out.append(f'<text x="66" y="{y + 4:.1f}" font-size="11" fill="{p["dim"]}" text-anchor="end">{tv}</text>')
    n = len(days)
    run, pts, seen = 0, [], None
    for i, d in enumerate(days):
        run += d["count"]
        x = 76 + (952 - 76) * i / (n - 1)
        pts.append((x, plot_bot - (plot_bot - plot_top) * run / top))
        m = int(d["date"][5:7])
        if d["date"][8:] == "01":
            if m != seen:
                seen = m
                out.append(f'<text x="{x:.1f}" y="240" font-size="11" fill="{p["dim"]}" '
                           f'text-anchor="middle">{MONTHS[m - 1]}</text>')
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{line} L952,{plot_bot} L76,{plot_bot} Z"
    out.append(f'<path d="{area}" fill="{p["hi"]}" opacity="0.16"{anim("fade", 1.6)}/>')
    draw = "" if STATIC else ' class="draw" pathLength="1" stroke-dasharray="1"'
    out.append(f'<path d="{line}" fill="none" stroke="{p["hi"]}" stroke-width="2" stroke-linejoin="round"{draw}/>')
    ex, ey = pts[-1]
    out.append(f'<circle cx="{ex:.1f}" cy="{ey:.1f}" r="4.5" fill="{p["hi"]}" stroke="{p["bg"]}" '
               f'stroke-width="2"{anim("pop", 2.2)}/>')
    out.append(f'<text x="{ex - 8:.1f}" y="{ey + 16:.1f}" font-size="14" fill="{p["peak"]}" '
               f'text-anchor="end"{anim("fade", 2.3)}>{s["total"]:,}</text>')
    write("cumulative", theme, out)


# ------------------------------------------------------------------- readme

def picture(name: str, alt: str) -> str:
    return (f'<picture>\n'
            f'  <source media="(prefers-color-scheme: dark)"  srcset="./{name}-dark.svg">\n'
            f'  <source media="(prefers-color-scheme: light)" srcset="./{name}-light.svg">\n'
            f'  <img src="./{name}-dark.svg" width="100%" alt="{html.escape(alt)}">\n'
            f'</picture>')


def readme(s: dict) -> None:
    hi = max(range(7), key=lambda i: s["weekdays"][i])
    lo = min(range(7), key=lambda i: s["weekdays"][i])
    charts = "\n\n<br>\n\n".join([
        picture("contrib", f"Contribution calendar: {s['total']:,} contributions, {s['active']} active days"),
        picture("stats", f"{s['total']:,} contributions, {s['active']} active days, "
                         f"longest streak {s['streak']}, best day {s['best']}"),
        picture("weekdays", f"Contributions by weekday — {WEEKDAY_NAMES[hi]} highest at "
                            f"{s['weekdays'][hi]}, {WEEKDAY_NAMES[lo]} lowest at {s['weekdays'][lo]}"),
    ])
    month_rows = "\n".join(f"| {MONTHS[m - 1]} {y} | {v} |" for (y, m), v in s["months"])
    day_rows = "\n".join(f"| {d} | {v} |" for d, v in zip(WEEKDAYS, s["weekdays"]))
    numbers = (
        "<details>\n<summary>The numbers behind the charts</summary>\n\n"
        f"| Month | Contributions |\n|---|---|\n{month_rows}\n\n"
        f"| Weekday | Contributions |\n|---|---|\n{day_rows}\n\n"
        f"Peak day: **{s['best_date']}** with **{s['best']}** contributions ·\n"
        f"Average on an active day: **{s['avg']}** ·\n"
        f"Window: {s['n']} days\n\n</details>"
    )
    text = README.read_text()
    for tag, body in (("charts", charts), ("numbers", numbers)):
        pat = re.compile(rf"(<!-- {tag}:start -->\n).*?(\n<!-- {tag}:end -->)", re.S)
        if not pat.search(text):
            raise SystemExit(f"README is missing the <!-- {tag}:start/end --> markers")
        text = pat.sub(lambda m: m.group(1) + body + m.group(2), text)
    README.write_text(text)


def main() -> None:
    days = load()
    s = summarise(days)
    levels = [d["level"] for d in days]  # GitHub's own 0-4 shading
    for theme, p in PALETTES.items():
        contrib(p, theme, days, s, levels)
        stats(p, theme, s)
        months_card(p, theme, s)
        weekdays_card(p, theme, s)
        cumulative_card(p, theme, days, s)
    readme(s)
    # The banner is hand-made; only keep its contribution count current.
    for theme in PALETTES:
        b = ROOT / f"banner-{theme}.svg"
        if b.exists():
            b.write_text(re.sub(r"[\d,]+ contributions in the last year",
                                f"{s['total']:,} contributions in the last year", b.read_text()))
    print(f"{s['total']} contributions · {s['active']} active days · streak {s['streak']} · "
          f"best {s['best']} on {s['best_date']} · {s['first']} → {s['last']}")


if __name__ == "__main__":
    main()
