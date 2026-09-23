"""Free, local check of the SMN/CONAGUA short-range forecast for Cuajimalpa
de Morelos (Ciudad de México) — grounds the menu generator's seasonal/climate
guidance in a real forecast instead of the model's general knowledge or a
bare "consulta este sitio" instruction it had no way to act on (that's what
the prompt used to say before it was dropped — see git history on
menu_generator.py, commit ce5fb83).

Source: the public JSON endpoint that backs SMN's own municipio-forecast page
(https://smn.conagua.gob.mx/es/pronosticos/pronostico-del-tiempo-por-municipios,
embedded iframe -> controlador/getDataJson2String.php). Undocumented — found
by reading that page's own JS (public/js/main.js) — so it could change or
disappear without notice. Fails soft: any error (network, non-200, unexpected
shape) returns None/"" and the caller falls back to season-only guidance.
"""
from datetime import date, timedelta

import requests

# Spanish weekday names, keyed by date.weekday() (0=lunes) — the system
# locale isn't set to es_MX anywhere in this project, so strftime('%A') comes
# back in English; every other Spanish-language date label in this codebase
# (site_builder.py's _DAY_SHORT, menu_generator.py's day_names) hand-maps for
# the same reason.
_DOW_ES = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo']

BASE_URL = "https://smn.conagua.gob.mx/tools/PHP/pronostico_municipios_grafico/controlador/getDataJson2String.php"
# Cuajimalpa de Morelos, Ciudad de México — id_edo/id_mpo from that same
# tool's controlador/datosMunicipios.php municipio list.
ID_EDO = 9
ID_MPO = 4
TIMEOUT_S = 10


def get_forecast() -> list[dict] | None:
    """Return SMN's short-range forecast for Cuajimalpa de Morelos as a list
    of daily dicts (tmax/tmin °C, desciel, probprec %, prec mm, ...), one
    entry per day starting today — typically 4 days out. None on any failure;
    never raises."""
    try:
        resp = requests.get(
            BASE_URL,
            params={"edo": ID_EDO, "mun": ID_MPO},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) and data else None
    except Exception:
        return None


def format_forecast_for_prompt(data: list[dict] | None, today: date | None = None) -> str:
    """Render the forecast as a short block for the menu-generation prompt.
    Returns "" for None/empty input — callers must treat that as "no forecast
    available" and fall back to season-only guidance, never block on it."""
    if not data:
        return ""
    today = today or date.today()
    lines = [
        f"PRONÓSTICO DEL CLIMA — Cuajimalpa de Morelos, CDMX (fuente: SMN/CONAGUA, "
        f"consultado hoy {today.isoformat()}; solo cubre los próximos {len(data)} días — "
        "para el resto de la semana usa la temporada del mes indicada arriba):"
    ]
    for i, day in enumerate(data):
        d = today + timedelta(days=i)
        try:
            tmax = float(day["tmax"])
            tmin = float(day["tmin"])
            prob = float(day.get("probprec", 0) or 0)
        except (KeyError, ValueError, TypeError):
            continue
        cielo = day.get("desciel", "").strip()
        dow = _DOW_ES[d.weekday()]
        lines.append(
            f"- {dow.capitalize()} {d.strftime('%d/%m')}: {tmin:.0f}–{tmax:.0f}°C, {cielo}"
            + (f", prob. lluvia {prob:.0f}%" if prob else "")
        )
    return "\n".join(lines) if len(lines) > 1 else ""
