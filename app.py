from flask import Flask, request, jsonify
from flask_cors import CORS
import swisseph as swe
import datetime
from typing import List, Union, Dict, Any

app = Flask(__name__)
CORS(app)

# -----------------------------------------------------------------------------
# CONFIGURACIÓN GENERAL
# -----------------------------------------------------------------------------
swe.set_ephe_path("./ephe")  # Carpeta donde están los archivos .se1 / .se2
SIGNS = [
    "ARIES", "TAURUS", "GEMINI", "CANCER", "LEO", "VIRGO",
    "LIBRA", "SCORPIO", "SAGITTARIUS", "CAPRICORNUS", "AQUARIUS", "PISCES"
]

# -----------------------------------------------------------------------------
# UTILIDADES
# -----------------------------------------------------------------------------

def _to_julian(dt_iso: str) -> float:
    dt = datetime.datetime.fromisoformat(dt_iso)
    return swe.julday(dt.year, dt.month, dt.day,
                      dt.hour + dt.minute / 60 + dt.second / 3600)


def _planet_data(planet_name: str, dt_iso: str) -> Dict[str, Any]:
    jd = _to_julian(dt_iso)
    pl_id = getattr(swe, planet_name.upper(), None)
    if pl_id is None:
        raise ValueError(f"Planeta desconocido: {planet_name}")

    (lon, _lat, _dist, spd_lon, *_), _ = swe.calc_ut(jd, pl_id)
    lon %= 360

    sign_index = int(lon // 30)
    sign = SIGNS[sign_index]

    deg_in_sign = lon % 30
    deg = int(deg_in_sign)
    minutes = int(round((deg_in_sign - deg) * 60))
    if minutes == 60:
        minutes = 0
        deg += 1
        if deg == 30:
            deg = 0
            sign_index = (sign_index + 1) % 12
            sign = SIGNS[sign_index]

    position = f"{deg:02d}° {minutes:02d}′"
    motion = "R" if spd_lon < 0 else "D"

    return {
        "planet": planet_name.upper(),
        "sign": sign,
        "position": position,
        "motion": motion,
    }

# -----------------------------------------------------------------------------
# ROUTES
# -----------------------------------------------------------------------------

@app.route("/planet_position", methods=["GET"])
def planet_position():
    planet = request.args.get("planet")
    dt_iso = request.args.get("datetime")
    if not planet or not dt_iso:
        return jsonify(error="Faltan parámetros 'planet' y/o 'datetime'"), 400
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
    natal_chart: Dict[str, float] = data.get("natal_chart", {})

    if not isinstance(bodies, list) or not bodies:
        return jsonify(error="'bodies' debe ser lista"), 400
    if target_raw is None or jd_start_s is None or jd_end_s is None:
        return jsonify(error="'target', 'jd_start' y 'jd_end' son obligatorios"), 400

    targets = target_raw if isinstance(target_raw, list) else [target_raw]
    aspects = aspect_raw if isinstance(aspect_raw, list) else [aspect_raw]
    aspects = [float(a) for a in aspects]

    try:
        jd_start = _to_julian(jd_start_s + "T00:00")
        jd_end = _to_julian(jd_end_s + "T00:00")
    except Exception as exc:
        return jsonify(error=f"Fecha inválida: {exc}"), 400

    hits = []
    for t in targets:
        if isinstance(t, (int, float)):
            t_lon = float(t) % 360
        elif isinstance(t, str):
            t_lon = natal_chart.get(t.upper())
            if t_lon is None:
                continue
        else:
            continue

        for body in bodies:
            pl_id = getattr(swe, body.upper(), None)
            if pl_id is None:
                continue

            jd_curr = jd_start
            while jd_curr <= jd_end:
                (lon, _lat, _dist, spd_lon, *_), _ = swe.calc_ut(jd_curr, pl_id)
                lon %= 360
                delta = (lon - t_lon + 360) % 360

                for asp in aspects:
                    diff = min(abs(delta - asp), 360 - abs(delta - asp))
                    if diff <= orb:
                        y, m, d, hr, mi, se = swe.revjul(jd_curr)
                        ts = f"{y:04d}-{m:02d}-{d:02d}T{int(hr):02d}:{int(mi):02d}Z"
                        hits.append({
                            "planet": body.upper(),
                            "utc": ts,
                            "motion": "R" if spd_lon < 0 else "D",
                        })
                        break
                jd_curr += 1

    return jsonify(hits)

# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
