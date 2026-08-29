#!/usr/bin/env python3
"""Bygger dashboard.html ud fra en dekrypteret payload.json.

Brug:  python3 scripts/build_dashboard.py payload.json dashboard.html

Outputtet er indhold til Artifact-vaerktoejet: ingen doctype, html, head eller body.
Alt CSS og JS er inline. Ingen eksterne kald ud over Google Fonts.

Version 2, 29-08-2026. Omlagt fra resume-dashboard til analyse-dashboard efter
Andreas' feedback: han kender allerede sit volumen og sin frekvens, han vil vide
om belastningen er lovende, for meget eller for lidt, om han holder planen, hvordan
formen udvikler sig i forhold til det planen selv lægger op til, og et VO2 maks-estimat.
Zonemodel er låst til Garmins Z2 = 118-138 (Andreas' beslutning 29-08-2026), se
docs/analysemetode.md. Byg ikke "zone 2 er tvetydig"-logik ind her igen.
"""

import datetime as dt
import html
import json
import math
import re
import sys
from collections import defaultdict

RACE = dt.date(2027, 5, 9)
RACE_NAME = "Copenhagen Marathon"
GOAL_SECONDS = 3 * 3600 + 45 * 60
MARATHON_KM = 42.195
PLAN_START = dt.date(2026, 8, 25)

# Aftalt zonemodel, se docs/analysemetode.md. Ikke tvetydig, indsæt ikke Aerobic 149-158
# som et alternativ i denne fil.
Z2_LOW, Z2_HIGH = 118, 138

# Guardrails fra metode.md, praktikerheuristikker, ikke stærk evidens. Se referencer der.
CTL_RAMP_CEIL = 7.0     # point/uge, øvre grænse før det flages
CTL_RAMP_WARN = 5.0     # point/uge, hvor "i den høje ende" begynder
ACWR_LOW, ACWR_HIGH = 0.8, 1.3

DOW_DK = ["man", "tir", "ons", "tor", "fre", "lør", "søn"]


def esc(s):
    return html.escape(str(s), quote=True)


def dk_day(d):
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


def parse_minutes(desc):
    if not desc:
        return None
    m = re.search(r"(\d+)\s*min", desc)
    return int(m.group(1)) if m else None


def daniels_gilbert_vo2max(distance_m, time_s):
    """VO2 maks-estimat fra en enkelt indsats. Daniels J, Gilbert J. Oxygen Power:
    Performance Tables for Distance Runners. 1979. Formlen antager at indsatsen er
    tæt på maksimal for varigheden. Brugt på et almindeligt træningsløb undervurderer
    den reelle VO2 maks, fordi effekten ikke var maksimal. Se dashboardets egen
    brødtekst for det forbehold, det gentages ikke i outputtet af denne funktion."""
    t = time_s / 60.0
    if t <= 0 or distance_m <= 0:
        return None
    v = distance_m / t  # meter per minut
    pct_vo2max = (0.8 + 0.1894393 * math.exp(-0.012778 * t)
                  + 0.2989558 * math.exp(-0.1932605 * t))
    vo2 = -4.60 + 0.182258 * v + 0.000104 * v * v
    if vo2 <= 0 or pct_vo2max <= 0:
        return None
    return vo2 / pct_vo2max


# ---------------------------------------------------------------- beregninger

def compute(d):
    gen = d.get("generated_date") or dt.date.today().isoformat()
    today = dt.date.fromisoformat(gen)
    acts = d.get("activities") or []
    events = d.get("events") or []
    wel = sorted((d.get("wellness") or []), key=lambda x: str(x.get("id")))
    detail = {a.get("id"): a for a in (d.get("recent_activity_detail") or [])}
    wel_by_date = {str(w.get("id")): w for w in wel}

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
            "dist_m": a.get("distance") or 0,
            "sec": mt,
            "hr": a.get("average_heartrate"),
            "load": a.get("icu_training_load") or 0,
            "name": a.get("name") or "",
            "pace": (mt / dist) if dist > 0 else None,
            "gap_pace": pace_from_mps(gap),
            "zones": det.get("icu_hr_zone_times"),
        })
    runs.sort(key=lambda r: r["date"], reverse=True)
    runs_by_date = defaultdict(list)
    for r in runs:
        runs_by_date[r["date"]].append(r)

    cur = wel[-1] if wel else {}
    ctl = cur.get("ctl") or 0.0
    atl = cur.get("atl") or 0.0

    # ---- belastningsvurdering: ramp og ACWR -------------------------------
    def wel_on(date_iso):
        return wel_by_date.get(date_iso)

    w7 = wel_on((today - dt.timedelta(days=7)).isoformat())
    ramp7 = (ctl - w7["ctl"]) if (w7 and w7.get("ctl") is not None) else None

    def load_sum(days):
        cutoff = (today - dt.timedelta(days=days - 1)).isoformat()
        return sum(r["load"] for r in runs if r["date"] >= cutoff)

    load7, load28 = load_sum(7), load_sum(28)
    acwr = (load7 / (load28 / 4)) if load28 else None
    days_since_restart = (today - PLAN_START).days + 1

    if days_since_restart < 14:
        load_verdict = ("for_tidligt",
            f"Kun {days_since_restart} dage siden genstart 25-08-2026. For kort til en "
            "robust vurdering, tallene vises alligevel til orientering.")
    elif ramp7 is None:
        load_verdict = ("ukendt", "Mangler CTL fra 7 dage siden, kan ikke vurdere ramp.")
    elif ramp7 > CTL_RAMP_CEIL:
        load_verdict = ("for_meget",
            f"CTL steg {ramp7:.1f} point den seneste uge, over guardrail-grænsen på "
            f"{CTL_RAMP_CEIL:.0f}. Hold øje med tegn på for hurtig opbygning.")
    elif ramp7 >= CTL_RAMP_WARN:
        load_verdict = ("i_top",
            f"CTL steg {ramp7:.1f} point den seneste uge, i den høje ende af det "
            f"anbefalede interval ({CTL_RAMP_WARN:.0f} til {CTL_RAMP_CEIL:.0f}).")
    elif ramp7 > 0:
        load_verdict = ("passende",
            f"CTL steg {ramp7:.1f} point den seneste uge. Forsigtig, holdbar opbygning.")
    else:
        load_verdict = ("faldende",
            f"CTL faldt eller stod stille den seneste uge ({ramp7:.1f} point). "
            "Forventeligt ved hviledage eller lavt volumen, værd at følge hvis det "
            "fortsætter flere uger i træk.")

    # ---- planoverholdelse siden genstart -----------------------------------
    plan_events = sorted(
        [e for e in events if e.get("category") == "WORKOUT"
         and str(e.get("start_date_local"))[:10] >= PLAN_START.isoformat()],
        key=lambda e: str(e.get("start_date_local")))

    due = [e for e in plan_events if str(e.get("start_date_local"))[:10] <= today.isoformat()]
    future = [e for e in plan_events if str(e.get("start_date_local"))[:10] > today.isoformat()]

    adherence_rows = []
    done_count = planned_minutes = actual_minutes = 0
    for e in due:
        ds = str(e.get("start_date_local"))[:10]
        pm = parse_minutes(e.get("description")) or 0
        planned_minutes += pm
        day_runs = runs_by_date.get(ds, [])
        am = round(sum(r["sec"] for r in day_runs) / 60.0)
        actual_minutes += am
        hit = bool(day_runs)
        done_count += 1 if hit else 0
        adherence_rows.append({
            "date": ds, "planned_min": pm, "actual_min": am, "done": hit,
            "desc": e.get("description") or "",
        })
    adherence_pct = (done_count / len(due) * 100) if due else None
    minutes_pct = (actual_minutes / planned_minutes * 100) if planned_minutes else None

    # ---- form-simulation: hvis planen følges 1:1, fremad til sidst kendte pas
    recent_ratios = []
    for e in due[-6:]:
        ds = e_ds = str(e.get("start_date_local"))[:10]
        for r in runs_by_date.get(ds, []):
            if r["sec"] and r["load"]:
                recent_ratios.append(r["load"] / (r["sec"] / 60.0))
    load_per_min = (sum(recent_ratios) / len(recent_ratios)) if recent_ratios else 0.6
    n_ratio_samples = len(recent_ratios)

    sim = []
    if future:
        sim_ctl, sim_atl = ctl, atl
        last_future = dt.date.fromisoformat(str(future[-1].get("start_date_local"))[:10])
        by_day_minutes = defaultdict(int)
        for e in future:
            by_day_minutes[str(e.get("start_date_local"))[:10]] += parse_minutes(e.get("description")) or 0
        d = today
        while d <= last_future:
            ds = d.isoformat()
            day_load = by_day_minutes.get(ds, 0) * load_per_min
            sim_ctl = sim_ctl + (day_load - sim_ctl) / 42.0
            sim_atl = sim_atl + (day_load - sim_atl) / 7.0
            sim.append({"d": ds, "ctl": sim_ctl, "atl": sim_atl})
            d += dt.timedelta(days=1)

    # ---- CTL/ATL kurve, 90 dage --------------------------------------------
    cutoff = (today - dt.timedelta(days=90)).isoformat()
    curve = [{"d": w["id"], "ctl": w.get("ctl") or 0, "atl": w.get("atl") or 0}
             for w in wel if str(w.get("id")) >= cutoff]

    # ---- tempo ved aerob puls, normaliseret til 140 ------------------------
    aer = []
    for r in runs:
        if not r["hr"] or not (130 <= r["hr"] <= 150):
            continue
        p = r["gap_pace"] or r["pace"]
        if not p or r["km"] < 2:
            continue
        aer.append({"d": r["date"], "pace": p + (r["hr"] - 140) * 0.6, "raw": p, "hr": r["hr"]})
    aer.sort(key=lambda x: x["d"])

    # ---- intensitetsfordeling: andel af tid med snitpuls under 138 ---------
    # icu_hr_zone_times er bundet til intervals.icu's egne grænser (149, 158, ...),
    # ikke til den besluttede 118-138-grænse, og bruges derfor ikke her. I stedet
    # klassificeres hvert løb som helhed ud fra dets gennemsnitspuls. Det er en grov
    # tilnærmelse, en tur med opvarmning og stryk ville blive fejlklassificeret, men
    # der er endnu ingen sådanne pas i planen. Se docs/analysemetode.md.
    lowcut = (today - dt.timedelta(days=28)).isoformat()
    low_sec = high_sec = 0
    for r in runs:
        if r["date"] < lowcut or not r["hr"] or not r["sec"]:
            continue
        if r["hr"] < Z2_HIGH:
            low_sec += r["sec"]
        else:
            high_sec += r["sec"]
    intensity_total = low_sec + high_sec
    low_pct = (low_sec / intensity_total * 100) if intensity_total else None

    # ---- VO2 maks-estimat ---------------------------------------------------
    vo2_candidates = []
    for a in acts:
        if a.get("type") not in ("Run", "VirtualRun", "TrailRun"):
            continue
        dist = a.get("distance") or 0
        t = a.get("moving_time") or 0
        if dist < 1000 or t < 480:
            continue
        est = daniels_gilbert_vo2max(dist, t)
        if est:
            vo2_candidates.append({
                "date": (a.get("start_date_local") or "")[:10],
                "km": dist / 1000.0, "min": t / 60.0,
                "hr": a.get("average_heartrate"), "max_hr": a.get("max_heartrate"),
                "vo2max": est,
            })
    vo2_best = max(vo2_candidates, key=lambda x: x["vo2max"]) if vo2_candidates else None
    vo2_stale_days = (today - dt.date.fromisoformat(vo2_best["date"])).days if vo2_best else None

    upcoming = sorted(
        [e for e in events if str(e.get("start_date_local"))[:10] > today.isoformat()
         and e.get("category") == "WORKOUT"],
        key=lambda e: str(e.get("start_date_local")))[:8]

    # ---- datakvalitet ---------------------------------------------------------
    gaps = []
    if not any(w.get("restingHR") for w in wel[-30:]):
        gaps.append("Hvilepuls synkroniserer ikke fra Garmin. Vælg wellness-felter under "
                    "intervals.icu, Settings, Garmin, eller overvej en Oura-integration.")
    if sum(1 for w in wel[-30:] if w.get("sleepSecs")) < 5:
        gaps.append("Søvndata mangler stort set helt i wellness.")
    if n_ratio_samples < 5:
        gaps.append(f"Belastning per minut til fremskrivningen bygger på kun "
                    f"{n_ratio_samples} pas. Usikkert, opdateres efterhånden som flere "
                    "pas gennemføres.")
    if vo2_best and vo2_stale_days and vo2_stale_days > 45:
        gaps.append(f"VO2 maks-estimatet er {vo2_stale_days} dage gammelt og formentlig "
                    "ikke retvisende for den aktuelle form.")

    return {
        "today": today, "gen": gen, "days_to_race": (RACE - today).days,
        "ctl": ctl, "atl": atl, "form": ctl - atl,
        "ramp7": ramp7, "acwr": acwr, "load_verdict": load_verdict,
        "days_since_restart": days_since_restart,
        "adherence_rows": adherence_rows, "adherence_pct": adherence_pct,
        "minutes_pct": minutes_pct, "planned_minutes": planned_minutes,
        "actual_minutes": actual_minutes, "done_count": done_count,
        "due_count": len(due), "load_per_min": load_per_min,
        "n_ratio_samples": n_ratio_samples,
        "curve": curve, "sim": sim, "aer": aer,
        "low_pct": low_pct, "intensity_total": intensity_total,
        "vo2_best": vo2_best, "vo2_stale_days": vo2_stale_days,
        "upcoming": upcoming, "runs": runs, "gaps": gaps,
        "phase": next((e.get("name") for e in sorted(
            events, key=lambda e: str(e.get("start_date_local")), reverse=True)
            if str(e.get("start_date_local"))[:10] <= today.isoformat()
            and e.get("category") == "WORKOUT"),
            (upcoming[0].get("name") if upcoming else "")),
    }


# ------------------------------------------------------------------- diagrammer

def curve_chart(curve, sim, w=680, h=190):
    if len(curve) < 2:
        return '<p class="empty">Ikke nok belastningsdata endnu.</p>'
    pad_l, pad_b, pad_t = 34, 26, 12
    iw, ih = w - pad_l - 8, h - pad_b - pad_t
    all_vals = [max(c["ctl"], c["atl"]) for c in curve] + [s["ctl"] for s in sim] + [10]
    mx = max(all_vals)
    n = len(curve)
    d0 = dt.date.fromisoformat(curve[0]["d"]).toordinal()
    d1_ord = dt.date.fromisoformat((sim[-1]["d"] if sim else curve[-1]["d"])).toordinal()
    span = max(d1_ord - d0, 1)
    X = lambda ds: pad_l + iw * (dt.date.fromisoformat(ds).toordinal() - d0) / span
    Y = lambda v: pad_t + ih - ih * (v / mx)
    out = [f'<svg viewBox="0 0 {w} {h}" class="chart" role="img" aria-label="Form og træthed">']
    for frac in (0, 0.5, 1):
        y = pad_t + ih - ih * frac
        out.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{w-8}" y2="{y:.1f}" class="grid"/>')
        out.append(f'<text x="{pad_l-7}" y="{y+3.5:.1f}" class="ax ar">{mx*frac:.0f}</text>')
    area = " ".join(f"{X(c['d']):.1f},{Y(c['ctl']):.1f}" for c in curve)
    out.append(f'<polygon points="{X(curve[0]["d"]):.1f},{pad_t+ih} {area} '
               f'{X(curve[-1]["d"]):.1f},{pad_t+ih}" class="fill1"/>')
    out.append(f'<polyline points="{area}" class="ln1"/>')
    out.append('<polyline points="' + " ".join(f"{X(c['d']):.1f},{Y(c['atl']):.1f}"
               for c in curve) + '" class="ln2"/>')
    if sim:
        bridge = [f"{X(curve[-1]['d']):.1f},{Y(curve[-1]['ctl']):.1f}"]
        bridge += [f"{X(s['d']):.1f},{Y(s['ctl']):.1f}" for s in sim]
        out.append('<polyline points="' + " ".join(bridge) + '" class="ln4"/>')
    last = curve[-1]
    out.append(f'<circle cx="{X(last["d"]):.1f}" cy="{Y(last["ctl"]):.1f}" r="4" class="dot1"/>')
    out.append(f'<circle cx="{X(last["d"]):.1f}" cy="{Y(last["atl"]):.1f}" r="4" class="dot2"/>')
    labels = [curve[0]["d"], curve[-1]["d"]]
    if sim:
        labels.append(sim[-1]["d"])
    for ds in labels:
        out.append(f'<text x="{X(ds):.1f}" y="{h-8}" class="ax am">'
                   f'{dk_short(dt.date.fromisoformat(ds))}</text>')
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

VERDICT_LABEL = {
    "for_tidligt": ("warn", "For tidligt at vurdere"),
    "ukendt": ("warn", "Ukendt"),
    "for_meget": ("crit", "Hurtigere end guardrail"),
    "i_top": ("warn", "I den høje ende"),
    "passende": ("good", "Forsigtig opbygning"),
    "faldende": ("warn", "Faldende eller flad"),
}


def render(m):
    wk = (m["days_to_race"] + 6) // 7
    goal_pace = mmss(GOAL_SECONDS / MARATHON_KM)
    form = m["form"]
    fcls = "good" if form > -5 else ("warn" if form > -15 else "crit")

    vcls, vlabel = VERDICT_LABEL.get(m["load_verdict"][0], ("warn", "?"))
    ramp_txt = f'{m["ramp7"]:+.1f}' if m["ramp7"] is not None else "-"
    acwr_txt = f'{m["acwr"]:.2f}' if m["acwr"] is not None else "-"

    adh_rows = []
    for r in m["adherence_rows"][-10:]:
        day = dt.date.fromisoformat(r["date"])
        cls = "done" if r["done"] else "miss"
        adh_rows.append(
            f'<tr class="{cls}"><td class="mono">{dk_day(day)}</td>'
            f'<td>{esc(r["desc"][:40])}</td>'
            f'<td class="mono num">{r["planned_min"]}</td>'
            f'<td class="mono num">{r["actual_min"] or "-"}</td>'
            f'<td>{"gennemført" if r["done"] else "mangler"}</td></tr>')

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

    intensity_note = ""
    if m["low_pct"] is not None:
        intensity_note = (f'<p class="note">Andel af løbetid med snitpuls under {Z2_HIGH} '
                          f'(zone 2-loftet) de sidste 28 dage: <strong>{m["low_pct"]:.0f} '
                          f'procent</strong> af {m["intensity_total"]/60:.0f} minutter. '
                          f'Beregnet per løb, ikke per omgang, se datakvalitet.</p>')

    vo2_card = ""
    if m["vo2_best"]:
        v = m["vo2_best"]
        vday = dt.date.fromisoformat(v["date"])
        vo2_card = f"""
  <section class="card">
    <h2>VO2 maks-estimat</h2>
    <div class="stats">
      <div class="tile"><div class="k">Bedste skøn</div>
        <div class="v mono">{v['vo2max']:.0f}</div><div class="u">ml/kg/min</div></div>
      <div class="tile"><div class="k">Kilde</div>
        <div class="v mono" style="font-size:20px">{dk_day(vday)}</div>
        <div class="u">{v['km']:.1f} km, {v['min']:.0f} min, puls {v['hr'] or '-'}</div></div>
      <div class="tile"><div class="k">Alder</div>
        <div class="v mono">{m['vo2_stale_days']}</div><div class="u">dage gammelt</div></div>
    </div>
    <p class="note">Estimeret med Daniels og Gilberts formel (Oxygen Power, 1979) ud fra det
      hårdeste løb i historikken, ikke en reel tidsmåling. Formlen forudsætter en indsats tæt
      på maksimal for varigheden. Alle rolige ture i genstartsfasen er bevidst lette og kan
      ikke bruges til dette, så tallet er ikke opdateret med aktuel form og formentlig for
      lavt hvis den seneste indsats ligger langt tilbage. Brug det som et løst referencepunkt,
      ikke som et mål for fremgang. En rigtig test, for eksempel en 5 eller 10 km for fuld
      indsats eller en 30-minutters tempotest, vil give et pålideligt tal.</p>
  </section>"""

    gaps = ""
    if m["gaps"]:
        gaps = ('<section class="card flags"><h2>Datakvalitet</h2><ul>'
                + "".join(f"<li>{esc(g)}</li>" for g in m["gaps"]) + "</ul></section>")

    sim_legend = ('<span><i style="background:var(--s4)"></i>reference, hvis planen '
                  'følges 1:1</span>') if m["sim"] else ""

    return f"""<title>Vejen til København</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;700;800&family=Public+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {{
  --bg:#F4F6F8; --surf:#FFFFFF; --line:#E1E6EB; --grid:#EDF0F3;
  --ink:#16202B; --ink2:#54616E; --ink3:#8B959F;
  --s1:#1B6FA8; --s2:#C46A10; --s3:#7B3F98; --s4:#8B959F;
  --good:#2F7D4F; --warn:#B0730F; --crit:#A83E36;
  --s1f:rgba(27,111,168,.13);
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --bg:#0E141A; --surf:#171F27; --line:#28323C; --grid:#222B34;
    --ink:#E4EAF0; --ink2:#9AA6B2; --ink3:#6B7784;
    --s1:#3789C0; --s2:#CC7F28; --s3:#9C5FB6; --s4:#6B7784;
    --good:#4E9E6E; --warn:#C9902F; --crit:#C25B52;
    --s1f:rgba(55,137,192,.16);
  }}
}}
:root[data-theme="dark"] {{
  --bg:#0E141A; --surf:#171F27; --line:#28323C; --grid:#222B34;
  --ink:#E4EAF0; --ink2:#9AA6B2; --ink3:#6B7784;
  --s1:#3789C0; --s2:#CC7F28; --s3:#9C5FB6; --s4:#6B7784;
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
.verdict {{ margin-top:14px; padding:12px 14px; border-radius:10px; border:1px solid var(--line);
      font-size:14px; }}
.verdict.good {{ border-color:var(--good); }} .verdict.warn {{ border-color:var(--warn); }}
.verdict.crit {{ border-color:var(--crit); }}
.verdict b {{ display:block; font-family:Archivo,sans-serif; font-weight:700; margin-bottom:3px; }}
.chart {{ width:100%; height:auto; display:block; overflow:visible; }}
.grid {{ stroke:var(--grid); stroke-width:1; }}
.ax {{ font-family:"IBM Plex Mono",monospace; font-size:10px; fill:var(--ink3); }}
.ar {{ text-anchor:end; }} .am {{ text-anchor:middle; }}
.ln1 {{ fill:none; stroke:var(--s1); stroke-width:2; stroke-linejoin:round; }}
.ln2 {{ fill:none; stroke:var(--s2); stroke-width:2; stroke-dasharray:4 3; stroke-linejoin:round; }}
.ln3 {{ fill:none; stroke:var(--s3); stroke-width:2; stroke-linejoin:round; }}
.ln4 {{ fill:none; stroke:var(--s4); stroke-width:2; stroke-dasharray:2 3; stroke-linejoin:round; }}
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
tr.miss td:first-child {{ color:var(--crit); }}
.tw {{ overflow-x:auto; }}
.note {{ color:var(--ink2); font-size:14px; margin:12px 0 0; }}
.empty {{ color:var(--ink3); font-size:14px; font-style:italic; margin:6px 0; }}
.flags ul {{ margin:0; padding-left:18px; color:var(--ink2); }}
.flags li {{ margin-bottom:6px; }}
.flags {{ border-left:3px solid var(--warn); }}
footer {{ color:var(--ink3); font-size:12.5px; text-align:center; }}
@media (max-width:620px) {{
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

  <section class="card">
    <h2>Belastningsvurdering</h2>
    <div class="stats">
      <div class="tile"><div class="k">Form</div>
        <div class="v {fcls} mono">{form:+.0f}</div><div class="u">CTL {m['ctl']:.1f} · ATL {m['atl']:.1f}</div></div>
      <div class="tile"><div class="k">CTL, seneste uge</div>
        <div class="v mono">{ramp_txt}</div><div class="u">point ramp</div></div>
      <div class="tile"><div class="k">Akut/kronisk</div>
        <div class="v mono">{acwr_txt}</div><div class="u">7d ift. 28d/4, mål 0,8-1,3</div></div>
    </div>
    <div class="verdict {vcls}"><b>{vlabel}</b>{esc(m["load_verdict"][1])}</div>
  </section>

  <section class="card">
    <h2>Planoverholdelse siden genstart, 25-08-2026</h2>
    <div class="stats">
      <div class="tile"><div class="k">Pas</div>
        <div class="v mono">{m['done_count']}/{m['due_count']}</div>
        <div class="u">{(m['adherence_pct'] or 0):.0f} procent gennemført</div></div>
      <div class="tile"><div class="k">Minutter</div>
        <div class="v mono">{m['actual_minutes']}/{m['planned_minutes']}</div>
        <div class="u">{(m['minutes_pct'] or 0):.0f} procent af planlagt tid</div></div>
    </div>
    <div class="tw"><table>
      <thead><tr><th>Dato</th><th>Ordination</th><th class="num">Planlagt min</th>
        <th class="num">Udført min</th><th>Status</th></tr></thead>
      <tbody>{"".join(adh_rows) or '<tr><td colspan="5" class="empty">Ingen pas forfaldet endnu.</td></tr>'}</tbody>
    </table></div>
  </section>

  <section class="card">
    <h2>Formudvikling, 90 dage</h2>
    {curve_chart(m["curve"], m["sim"])}
    <div class="legend"><span><i style="background:var(--s1)"></i>CTL, grundform</span>
      <span><i style="background:var(--s2)"></i>ATL, træthed</span>{sim_legend}</div>
    <p class="note">Den stiplede grå linje er ikke en prognose for racedagen. Den viser hvad
      CTL ville blive, hvis alle planlagte pas frem til {dk_day(dt.date.fromisoformat(m['sim'][-1]['d']))
      if m['sim'] else 'sidst kendte pas'} gennemføres præcis som foreskrevet, ud fra dit eget
      observerede forhold mellem belastning og varighed på {m['n_ratio_samples']} rolige pas.
      Det rækker kun til den del af planen der allerede er hentet, ikke til racedagen 256 dage
      ude, og det er en fremskrivning af egne tal, ikke en valideret model.</p>
  </section>

  <section class="card">
    <h2>Tempo ved puls 140</h2>
    {aerobic_chart(m["aer"])}
    <p class="note">Hurtigst ligger øverst, så fremgang er en kurve der bevæger sig opad.
      Tempoet er grade adjusted og normaliseret til puls 140. Kræver flere uger med rolige
      ture, før trenden betyder noget.</p>
    {intensity_note}
  </section>
  {vo2_card}

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
