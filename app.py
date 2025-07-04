from flask import Flask, request, jsonify
from flask_cors import CORS
import swisseph as swe
import datetime
from typing import List, Union, Dict, Any

app = Flask(__name__)
CORS(app)

# -----------------------------------------------------------------------------
# CONFIGURACIÓN
# -----------------------------------------------------------------------------
swe.set_ephe_path("./ephe")  # Update to path where .se1/.se2 live

# -----------------------------------------------------------------------------
# UTILIDADES
# -----------------------------------------------------------------------------

def _to_julian(dt_iso: str) -> float:
    dt = datetime.datetime.fromisoformat(dt_iso)
    return swe.julday(dt.year, dt.month, dt.day,
                      dt.hour + dt.minute / 60 + dt.second / 3600)


def _planet_longitude(planet_name: str, dt_iso: str) -> float:
    jd = _to_julian(dt_iso)
    pl_id = getattr(swe, planet_name.upper(), None)
    if pl_id is None:
        raise ValueError(f"Planeta desconocido: {planet_name}")
    (lon, _lat, _dist, *_), _flags = swe.calc_ut(jd, pl_id)
    return lon % 360


# -----------------------------------------------------------------------------
# /planet_position
# -----------------------------------------------------------------------------

@app.get("/planet_position")
def planet_position():
    planet = request.args.get("planet")
    dt_iso = request.args.get("datetime")
    if not planet or not dt_iso:
        return jsonify(error="Faltan parámetros"), 400
    try:
        lon = _planet_longitude(planet, dt_iso)
        return jsonify(planet=planet.upper(), longitude=lon)
    except Exception as exc:
        return jsonify(error=str(exc)), 400


# -----------------------------------------------------------------------------
# /aspect_hits – soporta listas en target y aspect
# -----------------------------------------------------------------------------

@app.post("/aspect_hits")
def aspect_hits():
    data: Dict[str, Any] = request.get_json(force=True, silent=True) or {}

    bodies = data.get("bodies", [])
    target_raw = data.get("target")
    aspect_raw = data.get("aspect", 0)
    orb = float(data.get("orb", 0.05))
    jd_start_s, jd_end_s = data.get("jd_start"), data.get("jd_end")
    natal_chart: Dict[str, float] = data.get("natal_chart", {})

    if not isinstance(bodies, list) or not bodies:
        return jsonify(error="bodies debe ser lista"), 400
    if target_raw is None or jd_start_s is None or jd_end_s is None:
        return jsonify(error="target, jd_start y jd_end son obligatorios"), 400

    targets = target_raw if isinstance(target_raw, list) else [target_raw]
    aspect_list = aspect_raw if isinstance(aspect_raw, list) else [aspect_raw]
    aspect_list = [float(a) for a in aspect_list]

    jd_start = _to_julian(jd_start_s + "T00:00")
    jd_end = _to_julian(jd_end_s + "T00:00")

    hits: List[Dict[str, Any]] = []

    for t in targets:
        # obtengo la longitud del target
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
                (lon, _lat, _dist, *_), _flags = swe.calc_ut(jd_curr, pl_id)
                delta = (lon - t_lon + 360) % 360

                for asp in aspect_list:
                    diff = min(abs(delta - asp), 360 - abs(delta - asp))
                    if diff <= orb:
                        y, m, d, hr, mi, se = swe.revjul(jd_curr)
                        ts = f"{y:04d}-{m:02d}-{d:02d}T{int(hr):02d}:{int(mi):02d}Z"
                        hits.append({
                            "planet": body.upper(),
                            "target": t,
                            "angle": asp,
                            "orb": round(diff, 4),
                            "utc": ts,
                        })
                        break  # evita duplicados en el mismo día
                jd_curr += 1

    return jsonify(hits)


# -----------------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
