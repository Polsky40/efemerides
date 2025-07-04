from flask import Flask, request, jsonify
from flask_cors import CORS
import swisseph as swe
import datetime
from typing import List, Union, Dict, Any

app = Flask(__name__)
CORS(app)

# -----------------------------------------------------------------------------
# CONFIGURACIÓN BÁSICA
# -----------------------------------------------------------------------------
swe.set_ephe_path("./ephe")  # Ajustar si la carpeta cambia

# -----------------------------------------------------------------------------
# HELPERS
# -----------------------------------------------------------------------------

def _to_julian(dt_iso: str) -> float:
    """Convierte fecha-hora ISO (YYYY-MM-DDThh:mm) a día juliano"""
    dt = datetime.datetime.fromisoformat(dt_iso)
    return swe.julday(dt.year, dt.month, dt.day,
                      dt.hour + dt.minute / 60 + dt.second / 3600)


def _planet_longitude(planet_name: str, dt_iso: str) -> float:
    """Devuelve la longitud eclíptica (0-360°) de un planeta"""
    jd = _to_julian(dt_iso)
    pl_id = getattr(swe, planet_name.upper(), None)
    if pl_id is None:
        raise ValueError(f"Planeta desconocido: {planet_name}")
    pl_data, _ = swe.calc_ut(jd, pl_id)  # retorna (datos, flags)
    lon = pl_data[0] % 360
    return lon

# -----------------------------------------------------------------------------
# ENDPOINT /planet_position
# -----------------------------------------------------------------------------

@app.get("/planet_position")
def planet_position():  # pragma: no cover
    planet = request.args.get("planet")
    dt_iso = request.args.get("datetime")
    if not planet or not dt_iso:
        return jsonify(error="Faltan parámetros: planet y datetime"), 400
    try:
        lon = _planet_longitude(planet, dt_iso)
    except Exception as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(planet=planet.upper(), longitude=lon)

# -----------------------------------------------------------------------------
# ENDPOINT /aspect_hits (versión lista)
# -----------------------------------------------------------------------------

@app.post("/aspect_hits")
def aspect_hits():  # pragma: no cover
    data: Dict[str, Any] = request.get_json(force=True, silent=True) or {}

    bodies: List[str] = data.get("bodies", [])
    target: Union[str, float, int, List[Union[str, float, int]]] = data.get("target")
    aspect_in = data.get("aspect", 0)
    orb = float(data.get("orb", 0.05))
    jd_start_s = data.get("jd_start")
    jd_end_s = data.get("jd_end")
    natal_chart: Dict[str, float] = data.get("natal_chart", {})

    if not isinstance(bodies, list) or not bodies:
        return jsonify(error="bodies debe ser lista y no vacía"), 400
    if target is None:
        return jsonify(error="target es obligatorio"), 400
    if jd_start_s is None or jd_end_s is None:
        return jsonify(error="jd_start y jd_end son obligatorios"), 400

    aspect_list: List[float] = (
        [float(a) for a in aspect_in] if isinstance(aspect_in, list) else [float(aspect_in)]
    )
    targets: List[Union[str, float, int]] = target if isinstance(target, list) else [target]

    jd_start = _to_julian(f"{jd_start_s}T00:00")
    jd_end = _to_julian(f"{jd_end_s}T00:00")

    hits: List[Dict[str, Any]] = []

    for t in targets:
        # longitud del target
        if isinstance(t, (int, float)):
            t_lon = float(t) % 360
        elif isinstance(t, str):
            t_lon = natal_chart.get(t.upper())
            if t_lon is None:
                continue  # target string sin posición → se ignora
        else:
            continue

        for body in bodies:
            pl_id = getattr(swe, body.upper(), None)
            if pl_id is None:
                continue

            jd_curr = jd_start
            while jd_curr <= jd_end:
                pl_data, _ = swe.calc_ut(jd_curr, pl_id)
                lon = pl_data[0] % 360
                delta = (lon - t_lon + 360) % 360

                for asp in aspect_list:
                    diff = min(abs(delta - asp), 360 - abs(delta - asp))
                    if diff <= orb:
                        y, m, d, frac = swe.revjul(jd_curr)
                        hour = int(frac * 24)
                        minute = int((frac * 24 - hour) * 60)
                        ts = f"{y:04d}-{m:02d}-{d:02d}T{hour:02d}:{minute:02d}Z"
                        hits.append({
                            "planet": body.upper(),
                            "target": t,
                            "angle": asp,
                            "orb": round(diff, 4),
                            "utc": ts,
                        })
                        break
                jd_curr += 1

    return jsonify(hits)

# -----------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    app.run(host="0.0.0.0", port=8000, debug=False)
