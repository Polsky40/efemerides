from flask import Flask, request, jsonify
from flask_cors import CORS
import swisseph as swe
import datetime
from typing import List, Union, Dict, Any
from dateutil import parser, tz

# -----------------------------------------------------------------------------
# CONFIGURACIÓN
# -----------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

swe.set_ephe_path("./ephe")

SIGNS = [
    "ARIES", "TAURUS", "GEMINI", "CANCER", "LEO", "VIRGO",
    "LIBRA", "SCORPIO", "SAGITTARIUS", "CAPRICORNUS", "AQUARIUS", "PISCES"
]

DEFAULT_PLANETS = [
    "SUN", "MOON", "MERCURY", "VENUS", "MARS",
    "JUPITER", "SATURN", "URANUS", "NEPTUNE", "PLUTO"
]

# -----------------------------------------------------------------------------
# UTILIDADES
# -----------------------------------------------------------------------------

def _to_julian(dt_iso: str) -> float:
    dt = parser.isoparse(dt_iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz.UTC)
    dt_utc = dt.astimezone(tz.UTC)
    return swe.julday(
        dt_utc.year, dt_utc.month, dt_utc.day,
        dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600
    )

def format_lon(lon: float) -> str:
    sign_index = int(lon // 30)
    sign = SIGNS[sign_index]
    deg_in_sign = lon % 30
    deg = int(deg_in_sign)
    minutes = int((deg_in_sign - deg) * 60)
    seconds = int(((deg_in_sign - deg) * 60 - minutes) * 60)
    return f"{deg:02d}°{minutes:02d}′{seconds:02d}″ {sign}"

def _planet_data(planet_name: str, dt_iso: str) -> Dict[str, Any]:
    jd = _to_julian(dt_iso)
    pl_id = getattr(swe, planet_name.upper(), None)
    if pl_id is None:
        raise ValueError(f"Planeta desconocido: {planet_name}")

    (pl_pos, _flags) = swe.calc_ut(jd, pl_id)
    lon, spd_lon = pl_pos[0] % 360, pl_pos[3]

    return {
        "planet": planet_name.upper(),
        "longitude": lon,
        "sign": SIGNS[int(lon // 30)],
        "position": format_lon(lon),
        "motion": "R" if spd_lon < 0 else "D",
    }

# -----------------------------------------------------------------------------
# ROUTES
# -----------------------------------------------------------------------------

@app.route("/")
def index():
    return "Swiss Ephemeris API – rutas: /planet_position, /aspect_hits, /chart", 200

@app.route("/planet_position", methods=["GET"])
def planet_position():
    planet = request.args.get("planet")
    dt_iso = request.args.get("datetime")
    if not planet or not dt_iso:
        return jsonify(error="Faltan parámetros: 'planet' y 'datetime' son obligatorios"), 400
    try:
        return jsonify(_planet_data(planet, dt_iso))
    except Exception as exc:
        return jsonify(error=str(exc)), 400

@app.route("/aspect_hits", methods=["POST"])
def aspect_hits():
    data: Dict[str, Any] = request.get_json(force=True, silent=True) or {}

    bodies = data.get("bodies", [])
    target_raw = data.get("target")
    aspect_raw = data.get("aspect", 0)
    orb = float(data.get("orb", 0.05))
    jd_start_s, jd_end_s = data.get("jd_start"), data.get("jd_end")
    step_hours = float(data.get("step_hours", 1))
    natal_chart: Dict[str, float] = data.get("natal_chart", {})

    if not bodies:
        return jsonify(error="Debes especificar al menos un planeta en 'bodies'"), 400
    if target_raw is None or jd_start_s is None or jd_end_s is None:
        return jsonify(error="'target', 'jd_start' y 'jd_end' son obligatorios"), 400

    targets = target_raw if isinstance(target_raw, list) else [target_raw]
    aspects = [float(a) for a in aspect_raw] if isinstance(aspect_raw, list) else [float(aspect_raw)]

    jd_start = _to_julian(jd_start_s + "T00:00")
    jd_end = _to_julian(jd_end_s + "T00:00")
    step = step_hours / 24.0

    hits: List[Dict[str, Any]] = []

    for t in targets:
        dyn_pl_id = None
        if isinstance(t, (int, float)):
            base_t_lon = float(t) % 360
        elif isinstance(t, str):
            if t.upper() in natal_chart:
                base_t_lon = natal_chart[t.upper()] % 360
            else:
                dyn_pl_id = getattr(swe, t.upper(), None)
                if dyn_pl_id is None:
                    continue
                base_t_lon = None
        else:
            continue

        for body in bodies:
            pl_id = getattr(swe, body.upper(), None)
            if pl_id is None:
                continue

            jd_curr = jd_start
            while jd_curr <= jd_end:
                (pos_body, _flags) = swe.calc_ut(jd_curr, pl_id)
                lon_body, spd_lon_body = pos_body[0] % 360, pos_body[3]

                if dyn_pl_id is not None:
                    (pos_target, _) = swe.calc_ut(jd_curr, dyn_pl_id)
                    t_lon = pos_target[0] % 360
                else:
                    t_lon = base_t_lon

                delta = (lon_body - t_lon + 360) % 360

                for asp in aspects:
                    diff = min(abs(delta - asp), 360 - abs(delta - asp))
                    if diff <= orb:
                        y, m, d, ut = swe.revjul(jd_curr)
                        hr = int(ut)
                        mi = int(round((ut - hr) * 60))
                        ts = f"{y:04d}-{m:02d}-{d:02d}T{hr:02d}:{mi:02d}Z"
                        hits.append({
                            "planet": body.upper(),
                            "utc": ts,
                            "motion": "R" if spd_lon_body < 0 else "D",
                        })
                        break
                jd_curr += step

    hits.sort(key=lambda h: h["utc"])
    return jsonify(hits)

@app.route("/chart", methods=["GET"])
def chart():
    dt_iso = request.args.get("datetime")
    lat = float(request.args.get("lat", 0))
    lon = float(request.args.get("lon", 0))
    if not dt_iso:
        return jsonify(error="Falta 'datetime'"), 400

    jd = _to_julian(dt_iso)
    chart = {}
    for p in DEFAULT_PLANETS:
        chart[p] = _planet_data(p, dt_iso)

    # Cálculo de casas (Placidus)
    hsys = b'P'
    cusps, ascmc = swe.houses(jd, lat, lon, hsys)
    chart["houses"] = {f"House {i+1}": format_lon(cusps[i] % 360) for i in range(12)}
    chart["asc"] = format_lon(ascmc[0] % 360)
    chart["mc"] = format_lon(ascmc[1] % 360)

    return jsonify(chart)

# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
