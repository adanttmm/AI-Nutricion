from .base_skill import BaseSkill
from . import recipe_refs
from pathlib import Path
from datetime import date
import re
import time


class RecipeFinderSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un chef instructor que crea tarjetas de receta profesionales y concisas para cocineros avanzados. Escribe recetas rápidas, eficientes, fit, gourmet amateur y de comida hogareña.

NIVEL DEL COCINERO: Avanzado. No explicar técnicas básicas. Ir directo a la técnica y el resultado.
ESTILO: Gourmet amateur, rápido, eficiente, fit y hogareño. Técnicas profesionales, temperaturas exactas, indicadores visuales/táctiles de punto.
COCINA: En orden de preferencia:
    1 - Mexicana
    2 - Japonesa
    3 - Thai
    4 - Italiana
    5 - Francesa
    6 - China
    7 - Peruana
    8 - Mediterránea
    9 - Alemana
    10 - Turca
    11 - Libanesa
    12 - Americana
    13 - Inglesa
EQUIPO: horno convencional, estufa de gas, sartén de hierro, olla de presión, licuadora, procesador, batidora, maquina helados, big green egg, ahumados y rostiados.
INGREDIENTES: Locales, preferentemente frescos y de temporada. También considerar conservas gourmet. LOS INGREDIENTES DEBEN ESTAR DISPONIBLES EN  MEXICO EN CITY MARKET, COSTCO, OR MERCADO LIBRE SUPER
EXLCUIR TERMINANTEMENTE LOS SIGUIENTES INGREDIENTES:
    - Tajin
    - Coco seco
IDIOMA: Español mexicano / Ingles.
REFERENCIAS: Los platillos del menú marcados con "📌 *Inspirado en: … (ref: <id>)*" se basan en una receta que el cocinero guardó en TikTok/Pinterest; cuando recibas el bloque "RECETAS DE REFERENCIA USADAS EN ESTE MENÚ", usa esa referencia como plantilla de la tarjeta (su técnica, perfil de sabor e ingredientes característicos) y adáptala a lo que dicta el menú: nombre del platillo, porciones y gramajes por persona, ingredientes disponibles en México y las exclusiones de arriba. Si el menú cambió algo respecto a la referencia (proteína, guarnición, técnica para meal prep), manda el menú. Los platillos sin 📌 se crean desde cero.

ESTRUCTURA DE CADA TARJETA — exactamente así, sin secciones adicionales:

### [emoji] [Tiempo de comida] — [Nombre del Platillo]
**Tiempo:** prep XX min · cocción XX min | **Porciones:** 2 (o 3 si aplica)
📌 Basado en: [nombre de la referencia](URL de la referencia)   ← SOLO si el platillo del menú tiene 📌; omite la línea si no

| Porción | 🧔 ATM | 👤 IOB |
|---|---|---|
| [nombre del platillo o acompañamiento] | [peso después de cocción o unidades] | [peso después de cocción o unidades] |

*(una fila por platillo o acompañamiento, peso después de cocción o unidades a servir)*

| Ingrediente | 🧔 ATM | 👤 IOB |
|---|---|---|
| [nombre ingrediente] | [cantidad cruda] | [cantidad cruda] |

*(una fila por ingrediente con peso en CRUDO/SECO antes de cocción — NUNCA pesos cocidos; omitir condimentos "al gusto")*

**Preparación**
Pasos numerados enunciando ingredientes y cantidades respectivas. Para cada paso que se realiza el fin de semana en el meal prep, antepón exactamente esta nota en cursiva:
*🏪 Prep fin de semana — hecho el domingo, guardar refrigerado.*
Luego el paso normalmente. Los pasos del día de servicio van directamente sin nota.

**Emplatado**
1-2 líneas de presentación.

**Tip del chef**
Un consejo técnico no obvio.

🎥 [Buscar en YouTube ES](https://www.youtube.com/results?search_query=receta+NOMBRE) · [YouTube EN](https://www.youtube.com/results?search_query=how+to+make+NOMBRE_EN) · [Referencia Google](https://www.google.com/search?q=receta+gourmet+NOMBRE)

---
REGLAS:
- NO incluir secciones "Mise en place", "Conservación", "Regeneración" ni "Meal prep durante la semana". Solo las secciones indicadas arriba.
- Los URLs deben tener nombres codificados (sin acentos, espacios como +).
- Si el mismo platillo aparece varios días, genera la tarjeta completa IDÉNTICA cada vez (mismos ingredientes, mismas cantidades, mismo nombre de cada ingrediente, mismos pasos) — nunca referencies otro día ni cambies los nombres de ingredientes entre días.
- CONSISTENCIA DE NOMBRES: usa exactamente el mismo nombre para cada ingrediente en todas las tarjetas de la semana. No escribas "plátano dominico" un día y "plátano maduro" otro — elige un nombre y úsalo siempre. Lo mismo para proteína en polvo, tortilla integral, champiñones, etc."""

    def generate_for_menu(
        self, menu_path: str, week_date: date = None, week_notes: str = "", on_progress=None,
    ) -> Path:
        """on_progress(i, total, elapsed=None), called once before each chunk starts
        (elapsed=None) and once after it finishes (elapsed=seconds) — used to show
        progress instead of a single silent spinner across all chunks."""
        if week_date is None:
            week_date = date.today()

        menu_content = Path(menu_path).read_text(encoding="utf-8")
        # Refs go in the system prompt, not the per-chunk message: every chunk
        # needs the same block, and the system prompt is what's cached.
        refs = recipe_refs.recipe_context(menu_content)
        system = f"{self.SYSTEM_PROMPT}\n\n{refs}" if refs else self.SYSTEM_PROMPT
        chunks = self._split_menu_into_chunks(menu_content, chunk_size=2)

        day_hdr = (
            "Usa encabezados de sección exactamente así antes de cada grupo de recetas: "
            "'# 🗓️ NOMBRE_DÍA DD DE MES' con el nombre del día en mayúsculas igual que en el menú "
            "(ej: # 🗓️ LUNES 8 DE JUNIO, # 🗓️ JUEVES 11 DE JUNIO)."
        )
        base = (
            "Crea las tarjetas de receta para todos los platillos indicados (excepto comida trampa 🎉). "
            "Organiza por día y tiempo de comida en el mismo orden del menú. "
            "IMPORTANTE: Si el mismo platillo aparece en múltiples días, genera la receta COMPLETA en cada día. "
            "Nunca uses referencias a otros días ('Ver receta del X') — cada día debe ser completamente autónomo."
        )
        notes_block = ""
        if week_notes:
            notes_block = (
                f"\n\n📋 INDICACIONES DEL COCINERO PARA ESTA SEMANA:\n{week_notes}\n"
                "Ten esto en cuenta al escribir cada tarjeta (ej: si pide técnicas rápidas, prioriza pasos "
                "cortos; si pide evitar un ingrediente, verifica que ninguna tarjeta lo use; si menciona "
                "sobras o equipo disponible, ajusta la técnica de las tarjetas afectadas)."
            )

        parts = []
        for i, chunk in enumerate(chunks):
            if on_progress:
                on_progress(i + 1, len(chunks))
            t0 = time.monotonic()
            extra = (
                "\nAl final incluye '## Preparaciones Base Compartidas' si alguna base del domingo se reutiliza."
                if i == len(chunks) - 1 else ""
            )
            raw = self._call_claude(
                system,
                f"{base} {day_hdr}{notes_block}\n\n{chunk}{extra}",
                max_tokens=16000,
            )
            if on_progress:
                on_progress(i + 1, len(chunks), time.monotonic() - t0)
            parts.append(raw)

        content = "\n\n---\n\n".join(parts)
        content = self._dedupe_repeated_recipes(content)
        header = (
            f"# 📖 Recetario Semanal\n"
            f"## Semana del {week_date.strftime('%d de %B de %Y')}\n\n"
            f"> **Nivel:** Avanzado · **Para:** 2 personas (3 en comidas mar/mié/vie — 3er comensal porción IOB)\n\n---\n\n"
        )
        filename = f"recetas_{week_date.strftime('%Y-%m-%d')}.md"
        return self._save_output(header + content, "outputs/recipes", filename)

    @staticmethod
    def _dedupe_repeated_recipes(content: str) -> str:
        """Force byte-identical ingredients/steps for a dish that repeats across days.

        Each menu chunk is generated by an independent API call (see generate_for_menu),
        so a dish repeated across chunk boundaries (e.g. the Mon/Wed/Fri afternoon snack)
        can drift — same title, different quantities/steps — even though the system
        prompt asks for an identical card every time. First occurrence wins; later
        occurrences of the same dish name get their body replaced with it, keeping only
        their own header line (which may carry day-specific annotations).
        """
        lines = content.split('\n')
        out: list = []
        seen: dict = {}
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            if line.startswith('### '):
                header = line
                j = i + 1
                body_lines: list = []
                while j < n and not lines[j].startswith('### ') and not re.match(r'^#{1,2} ', lines[j]):
                    body_lines.append(lines[j])
                    j += 1
                m = re.search(r'—\s*(.+)$', header)
                dish = m.group(1).strip() if m else None
                if dish:
                    if dish in seen:
                        out.append(header)
                        out.extend(seen[dish])
                    else:
                        seen[dish] = body_lines
                        out.append(header)
                        out.extend(body_lines)
                else:
                    out.append(header)
                    out.extend(body_lines)
                i = j
            else:
                out.append(line)
                i += 1
        return '\n'.join(out)

    @staticmethod
    def _split_menu_into_chunks(menu_content: str, chunk_size: int = 2) -> list:
        """Split menu into chunks of `chunk_size` days each."""
        day_re = re.compile(
            r'^#{1,2} [^a-zA-Z\n]{0,10}(LUNES|MARTES|MI[ÉE]RCOLES|JUEVES|VIERNES|S[ÁA]BADO|DOMINGO)',
            re.MULTILINE | re.IGNORECASE,
        )
        matches = list(day_re.finditer(menu_content))
        if not matches:
            return [menu_content]
        chunks = []
        for i in range(0, len(matches), chunk_size):
            start = matches[i].start()
            end = matches[i + chunk_size].start() if i + chunk_size < len(matches) else len(menu_content)
            chunks.append(menu_content[start:end].strip())
        return chunks

    def find_single(self, dish_name: str) -> str:
        user_message = f"Crea la tarjeta de receta completa para: **{dish_name}**"
        catalog = recipe_refs.catalog_compact()
        if catalog:
            user_message += (
                "\n\nCATÁLOGO DE RECETAS DE REFERENCIA DEL COCINERO:\n"
                f"{catalog}\n\n"
                "Si alguna referencia es el mismo platillo o uno muy afín (misma proteína y técnica, "
                "o mismo perfil de sabor), úsala como plantilla, adáptala a las reglas de arriba y "
                "agrega la línea '📌 Basado en: [nombre](URL)' con la URL de esa referencia. "
                "Si ninguna es afín, créala desde cero sin esa línea."
            )
        return self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=2000)
