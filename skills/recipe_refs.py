"""Reference-recipe catalog (config/recetas_referencia.yaml), built automatically
and incrementally from the cook's TikTok collection + Pinterest board.

Pipeline (`python main.py actualizar-recetas-ref`, also run at the start of
`semana-completa`):
  1. recipe_refs_scraper reads each collection (newest first, stops early once
     it's back among already-cataloged items).
  2. Items whose id is already in the catalog — as a recipe OR as a discarded
     non-recipe — are skipped. Idempotent: re-running adds nothing.
  3. Only the new items go to Claude (caption + thumbnail) to be classified into
     a structured entry: dish, cuisine, meal type, protein, technique, key
     ingredients. Non-recipe pins (decor, quotes…) land in `descartados` so they
     aren't re-analyzed every run.

Consumers:
  - MenuGeneratorSkill gets menu_context(): the whole catalog, compact, and must
    base several of the week's dishes on it, tagging each with a
    "📌 *Inspirado en: … (ref: <id>)*" line under the dish name.
  - RecipeFinderSkill gets recipe_context(menu): full detail for just the refs
    the menu tagged, to adapt them and cite the source on the card.
  - mark_used() stamps `ultimo_uso` on the refs the final menu used, so the menu
    generator can prefer ones not cooked recently.
"""
import base64
import json
import re
from datetime import date, datetime
from pathlib import Path

import requests
import yaml

from . import recipe_refs_scraper as scraper
from .base_skill import BaseSkill

CATALOG_PATH = Path("config/recetas_referencia.yaml")
LOG_PATH = Path("data/recipe_refs_log.txt")

ENRICH_BATCH = 15
MAX_THUMB_BYTES = 1_500_000
_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}

REF_TAG_RE = re.compile(r"\(ref:\s*((?:tiktok|pinterest)-\d+)\)")


def _log(msg: str) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now().isoformat(timespec='seconds')}  {msg}\n")


# ── Catalog I/O ─────────────────────────────────────────────────────────────

def load_catalog() -> dict:
    if not CATALOG_PATH.exists():
        return {"recetas": [], "descartados": []}
    data = yaml.safe_load(CATALOG_PATH.read_text(encoding="utf-8")) or {}
    data.setdefault("recetas", [])
    data.setdefault("descartados", [])
    return data


def save_catalog(catalog: dict) -> None:
    catalog["actualizado"] = date.today().isoformat()
    header = (
        "# Generado automáticamente por `python main.py actualizar-recetas-ref`\n"
        "# desde la colección de TikTok y el tablero de Pinterest del cocinero.\n"
        "# Puedes corregir campos a mano; los ids existentes nunca se re-analizan.\n"
    )
    body = yaml.safe_dump(
        {k: catalog[k] for k in ("actualizado", "recetas", "descartados")},
        allow_unicode=True, sort_keys=False, width=120,
    )
    CATALOG_PATH.write_text(header + body, encoding="utf-8")


def known_ids(catalog: dict) -> set:
    return {r["id"] for r in catalog["recetas"]} | {d["id"] for d in catalog["descartados"]}


# ── Enrichment (Claude) ─────────────────────────────────────────────────────

class RecipeRefsSkill(BaseSkill):

    SYSTEM_PROMPT = """Clasificas publicaciones guardadas (TikTok / Pinterest) de un cocinero gourmet amateur en México para construir su catálogo de recetas de referencia.

Para cada publicación recibes: ID, fuente, el texto disponible (caption/alt, a menudo truncado, con hashtags o en inglés) y, cuando existe, la miniatura.

Decide si es una RECETA o platillo cocinable (incluye salsas, bases, postres, bebidas, técnicas de cocina aplicadas a un platillo). Decoración, frases, lugares, restaurantes sin receta, productos, memes → NO es receta.

Responde ÚNICAMENTE con un arreglo JSON (sin texto antes ni después, sin ```), un objeto por publicación, en el mismo orden:
[
  {
    "id": "<ID tal cual>",
    "es_receta": true,
    "platillo": "Nombre descriptivo en español del platillo (no copies hashtags)",
    "cocina": "Mexicana|Japonesa|Thai|Italiana|Francesa|China|Peruana|Mediterránea|Alemana|Turca|Libanesa|Americana|Inglesa|Coreana|India|Otra",
    "tipo": "desayuno|colación|comida|cena|postre|bebida|salsa/base",
    "proteina": "proteína principal o 'vegetal'",
    "tecnica": "técnica principal (ej. sellado + glaseado al horno)",
    "ingredientes_clave": ["3 a 6 ingredientes que definen el platillo"],
    "perfil": "perfil de sabor en ≤8 palabras"
  },
  {"id": "<ID>", "es_receta": false, "motivo": "≤6 palabras"}
]

Si el texto es ambiguo, usa la miniatura. Si aun así no puedes identificar el platillo con confianza razonable, marca es_receta=false con motivo "no identificable"."""

    def classify(self, items: list[dict]) -> list[dict]:
        content: list = []
        for it in items:
            content.append({
                "type": "text",
                "text": f"ID: {it['id']} · fuente: {it['fuente']}\nTexto: {it['caption'] or '(sin texto)'}",
            })
            img = _thumb_block(it.get("thumb", ""))
            if img:
                content.append(img)
        content.append({"type": "text", "text": f"Clasifica las {len(items)} publicaciones anteriores."})
        raw = self._call_claude(self.SYSTEM_PROMPT, content, max_tokens=8000)
        return _parse_json_array(raw)


def _thumb_block(url: str) -> dict | None:
    """Download the thumbnail ourselves and inline it as base64. URL image
    sources would be simpler, but TikTok CDN links are signed/expiring and often
    refuse non-browser fetchers — one unreachable URL would fail the whole batch.
    Failing here just means that item is classified from its text alone."""
    if not url.startswith("http"):
        return None
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        ctype = r.headers.get("content-type", "").split(";")[0].strip()
        if r.status_code != 200 or ctype not in _IMAGE_TYPES or len(r.content) > MAX_THUMB_BYTES:
            return None
        return {"type": "image", "source": {
            "type": "base64", "media_type": ctype, "data": base64.b64encode(r.content).decode("ascii"),
        }}
    except requests.RequestException:
        return None


def _parse_json_array(raw: str) -> list[dict]:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        raise ValueError("la respuesta de clasificación no contiene un arreglo JSON")
    return json.loads(raw[start:end + 1])


# ── Update (scrape + classify + append) ─────────────────────────────────────

def update(sources: list[str], full: bool = False, headless: bool = True, log=print) -> dict:
    """Scrape the given sources and append only never-seen items to the catalog.
    Saves after every classified batch, so an interrupted run keeps its progress
    and the next run resumes where it stopped."""
    catalog = load_catalog()
    known = known_ids(catalog)
    stats = {"leidos": 0, "nuevas_recetas": 0, "descartados": 0, "errores": []}

    new_items: list[dict] = []
    for source in sources:
        try:
            items = scraper.scrape_source(source, known, full=full, headless=headless, log=log)
        except scraper.LoginRequired:
            raise  # actionable by the cook — surface it instead of logging past it
        except Exception as e:  # noqa: BLE001 — one broken source shouldn't block the other
            msg = f"{source}: error al leer ({e.__class__.__name__}: {str(e)[:200]})"
            stats["errores"].append(msg)
            _log(msg)
            log(msg)
            continue
        stats["leidos"] += len(items)
        new_items += [it for it in items if it["id"] not in known]

    # Oldest first, so `agregado` order roughly follows when they were saved.
    new_items.reverse()
    if not new_items:
        _log(f"sin publicaciones nuevas ({stats['leidos']} leídas)")
        return stats

    skill = RecipeRefsSkill()
    today = date.today().isoformat()
    for i in range(0, len(new_items), ENRICH_BATCH):
        batch = new_items[i:i + ENRICH_BATCH]
        log(f"Clasificando {i + 1}-{i + len(batch)} de {len(new_items)} nuevas...")
        try:
            results = {r.get("id"): r for r in skill.classify(batch)}
        except Exception as e:  # noqa: BLE001 — batch stays uncataloged → retried next run
            msg = f"clasificación falló para {len(batch)} items ({e.__class__.__name__}: {str(e)[:200]})"
            stats["errores"].append(msg)
            _log(msg)
            log(msg)
            continue

        for it in batch:
            r = results.get(it["id"])
            if not r:
                continue  # model skipped it — retried next run
            if r.get("es_receta"):
                entry = {
                    "id": it["id"],
                    "platillo": r.get("platillo", "").strip(),
                    "cocina": r.get("cocina", ""),
                    "tipo": r.get("tipo", ""),
                    "proteina": r.get("proteina", ""),
                    "tecnica": r.get("tecnica", ""),
                    "ingredientes_clave": r.get("ingredientes_clave", []),
                    "perfil": r.get("perfil", ""),
                    "fuente": it["fuente"],
                    "url": it["url"],
                    "caption": it["caption"],
                    "agregado": today,
                }
                catalog["recetas"].append(entry)
                stats["nuevas_recetas"] += 1
                _log(f"+ {entry['id']}  {entry['platillo']}")
            else:
                catalog["descartados"].append({
                    "id": it["id"], "url": it["url"], "motivo": r.get("motivo", "no es receta"),
                })
                stats["descartados"] += 1
                _log(f"- {it['id']}  descartado: {r.get('motivo', '')}")
        save_catalog(catalog)

    return stats


# ── Prompt context for the generators ───────────────────────────────────────

def _entry_line(r: dict) -> str:
    ingr = ", ".join(r.get("ingredientes_clave") or [])
    used = f" · usado {r['ultimo_uso']}" if r.get("ultimo_uso") else ""
    return (
        f"- (ref: {r['id']}) {r['platillo']} — {r.get('cocina', '')} · {r.get('tipo', '')} · "
        f"{r.get('proteina', '')} · {r.get('tecnica', '')} · {ingr}{used}"
    )


def menu_context(catalog: dict | None = None) -> str:
    """Whole catalog, one line per recipe, never-used first (then least recently
    used) so the model naturally rotates through it."""
    catalog = catalog or load_catalog()
    recetas = [r for r in catalog["recetas"] if r.get("platillo")]
    if not recetas:
        return ""
    recetas.sort(key=lambda r: (r.get("ultimo_uso") or "", r["id"]))
    return (
        "RECETAS DE REFERENCIA DEL COCINERO (guardadas por él en TikTok/Pinterest — ver regla 11):\n"
        + "\n".join(_entry_line(r) for r in recetas)
    )


def refs_in_menu(menu_text: str) -> list[str]:
    return list(dict.fromkeys(REF_TAG_RE.findall(menu_text)))


def recipe_context(menu_text: str, catalog: dict | None = None) -> str:
    """Full detail for only the refs the menu tagged — the recipe cards adapt
    these; untagged dishes are written from scratch as before."""
    catalog = catalog or load_catalog()
    by_id = {r["id"]: r for r in catalog["recetas"]}
    refs = [by_id[i] for i in refs_in_menu(menu_text) if i in by_id]
    if not refs:
        return ""
    blocks = []
    for r in refs:
        blocks.append(
            f"(ref: {r['id']}) {r['platillo']}\n"
            f"  Cocina: {r.get('cocina', '')} · Técnica: {r.get('tecnica', '')} · Perfil: {r.get('perfil', '')}\n"
            f"  Ingredientes clave: {', '.join(r.get('ingredientes_clave') or [])}\n"
            f"  Texto original: {r.get('caption', '')}\n"
            f"  URL: {r['url']}"
        )
    return "RECETAS DE REFERENCIA USADAS EN ESTE MENÚ:\n\n" + "\n\n".join(blocks)


def catalog_compact(catalog: dict | None = None) -> str:
    catalog = catalog or load_catalog()
    return "\n".join(f"{_entry_line(r)} · {r['url']}" for r in catalog["recetas"] if r.get("platillo"))


def mark_used(menu_path) -> list[str]:
    """Stamp `ultimo_uso` (the menu's week, from its menu_YYYY-MM-DD.md name) on
    every ref the final menu tagged. Call once per week, after the menu passed
    (or exhausted) validation — not per retry attempt."""
    menu_path = Path(menu_path)
    ids = refs_in_menu(menu_path.read_text(encoding="utf-8"))
    if not ids:
        return []
    m = re.search(r"\d{4}-\d{2}-\d{2}", menu_path.name)
    stamp = m.group(0) if m else date.today().isoformat()
    catalog = load_catalog()
    hit = []
    for r in catalog["recetas"]:
        if r["id"] in ids:
            r["ultimo_uso"] = stamp
            hit.append(r["platillo"])
    if hit:
        save_catalog(catalog)
    return hit
