#!/usr/bin/env python3
"""Henter traeningsdata fra intervals.icu og skriver en samlet payload.

Koerer paa GitHub Actions (ubuntu-latest, ingen eksterne pip-afhaengigheder).

Output:
  build/payload.json.gz  - fuld data, krypteres af workflowet bagefter
  data/status.json       - diagnostik UDEN persondata, committes i klartekst

status.json indeholder kun HTTP-koder, antal records, og feltnavne.
Ingen datoer, distancer, pulstal, positioner eller navne.
"""

import base64
import datetime as dt
import gzip
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

API = os.environ.get("INTERVALS_API_BASE", "https://intervals.icu/api/v1")
KEY = os.environ.get("INTERVALS_API_KEY", "").strip()
ATHLETE = os.environ.get("INTERVALS_ATHLETE_ID", "").strip()

if not KEY or not ATHLETE:
    print("FEJL: INTERVALS_API_KEY og INTERVALS_ATHLETE_ID skal vaere sat", file=sys.stderr)
    sys.exit(1)

# intervals.icu bruger HTTP Basic auth med brugernavnet "API_KEY"
AUTH = base64.b64encode(f"API_KEY:{KEY}".encode()).decode()

STATUS = {
    "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
    "calls": [],
    "field_inventory": {},
}


def get(path, params=None, label=None):
    """GET mod intervals.icu. Returnerer parsed JSON eller None. Fejler aldrig hardt."""
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {AUTH}",
            "Accept": "application/json",
            "User-Agent": "marathon-sync/1.0",
        },
    )
    entry = {"label": label or path, "path": path, "params": params or {}}
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            entry["http"] = r.status
            raw = r.read()
            entry["bytes"] = len(raw)
            data = json.loads(raw.decode("utf-8", "replace"))
            entry["count"] = len(data) if isinstance(data, list) else 1
            STATUS["calls"].append(entry)
            return data
    except urllib.error.HTTPError as e:
        entry["http"] = e.code
        try:
            entry["error"] = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            entry["error"] = "(kunne ikke laese fejlbody)"
        STATUS["calls"].append(entry)
        return None
    except Exception as e:
        entry["http"] = 0
        entry["error"] = f"{type(e).__name__}: {e}"[:300]
        STATUS["calls"].append(entry)
        return None


def note_fields(label, data):
    """Gem feltnavne (ikke vaerdier) saa opsaetningen kan valideres uden noeglen."""
    sample = None
    if isinstance(data, list) and data:
        sample = data[0]
    elif isinstance(data, dict):
        sample = data
    if isinstance(sample, dict):
        STATUS["field_inventory"][label] = sorted(sample.keys())


def main():
    today = dt.date.today()
    d = lambda days: (today + dt.timedelta(days=days)).isoformat()

    payload = {
        "generated_at": STATUS["generated_at"],
        "generated_date": today.isoformat(),
        "athlete_id": ATHLETE,
    }

    # Profil: zoner, taerskler, maks-puls, vaegt. Bruges til at vurdere intensitet.
    payload["athlete"] = get(f"/athlete/{ATHLETE}", label="athlete")
    note_fields("athlete", payload["athlete"])

    # Udfoerte aktiviteter, 240 dage tilbage (daekker hele opbygningen)
    payload["activities"] = get(
        f"/athlete/{ATHLETE}/activities",
        {"oldest": d(-240), "newest": d(0)},
        label="activities",
    )
    note_fields("activities", payload["activities"])

    # Kalender: planlagte pas fra marathonplanen, bagud og fremad
    payload["events"] = get(
        f"/athlete/{ATHLETE}/events",
        {"oldest": d(-35), "newest": d(35)},
        label="events",
    )
    note_fields("events", payload["events"])

    # Wellness: CTL, ATL, form, hvilepuls, HRV, soevn, vaegt
    payload["wellness"] = get(
        f"/athlete/{ATHLETE}/wellness",
        {"oldest": d(-240), "newest": d(0)},
        label="wellness",
    )
    note_fields("wellness", payload["wellness"])

    # Detaljer for de seneste loeb, inkl. intervaller. Bruges til at vurdere
    # om et intervalpas faktisk blev udfoert paa den foreskrevne fart.
    details = []
    acts = payload.get("activities") or []
    cutoff = d(-21)
    run_types = {"run", "virtualrun", "trailrun"}
    for a in acts:
        if not isinstance(a, dict):
            continue
        day = str(a.get("start_date_local") or a.get("start_date") or "")[:10]
        atype = str(a.get("type") or "").lower()
        if day >= cutoff and atype in run_types and a.get("id"):
            det = get(f"/activity/{a['id']}", {"intervals": "true"}, label="activity_detail")
            if det:
                details.append(det)
        if len(details) >= 25:
            break
    payload["recent_activity_detail"] = details
    note_fields("activity_detail", details)

    # Skriv payload komprimeret
    os.makedirs("build", exist_ok=True)
    with gzip.open("build/payload.json.gz", "wt", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    # Opsummering til status (ingen persondata)
    STATUS["summary"] = {
        "activities": len(payload.get("activities") or []),
        "events": len(payload.get("events") or []),
        "wellness": len(payload.get("wellness") or []),
        "activity_detail": len(details),
        "athlete_ok": bool(payload.get("athlete")),
        "payload_bytes": os.path.getsize("build/payload.json.gz"),
    }
    ok = all(c.get("http") == 200 for c in STATUS["calls"])
    STATUS["all_ok"] = ok

    os.makedirs("data", exist_ok=True)
    with open("data/status.json", "w", encoding="utf-8") as f:
        json.dump(STATUS, f, ensure_ascii=False, indent=2)

    print(json.dumps(STATUS["summary"], indent=2))
    for c in STATUS["calls"]:
        if c.get("http") != 200:
            print(f"ADVARSEL {c['label']}: HTTP {c.get('http')} {c.get('error','')}", file=sys.stderr)

    # Fejl kun hvis der slet ingen aktiviteter kom ind
    if not payload.get("activities"):
        print("FEJL: ingen aktiviteter hentet", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
