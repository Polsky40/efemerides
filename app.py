from flask import Flask, request, jsonify
from flask_cors import CORS
import swisseph as swe
from datetime import datetime

app = Flask(__name__)
CORS(app)  # Habilita CORS para todos los orígenes (incluye GPTs personalizados)

# Ruta a efemérides
EPHE_PATH = "/opt/render/project/src/ephe"
swe.set_ephe_path(EPHE_PATH)

# ───────────────────────────────
def hits(body, target_deg, jd0, jd1, aspect=0, orb=0.05, step_d=0.25):
    hits, jd, prev = [], jd0, None
    while jd <= jd1:
        lon = swe.calc_ut(jd, body)[0][0]
        diff = ((lon - target_deg + 540) % 360) - 180
        delta = abs(diff) - (aspect + orb)
        if prev is not None and delta * prev < 0:
            lo, hi = jd - step_d, jd
            for _ in range(30):
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

# ───────────────────────────────
@app.post("/aspect_hits")
def aspect_hits():
    data = request.get_json(force=True)

    bodies   = data["bodies"]
    target   = data["target"]
    aspect   = data.get("aspect", 0)
    orb      = data.get("orb", 0.05)
    jd_start = data["jd_start"]
    jd_end   = data["jd_end"]
    natal    = data.get("natal_chart", {})

    jd0 = swe.julday(*map(int, jd_start.split("-")), 0)
    jd1 = swe.julday(*map(int, jd_end.split("-")), 0)

    if isinstance(target, (int, float)) or str(target).replace('.', '', 1).isdigit():
        target_deg = float(target) % 360
    else:
        target_deg = natal.get(target.upper())
        if target_deg is None:
            return jsonify({"error": f"Target '{target}' no está presente en natal_chart."}), 400

    results = []
    for name in bodies:
        try:
            body = getattr(swe, name.upper())
        except AttributeError:
            continue
        for jd_hit in hits(body, target_deg, jd0, jd1, aspect, orb):
            ut = jd_to_dt(jd_hit)
            results.append({
                "planet": name,
                "utc": ut.strftime("%Y-%m-%d %H:%M"),
                "motion": "R" if swe.calc_ut(jd_hit, body)[0][3] < 0 else "D"
            })

    return jsonify(sorted(results, key=lambda r: r["utc"]))

# ───────────────────────────────
@app.get("/planet_position")
def planet_position():
    planet_name = request.args.get("planet", "").upper()
    datetime_str = request.args.get("datetime", "")

    if not planet_name or not datetime_str:
        return jsonify({"error": "Faltan parámetros: 'planet' y/o 'datetime'"}), 400

    try:
        dt = datetime.fromisoformat(datetime_str)
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Usá ISO: 2025-06-02T12:00"}), 400

    try:
        planet = getattr(swe, planet_name)
    except AttributeError:
        return jsonify({"error": f"Planeta '{planet_name}' no reconocido"}), 400

    jd = swe.julday(dt.year, dt.month, dt.day, dt.hour + dt.minute / 60.0)
    xx, _ = swe.calc_ut(jd, planet, flags=swe.FLG_SPEED)
    lon = xx[0]
    speed = xx[3]
    motion = "R" if speed < 0 else "D"

    signo_idx = int(lon // 30)
    signos = [
        "Aries", "Tauro", "Géminis", "Cáncer", "Leo", "Virgo",
        "Libra", "Escorpio", "Sagitario", "Capricornio", "Acuario", "Piscis"
    ]
    grados_en_signo = lon % 30
    deg = int(grados_en_signo)
    min_float = (grados_en_signo - deg) * 60
    minute = int(min_float)
    second = int((min_float - minute) * 60)
    dms = f"{deg:02d}°{minute:02d}'{second:02d}\""

    return jsonify({
        "planet": planet_name,
        "motion": motion,
        "sign_position": f"{dms} en {signos[signo_idx]}"
    })

# ───────────────────────────────
@app.get("/")
def index():
    return "🪐 Swiss Ephemeris API activa"