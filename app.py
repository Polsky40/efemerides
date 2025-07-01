from flask import Flask, request, jsonify
import swisseph as swe
from datetime import datetime, timedelta

EPHE_PATH = "/opt/render/project/src/ephe"
swe.set_ephe_path(EPHE_PATH)

app = Flask(__name__)

# ────────────────────────────────────────────────────────────────
def hits(body, target_deg, jd0, jd1, aspect=0, orb=0.05, step_d=0.25):
    hits, jd, prev = [], jd0, None
    while jd <= jd1:
        lon = swe.calc_ut(jd, body)[0][0]
        diff = ((lon - target_deg + 540) % 360) - 180
        delta = abs(diff) - (aspect + orb)
        if prev is not None and delta * prev < 0:
            lo, hi = jd - step_d, jd
            for _ in range(30):                     # bisección
                mid = 0.5 * (lo + hi)
                lon_mid = swe.calc_ut(mid, body)[0][0]
                diff_mid = ((lon_mid - target_deg + 540) % 360) - 180
                if (abs(diff_mid) - (aspect + orb)) * delta < 0:
                    lo = mid
                else:
                    hi, delta = mid, abs(diff_mid) - (aspect + orb)
            hits.append(hi)
        prev, jd = delta, jd + step_d
    return hits

def jd_to_dt(jd):
    return datetime.utcfromtimestamp((jd - 2440587.5) * 86400)

# ────────────────────────────────────────────────────────────────
@app.post("/aspect_hits")
def aspect_hits():
    data = request.get_json(force=True)

    bodies   = data["bodies"]                    # ["SATURN", ...]
    target   = data["target"]                    # número o string
    aspect   = data.get("aspect", 0)
    orb      = data.get("orb", 0.05)
    jd_start = data["jd_start"]                  # "2025-01-01"
    jd_end   = data["jd_end"]
    natal    = data["natal_chart"]               # {"SUN":120.13,…}

    jd0 = swe.julday(*map(int, jd_start.split("-")), 0)
    jd1 = swe.julday(*map(int, jd_end.split("-")), 0)

    # target → grados
    if isinstance(target, (int, float)) or str(target).replace('.', '', 1).isdigit():
        target_deg = float(target) % 360
    else:
        target_deg = natal[target.upper()]

    results = []
    for name in bodies:
        body = getattr(swe, name.upper())
        for jd_hit in hits(body, target_deg, jd0, jd1, aspect, orb):
            ut = jd_to_dt(jd_hit)
            results.append({
                "planet": name,
                "utc": ut.strftime("%Y-%m-%d %H:%M"),
                "motion": "R" if swe.calc_ut(jd_hit, body)[0][3] < 0 else "D"
            })

    return jsonify(sorted(results, key=lambda r: r["utc"]))