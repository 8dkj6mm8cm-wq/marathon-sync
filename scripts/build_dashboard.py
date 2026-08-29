#!/usr/bin/env python3
"""Bygger dashboard.html ud fra en dekrypteret payload.json.

Brug:  python3 scripts/build_dashboard.py payload.json dashboard.html

Outputtet er indhold til Artifact-vaerktoejet: ingen doctype, html, head eller body.
Alt CSS og JS er inline. Ingen eksterne kald ud over Google Fonts.
"""

import datetime as dt
import html
import json
import sys
from collections import defaultdict

RACE = dt.date(2027, 5, 9)
RACE_NAME = "Copenhagen Marathon"
GOAL_SECONDS = 3 * 3600 + 45 * 60
MARATHON_KM = 42.195

# Valideret palet. Lys: #1B6FA8 #C46A10 #7B3F98. Moerk: #3789C0 #CC7F28 #9C5FB6.
C_FIT, C_FAT, C_THIRD = "var(--s1)", "var(--s2)", "var(--s3)"


DOW_DK = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]


def esc(s):
    return html.escape(str(s), quote=True)


def dk_day(d):
    """Dansk ugedag og dato, fx 'tor 27/8'. strftime bruger C-locale, derfor manuelt."""
    return f"{DOW_DK[d.weekday()]} {d.day}/{d.month}"


def dk_short(d):
    return f"{d.day}/{d.month}"


def mmss(sec_per_km):
    if not sec_per_km or sec_per_km <= 0 or sec_per_km > 1800:
        return "-"
    m = int(sec_per_km // 60)
    s = int(round(sec_per_km - m * 60))
    if s == 60:
        m, s = m + 1, 0
    return f"{m}:{s:02d}"


def pace_from_mps(v):
    return 1000.0 / v if v and v > 0 else None


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- beregninger

def compute(d):
    gen = d.get("generated_date") or dt.date.today().isoformat()
    today = dt.date.fromisoformat(gen)
    acts = d.get("activities") or []
    events = d.get("events") or []
    wel = sorted((d.get("wellness") or []), key=lambda x: str(x.get("id")))
    detail = {a.get("id"): a for a in (d.get("recent_activity_detail") or [])}

    runs = []
    for a in acts:
        if a.get("type") not in ("Run", "VirtualRun", "TrailRun"):
            continue
        day = (a.get("start_date_local") or "")[:10]
        if not day:
            continue
        dist = (a.get("distance") or 0) / 1000.0
        mt = a.get("moving_time") or 0
        det = detail.get(a.get("id")) or {}
        gap = det.get("gap")
        runs.append({
            "date": day,
            "km": dist,
            "sec": mt,
            "hr": a.get("average_heartrate"),
            "load": a.get("icu_training_load") or 0,
            "name": a.get("name") or "",
            "pace": (mt / dist) if dist > 0 else None,
            "gap_pace": pace_from_mps(gap),
            "zones": det.get("icu_hr_zone_times"),
        })
    runs.sort(key=lambda r: r["date"], reverse=True)

    cur = wel[-1] if wel else {}
    ctl = cur.get("ctl") or 0.0
    atl = cur.get("atl") or 0.0

    # denne uge, mandag til soendag
    monday = today - dt.timedelta(days=today.weekday())
    week = []
    for i in range(7):
        day = monday + dt.timedelta(days=i)
        ds = day.isoformat()
        planned = [e for e in events if str(e.get("start_date_local"))[:10] == ds
                   and e.get("category") == "WORKOUT"]
        done = [r for r in runs if r["date"] == ds]
        week.append({"date": ds, "dow": DOW_DK[i],
                     "planned": planned, "done": done, "future": day > today,
                     "today": day == today})

    week_km = sum(r["km"] for r in runs if monday.isoformat() <= r["date"] <= today.isoformat())
    week_done = sum(1 for w in week if w["done"])
    week_planned = sum(1 for w in week if w["planned"])

    # ugentlig volumen, 16 uger
    vol = defaultdict(float)
    for i in range(16):
        vol[(monday - dt.timedelta(weeks=15 - i)).isoformat()] = 0.0
    for r in runs:
        rd = dt.date.fromisoformat(r["date"])
        m = (rd - dt.timedelta(days=rd.weekday())).isoformat()
        if m in vol:
            vol[m] += r["km"]
    volume = [{"week": k, "km": v} for k, v in sorted(vol.items())]

    # CTL og ATL, 90 dage
    cutoff = (today - dt.timedelta(days=90)).isoformat()
    curve = [{"d": w["id"], "ctl": w.get("ctl") or 0, "atl": w.get("atl") or 0}
             for w in wel if str(w.get("id")) >= cutoff]

    # tempo ved aerob puls: rolige ture, puls 130-150, normaliseret til 140
    aer = []
    for r in runs:
        if not r["hr"] or not (130 <= r["hr"] <= 150):
            continue
        p = r["gap_pace"] or r["pace"]
        if not p or r["km"] < 2:
            continue
        # 0,6 sek/km per slag er en grov, lineaer normalisering. Groft, men konsistent.
        aer.append({"d": r["date"], "pace": p + (r["hr"] - 140) * 0.6, "raw": p, "hr": r["hr"]})
    aer.sort(key=lambda x: x["d"])

    # zonefordeling, 28 dage
    zc = [0] * 7
    zcut = (today - dt.timedelta(days=28)).isoformat()
    for r in runs:
        if r["date"] >= zcut and r["zones"]:
            for i, s in enumerate(r["zones"][:7]):
                zc[i] += s or 0
    ztot = sum(zc)

    upcoming = sorted(
        [e for e in events if str(e.get("start_date_local"))[:10] > today.isoformat()
         and e.get("category") == "WORKOUT"],
        key=lambda e: str(e.get("start_date_local")))[:8]

    # datakvalitet
    gaps = []
    if not any(w.get("restingHR") for w in wel[-30:]):
        gaps.append("Hvilepuls synkroniserer ikke fra Garmin. Vælg wellness-felter under "
                    "intervals.icu, Settings, Garmin.")
    if sum(1 for w in wel[-30:] if w.get("sleepSecs")) < 5:
        gaps.append("Søvndata mangler. Vivoactive 3 kan levere det, hvis wellness-sync er sat op.")
    if ztot and zc[0] / ztot > 0.95:
        gaps.append("Al løbetid ligger i intervals.icu zone 1. Bemærk at Garmin og "
                    "intervals.icu bruger forskellige zonemodeller: Garmin regner i procent "
                    "af maksimalpuls med fem zoner, intervals.icu i procent af tærskelpuls "
                    "med syv. Samme løb kan derfor hedde zone 2 på uret og zone 1 her. "
                    "Skriv puls i slag per minut i planens beskrivelser, så undgås "
                    "forvekslingen.")
    if ztot:
        gaps.append("Tærskelpulsen 177 i intervals.icu svarer til 90,8 procent af "
                    "maksimalpulsen 195 og ser dermed ud til at være afledt, ikke målt. "
                    "Alle zonegrænser hviler derfor på et estimat. En tærskeltest vil "
                    "forankre dem.")

    return {
        "today": today, "gen": gen, "days_to_race": (RACE - today).days,
        "ctl": ctl, "atl": atl, "form": ctl - atl,
        "week": week, "week_km": week_km, "week_done": week_done, "week_planned": week_planned,
        "volume": volume, "curve": curve, "aer": aer, "zones": zc, "ztot": ztot,
        "upcoming": upcoming, "runs": runs, "gaps": gaps,
        "km4": sum(v["km"] for v in volume[-4:]),
        "phase": next((e.get("name") for e in sorted(
            events, key=lambda e: str(e.get("start_date_local")), reverse=True)
            if str(e.get("start_date_local"))[:10] <= today.isoformat()
            and e.get("category") == "WORKOUT"),
            (upcoming[0].get("name") if upcoming else "")),
    }


# ------------------------------------------------------------------- diagrammer

def bars(volume, w=680, h=170):
    pad_l, pad_b, pad_t = 34, 26, 12
    iw, ih = w - pad_l - 8, h - pad_b - pad_t
    mx = max([v["km"] for v in volume] + [10])
    step = iw / max(len(volume), 1)
    bw = min(step * 0.62, 26)
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Ugentlig løbevolumen">']
    for frac in (0, 0.5, 1):
        y = pad_t + ih - ih * frac
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-8}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{pad_l-7}" y="{y+3.5:.1f}" class="ax ar">{mx*frac:.0f}</text>')
    for i, v in enumerate(volume):
        x = pad_l + step * i + (step - bw) / 2
        bh = ih * (v["km"] / mx) if mx else 0
        y = pad_t + ih - bh
        lab = dk_short(dt.date.fromisoformat(v["week"]))
        if v["km"] > 0:
            out.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(bh,2):.1f}" '
                       f'rx="4" class="bar"><title>Uge {lab}: {v["km"]:.1f} km</title></rect>')
        else:
            out.append(f'<rect x="{x:.1f}" y="{pad_t+ih-2:.1f}" width="{bw:.1f}" height="2" '
                       f'rx="1" class="bar0"><title>Uge {lab}: ingen løb</title></rect>')
        if i % 3 == 0 or i == len(volume) - 1:
            out.append(f'<text x="{x+bw/2:.1f}" y="{h-8}" class="ax am">{lab}</text>')
    out.append("</svg>")
    return "".join(out)


def curve_chart(curve, w=680, h=180):
    if len(curve) < 2:
        return '<p class="empty">Ikke nok belastningsdata endnu.</p>'
    pad_l, pad_b, pad_t = 34, 26, 12
    iw, ih = w - pad_l - 8, h - pad_b - pad_t
    mx = max([max(c["ctl"], c["atl"]) for c in curve] + [10])
    n = len(curve)
    X = lambda i: pad_l + iw * i / (n - 1)
    Y = lambda v: pad_t + ih - ih * (v / mx)
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Form og træthed">']
    for frac in (0, 0.5, 1):
        y = pad_t + ih - ih * frac
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-8}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{pad_l-7}" y="{y+3.5:.1f}" class="ax ar">{mx*frac:.0f}</text>')
    area = " ".join(f"{X(i):.1f},{Y(c['ctl']):.1f}" for i, c in enumerate(curve))
    out.append(f'<polygon points="{pad_l},{pad_t+ih} {area} {X(n-1):.1f},{pad_t+ih}" class="fill1"/>')
    out.append(f'<polyline points="{area}" class="ln1"/>')
    out.append('<polyline points="' + " ".join(f"{X(i):.1f},{Y(c['atl']):.1f}"
               for i, c in enumerate(curve)) + '" class="ln2"/>')
    last = curve[-1]
    out.append(f'<circle cx="{X(n-1):.1f}" cy="{Y(last["ctl"]):.1f}" r="4" class="dot1"/>')
    out.append(f'<circle cx="{X(n-1):.1f}" cy="{Y(last["atl"]):.1f}" r="4" class="dot2"/>')
    for i in (0, n // 2, n - 1):
        out.append(f'<text x="{X(i):.1f}" y="{h-8}" class="ax am">'
                   f'{dk_short(dt.date.fromisoformat(curve[i]["d"]))}</text>')
    out.append("</svg>")
    return "".join(out)


def aerobic_chart(aer, w=680, h=170):
    if len(aer) < 3:
        return ('<p class="empty">Kræver mindst tre rolige ture med puls mellem 130 og 150. '
                f'Der er {len(aer)} indtil videre.</p>')
    pad_l, pad_b, pad_t = 46, 26, 12
    iw, ih = w - pad_l - 8, h - pad_b - pad_t
    ps = [a["pace"] for a in aer]
    lo, hi = min(ps) - 15, max(ps) + 15
    d0 = dt.date.fromisoformat(aer[0]["d"]).toordinal()
    d1 = dt.date.fromisoformat(aer[-1]["d"]).toordinal()
    span = max(d1 - d0, 1)
    X = lambda s: pad_l + iw * (dt.date.fromisoformat(s).toordinal() - d0) / span
    Y = lambda p: pad_t + ih * (p - lo) / (hi - lo)
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Tempo ved puls 140">']
    for frac in (0, 0.5, 1):
        y = pad_t + ih * frac
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-8}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{pad_l-7}" y="{y+3.5:.1f}" class="ax ar">{mmss(lo+(hi-lo)*frac)}</text>')
    pts = " ".join(f"{X(a['d']):.1f},{Y(a['pace']):.1f}" for a in aer)
    out.append(f'<polyline points="{pts}" class="ln3"/>')
    for a in aer:
        out.append(f'<circle cx="{X(a["d"]):.1f}" cy="{Y(a["pace"]):.1f}" r="4.5" class="dot3">'
                   f'<title>{a["d"]}: {mmss(a["raw"])}/km ved puls {a["hr"]}</title></circle>')
    out.append(f'<text x="{pad_l}" y="{h-8}" class="ax">'
               f'{dk_short(dt.date.fromisoformat(aer[0]["d"]))}</text>')
    out.append(f'<text x="{w-8}" y="{h-8}" class="ax ar">'
               f'{dk_short(dt.date.fromisoformat(aer[-1]["d"]))}</text>')
    out.append("</svg>")
    return "".join(out)


# ------------------------------------------------------------------------- html

def render(m):
    wk = (m["days_to_race"] + 6) // 7
    goal_pace = mmss(GOAL_SECONDS / MARATHON_KM)
    form = m["form"]
    fcls = "good" if form > -5 else ("warn" if form > -15 else "crit")

    daycells = []
    for w in m["week"]:
        st, txt = "rest", "fri"
        if w["planned"] and w["done"]:
            st = "done"
            txt = f'{w["done"][0]["km"]:.1f} km'
        elif w["planned"] and w["future"]:
            st = "plan"
            txt = "planlagt"
        elif w["planned"]:
            st = "miss"
            txt = "mangler"
        elif w["done"]:
            st = "extra"
            txt = f'{w["done"][0]["km"]:.1f} km'
        daycells.append(
            f'<div class="day {st}{" now" if w["today"] else ""}">'
            f'<span class="dow">{w["dow"]}</span><span class="dtxt">{esc(txt)}</span></div>')

    up = []
    for e in m["upcoming"]:
        day = dt.date.fromisoformat(str(e.get("start_date_local"))[:10])
        up.append(f'<tr><td class="mono">{dk_day(day)}</td>'
                  f'<td>{esc(e.get("description") or e.get("name") or "")}</td></tr>')

    rows = []
    for r in m["runs"][:8]:
        day = dt.date.fromisoformat(r["date"])
        rows.append(
            f'<tr><td class="mono">{dk_short(day)}</td>'
            f'<td>{esc(r["name"][:26])}</td>'
            f'<td class="mono num">{r["km"]:.1f}</td>'
            f'<td class="mono num">{mmss(r["gap_pace"] or r["pace"])}</td>'
            f'<td class="mono num">{r["hr"] or "-"}</td>'
            f'<td class="mono num">{r["load"]:.0f}</td></tr>')

    zpct = ""
    if m["ztot"]:
        low = (m["zones"][0] + m["zones"][1]) / m["ztot"] * 100
        zpct = (f'<p class="note">Lav intensitet, altså puls under 158, udgør '
                f'<strong>{low:.0f} procent</strong> af løbetiden de sidste 28 dage. '
                f'Målet i en opbygningsfase ligger omkring 80.</p>')

    gaps = ""
    if m["gaps"]:
        gaps = ('<section class="card flags"><h2>Datakvalitet</h2><ul>'
                + "".join(f"<li>{esc(g)}</li>" for g in m["gaps"]) + "</ul></section>")

    return f"""<title>Vejen til København</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800&family=Public+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --bg:#F4F6F8; --surf:#FFFFFF; --line:#E1E6EB; --grid:#EDF0F3;
  --ink:#16202B; --ink2:#54616E; --ink3:#8B959F;
  --s1:#1B6FA8; --s2:#C46A10; --s3:#7B3F98;
  --good:#2F7D4F; --warn:#B0730F; --crit:#A83E36;
  --s1f:rgba(27,111,168,.13);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#0E141A; --surf:#171F27; --line:#28323C; --grid:#222B34;
    --ink:#E4EAF0; --ink2:#9AA6B2; --ink3:#6B7784;
    --s1:#3789C0; --s2:#CC7F28; --s3:#9C5FB6;
    --good:#4E9E6E; --warn:#C9902F; --crit:#C25B52;
    --s1f:rgba(55,137,192,.16);
  }}
}}
:root[data-theme="dark"] {{
  --bg:#0E141A; --surf:#171F27; --line:#28323C; --grid:#222B34;
  --ink:#E4EAF0; --ink2:#9AA6B2; --ink3:#6B7784;
  --s1:#3789C0; --s2:#CC7F28; --s3:#9C5FB6;
  --good:#4E9E6E; --warn:#C9902F; --crit:#C25B52;
  --s1f:rgba(55,137,192,.16);
}}
* {{ box-sizing:border-box; }}
body {{
  margin:0; background:var(--bg); color:var(--ink);
  font-family:"Public Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
  font-size:15px; line-height:1.55; -webkit-font-smoothing:antialiased;
}}
.wrap {{ max-width:920px; margin:0 auto; padding:32px 20px 64px; display:flex; flex-direction:column; gap:20px; }}
.mono {{ font-family:"IBM Plex Mono",ui-monospace,monospace; font-variant-numeric:tabular-nums; }}
.num {{ text-align:right; }}
h1 {{ font-family:Archivo,sans-serif; font-weight:800; font-size:clamp(26px,4.4vw,38px);
      letter-spacing:-.022em; margin:0; text-wrap:balance; }}
h2 {{ font-family:Archivo,sans-serif; font-weight:700; font-size:13px; letter-spacing:.09em;
      text-transform:uppercase; color:var(--ink3); margin:0 0 14px; }}
.card {{ background:var(--surf); border:1px solid var(--line); border-radius:12px; padding:20px 22px; }}
header .eyebrow {{ font-family:"IBM Plex Mono",monospace; font-size:12px; letter-spacing:.1em;
      text-transform:uppercase; color:var(--ink3); margin:0 0 6px; }}
header p.sub {{ color:var(--ink2); margin:8px 0 0; max-width:62ch; }}
.stats {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:14px; }}
.tile {{ background:var(--surf); border:1px solid var(--line); border-radius:12px; padding:16px 18px; }}
.tile .k {{ font-size:12px; letter-spacing:.05em; text-transform:uppercase; color:var(--ink3); }}
.tile .v {{ font-family:Archivo,sans-serif; font-weight:800; font-size:32px; letter-spacing:-.02em;
      font-variant-numeric:tabular-nums; line-height:1.15; margin-top:2px; }}
.tile .u {{ font-size:13px; color:var(--ink2); }}
.v.good {{ color:var(--good); }} .v.warn {{ color:var(--warn); }} .v.crit {{ color:var(--crit); }}
.week {{ display:grid; grid-template-columns:repeat(7,1fr); gap:7px; }}
.day {{ border-radius:9px; padding:10px 6px; text-align:center; border:1px solid var(--line);
      background:var(--surf); }}
.day .dow {{ display:block; font-size:11px; letter-spacing:.07em; text-transform:uppercase; color:var(--ink3); }}
.day .dtxt {{ display:block; font-family:"IBM Plex Mono",monospace; font-size:12px; margin-top:3px; color:var(--ink2); }}
.day.done {{ border-color:var(--good); box-shadow:inset 0 -3px 0 var(--good); }}
.day.done .dtxt {{ color:var(--ink); }}
.day.miss {{ border-color:var(--crit); box-shadow:inset 0 -3px 0 var(--crit); }}
.day.miss .dtxt {{ color:var(--crit); }}
.day.plan {{ border-style:dashed; }}
.day.extra {{ box-shadow:inset 0 -3px 0 var(--s3); }}
.day.now {{ outline:2px solid var(--s1); outline-offset:1px; }}
.chart {{ width:100%; height:auto; display:block; overflow:visible; }}
.grid {{ stroke:var(--grid); stroke-width:1; }}
.ax {{ font-family:"IBM Plex Mono",monospace; font-size:10px; fill:var(--ink3); }}
.ar {{ text-anchor:end; }} .am {{ text-anchor:middle; }}
.bar {{ fill:var(--s1); }} .bar0 {{ fill:var(--line); }}
.ln1 {{ fill:none; stroke:var(--s1); stroke-width:2; stroke-linejoin:round; }}
.ln2 {{ fill:none; stroke:var(--s2); stroke-width:2; stroke-dasharray:4 3; stroke-linejoin:round; }}
.ln3 {{ fill:none; stroke:var(--s3); stroke-width:2; stroke-linejoin:round; }}
.fill1 {{ fill:var(--s1f); }}
.dot1 {{ fill:var(--s1); stroke:var(--surf); stroke-width:2; }}
.dot2 {{ fill:var(--s2); stroke:var(--surf); stroke-width:2; }}
.dot3 {{ fill:var(--s3); stroke:var(--surf); stroke-width:2; }}
.legend {{ display:flex; gap:18px; flex-wrap:wrap; margin-top:10px; font-size:13px; color:var(--ink2); }}
.legend i {{ display:inline-block; width:14px; height:3px; border-radius:2px; margin-right:6px;
      vertical-align:middle; }}
table {{ width:100%; border-collapse:collapse; font-size:14px; }}
th, td {{ text-align:left; padding:7px 8px; border-bottom:1px solid var(--line); }}
th {{ font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--ink3); font-weight:600; }}
th.num {{ text-align:right; }}
tbody tr:last-child td {{ border-bottom:none; }}
.tw {{ overflow-x:auto; }}
.note {{ color:var(--ink2); font-size:14px; margin:12px 0 0; }}
.empty {{ color:var(--ink3); font-size:14px; font-style:italic; margin:6px 0; }}
.flags ul {{ margin:0; padding-left:18px; color:var(--ink2); }}
.flags li {{ margin-bottom:6px; }}
.flags {{ border-left:3px solid var(--warn); }}
footer {{ color:var(--ink3); font-size:12.5px; text-align:center; }}
@media (max-width:620px) {{
  .week {{ grid-template-columns:repeat(4,1fr); }}
  .wrap {{ padding:22px 14px 48px; }}
}}
</style>

<div class="wrap">
  <header>
    <p class="eyebrow">{esc(RACE_NAME)} · 9. maj 2027</p>
    <h1>{wk} uger til start</h1>
    <p class="sub">Måltid 3:45:00, svarende til {goal_pace}/km.
      {("Aktuel fase: " + esc(m["phase"]) + ".") if m["phase"] else ""}
      Data hentet {esc(m["gen"])}.</p>
  </header>

  <div class="stats">
    <div class="tile"><div class="k">Form</div>
      <div class="v {fcls} mono">{form:+.0f}</div><div class="u">CTL {m['ctl']:.1f} · ATL {m['atl']:.1f}</div></div>
    <div class="tile"><div class="k">Denne uge</div>
      <div class="v mono">{m['week_km']:.1f}</div><div class="u">km løbet</div></div>
    <div class="tile"><div class="k">Pas</div>
      <div class="v mono">{m['week_done']}/{m['week_planned']}</div><div class="u">gennemført mod planlagt</div></div>
    <div class="tile"><div class="k">4 uger</div>
      <div class="v mono">{m['km4']:.0f}</div><div class="u">km, rullende</div></div>
  </div>

  <section class="card">
    <h2>Ugens plan</h2>
    <div class="week">{"".join(daycells)}</div>
  </section>

  <section class="card">
    <h2>Ugentlig løbevolumen, 16 uger</h2>
    {bars(m["volume"])}
    <p class="note">Tomme uger vises som en flad streg. De er en del af historikken, ikke et hul i data.</p>
  </section>

  <section class="card">
    <h2>Grundform og træthed, 90 dage</h2>
    {curve_chart(m["curve"])}
    <div class="legend"><span><i style="background:var(--s1)"></i>CTL, grundform</span>
      <span><i style="background:var(--s2)"></i>ATL, træthed</span></div>
  </section>

  <section class="card">
    <h2>Tempo ved puls 140</h2>
    {aerobic_chart(m["aer"])}
    <p class="note">Hurtigst ligger øverst, så fremgang er en kurve der bevæger sig opad.
      Tempoet er grade adjusted og normaliseret til puls 140. Markøren siger mere om aerob
      kapacitet end noget andet enkelt tal, men kræver flere uger med rolige ture, før den
      betyder noget.</p>
    {zpct}
  </section>

  <section class="card">
    <h2>Seneste løb</h2>
    <div class="tw"><table>
      <thead><tr><th>Dato</th><th>Navn</th><th class="num">Km</th><th class="num">GAP</th>
        <th class="num">Puls</th><th class="num">Load</th></tr></thead>
      <tbody>{"".join(rows) or '<tr><td colspan="6" class="empty">Ingen løb registreret.</td></tr>'}</tbody>
    </table></div>
  </section>

  <section class="card">
    <h2>Kommende pas</h2>
    <div class="tw"><table><tbody>{"".join(up) or '<tr><td class="empty">Ingen planlagte pas.</td></tr>'}</tbody></table></div>
  </section>

  {gaps}

  <footer>Bygget af de planlagte Claude-opgaver ud fra intervals.icu. Opdateres dagligt.</footer>
</div>
"""


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "payload.json"
    dst = sys.argv[2] if len(sys.argv) > 2 else "dashboard.html"
    m = compute(load(src))
    with open(dst, "w", encoding="utf-8") as f:
        f.write(render(m))
    print(f"skrev {dst} ({len(open(dst, encoding='utf-8').read())} tegn), "
          f"{m['days_to_race']} dage til løbet")


if __name__ == "__main__":
    main()
