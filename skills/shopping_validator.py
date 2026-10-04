from .base_skill import BaseSkill, ValidationResult
from pathlib import Path
import os
import re


class ShoppingValidatorSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un nutriólogo clínico y experto en supermercados de Ciudad de México (Costco Interlomas/Santa Fe y City Market Santa Fe). Auditas listas de compras contra el menú, las recetas y el plan de meal prep de la semana con el mismo rigor con que se audita el cumplimiento nutricional — la lista de compras es lo que determina si la semana realmente se puede cocinar y comer conforme al plan del nutriólogo. Sé estricto: cualquier ingrediente faltante, inventado o con cantidad incorrecta significa que la semana NO se puede ejecutar tal como el plan nutricional la definió.

FUENTE DE VERDAD PARA CANTIDADES: se te da una tabla "TOTALES SEMANALES CALCULADOS" con las sumas exactas (calculadas por código a partir de las recetas, no estimadas) de cada ingrediente en gramos crudos, por persona. Esa tabla es autoritativa — NO la recalcules ni la reestimes. La columna "Necesario" de la lista de compras debe corresponder a la suma ATM+IOB (+3er comensal donde aplique) de esa tabla.

VERIFICA ESTOS PUNTOS EN ORDEN:

1. COMPLETITUD: ¿Todos los ingredientes que aparecen en el menú, las recetas y el meal prep de la semana están en la lista? Cualquier ingrediente usado y ausente de la lista es un ❌ Problema Crítico (elemento ausente) — la semana no se puede cocinar sin él.

2. SIN INVENTOS: ¿Hay algún ingrediente en la lista que NO se usa en el menú, las recetas ni el meal prep? Repórtalo como ❌ Problema Crítico (ingrediente inventado) — infla la compra y el gasto sin motivo. Elimínalo de la tabla corregida.

3. CANTIDADES ("Necesario"): Para cada ingrediente que aparezca en la tabla de TOTALES SEMANALES, compara la columna "Necesario" de la lista contra la suma ATM+IOB (+3er comensal si el ingrediente se usa en comida de martes/miércoles/viernes) de esa tabla:
   - Coincide dentro de ±10% (tolerancia de redondeo) → correcto.
   - Si NO coincide, repórtalo como ❌ Problema Crítico (discrepancia de cantidad), citando el número exacto de la lista vs. el número exacto de la tabla, y corrige la cifra en la tabla final.

4. COLUMNA "Comprar" (ajuste, no exceso oculto): "Comprar" debe ser ≥ "Necesario", redondeado solo a presentación comercial (Despensa) o unidad mínima real de venta (Perecedero). Si "Comprar" excede "Necesario" en más de 15% para un Perecedero sin que la nota de "Posibles sobras" lo explique, repórtalo como ⚠️ Advertencia (no crítico, pero corrígelo si es evidente).

5. ASIGNACIÓN DE TIENDA (verificación SUAVE — nunca causa RECHAZADO, nunca cambia el menú ni las cantidades "Necesario"; no tienes búsqueda web, no la necesitas):
   - Si el bloque "COSTCO — VERIFICADO POR SCRIPT" (más abajo, cuando esté presente) da POSITIVO para la fila → Estado = ✅ Costco. Sus títulos de producto muestran la PRESENTACIÓN real que vende Costco: si esa presentación es mucho mayor que "Necesario" (más de ~5× y no es algo que dure meses en despensa), cambia la Tienda a City Market y anota "⚠️ Presentación Costco muy grande (<presentación>)"; si la presentación es razonable, ajusta "Comprar" a esa presentación real.
   - Un NEGATIVO del script NO es concluyente (el catálogo en línea de Costco es incompleto) — trátalo como si el script no lo hubiera cubierto.
   - Filas sin confirmación del script: si el ingrediente está claramente en el criterio de abajo para la tienda asignada → Estado = ✅ (criterio). Si no lo está (especialidad, importado, poco común) → deja la tienda más lógica según el criterio y Estado = ❔ Confirmar en tienda. No inventes evidencia ni marques ✅ sin ella.
   - Perecederos asignados a Costco: Costco vende producto fresco en paquetes grandes. Si "Comprar" es una cantidad chica que Costco no vende así (un manojo, una cabeza de ajo, un trozo de jengibre, <300 g de una verdura), cambia la Tienda a City Market y anótalo como ⚠️ Corregido.
   - Solo usa "Amazon-MercadoLibre" (Estado = 🌐 Online) para especialidades de nicho que claramente no se venden en supermercados de CDMX (ver criterio de abajo).
   Los cambios de tienda se aplican en la tabla y se listan en Advertencias; nunca son motivo de RECHAZADO.

CRITERIO DE TIENDA (referencia para asignar sin verificación):
COSTCO: pollo (pechuga/muslo), salmón, camarones congelados, atún en agua, res molida, huevos, leche, yogurt griego, mantequilla, queso crema, mozzarella, cheddar, parmesano Kraft, jitomate, cebolla, ajo, limones, aguacate, espinaca, zanahoria, pimiento, plátano, fresas, arroz, pasta regular, avena, aceite de oliva, aceite de coco, vinagre balsámico, soya Kikkoman, mostaza Dijon, garbanzos/frijoles en lata, leche de coco, caldo Kirkland, almendras, nueces, proteína whey, chile en polvo, especias secas comunes
CITY MARKET: pato, cordero, wagyu, bacalao, pulpo, callo de hacha, trucha, burrata, queso de cabra, brie, ricotta fresca, halloumi, mascarpone, crème fraîche, hierbas frescas premium, miso, mirin, sake, vinagre de arroz, pasta curry (tailandesa, la más común), za'atar, sumac, harissa, tahini artesanal, aceite de sésamo, hongos frescos, chiles secos especiales (mulato/negro/chihuacle/pasilla), chocolate de Oaxaca, pasta italiana premium
AMAZON/MERCADO LIBRE — especialidades de nicho que los supermercados de CDMX normalmente no tienen: ingredientes muy específicos importados, especias ultra-nicho (galanga fresca, hojas pandanus, pimienta szechuan, asafétida, pasta shrimp fermentado, ají amarillo peruano, gochujang, etc.), miso premium de importación, vinagres especiales (champaña, jerez añejo), licores/vinos para cocinar inusuales, utensilios especiales, ingredientes coreanos/japoneses/peruanos de nicho. En caso de duda entre Costco/City Market → City Market.

VEREDICTO: RECHAZADO si existe AL MENOS UN ❌ Problema Crítico (elemento ausente, ingrediente inventado, o discrepancia de cantidad fuera de ±10%). Errores de tienda y advertencias de "Comprar" nunca causan RECHAZADO por sí solos — se corrigen en la tabla y se listan como cambios.

FORMATO DE RESPUESTA — usa EXACTAMENTE esta estructura, sin variaciones:

VEREDICTO: APROBADO
(o VEREDICTO: RECHAZADO)

FEEDBACK_GENERADOR:
ninguno
(o, si RECHAZADO, lista específica y accionable para quien regenera la lista de compras, un punto por problema:)
- Falta "camarón" (usado en Cena Martes, receta X) — agregar ~340g a la lista, tienda Costco.
- "Salmón" inventado — no aparece en menú/recetas/prep — eliminar de la lista.
- "Pechuga de pollo" Necesario=1200g en la lista vs. 1450g en TOTALES SEMANALES — corregir a 1450g.

REPORTE_HUMANO:
## 🛒 Tabla Corregida
Tabla completa corregida con TODAS las columnas originales más una columna extra al final "Estado". ESTA TABLA ES LA LISTA FINAL (no habrá regeneración): aplica en ella TODAS las correcciones — agrega los ingredientes faltantes, elimina los inventados, corrige cantidades y tiendas — y conserva la sección "📋 Posibles sobras" si la lista original la tenía:
| Ingrediente | Tipo | Necesario | Comprar | Uso | Tienda | Estado |

## ✅ Correcto
Resumen breve de lo que ya estaba bien.

## ⚠️ Advertencias
Correcciones de tienda aplicadas y advertencias de exceso en "Comprar" (no críticas).

## ❌ Problemas Críticos
Elementos ausentes, ingredientes inventados y discrepancias de cantidad — cita ambos números en cada discrepancia. "ninguno" si no hay.

## 📝 Veredicto
Una línea: APROBADO o RECHAZADO y el motivo principal."""

    def validate(self, shopping_path: str, menu_path: str = None,
                  recipes_path: str = None, prep_path: str = None, week_notes: str = "") -> ValidationResult:
        shopping_content = Path(shopping_path).read_text(encoding="utf-8")

        sections = [f"LISTA DE COMPRAS A AUDITAR:\n{shopping_content}"]

        if menu_path and Path(menu_path).exists():
            sections.append(f"MENÚ DE LA SEMANA:\n{Path(menu_path).read_text(encoding='utf-8')}")

        totals_section = ""
        if recipes_path and Path(recipes_path).exists():
            recipes_content = Path(recipes_path).read_text(encoding="utf-8")
            sections.append(f"RECETAS (ingredientes y cantidades de referencia):\n{recipes_content}")
            totals_section = self._build_totals_reference(recipes_content)

        if prep_path and Path(prep_path).exists():
            sections.append(
                f"PLAN DE MEAL PREP (puede añadir ingredientes de salsas/preparaciones no listados en el menú):\n"
                f"{Path(prep_path).read_text(encoding='utf-8')}"
            )

        if week_notes:
            sections.append(
                "NOTA DE LA SEMANA DEL COCINERO (inventario en casa / sobrantes):\n" + week_notes + "\n"
                "Lo que ya hay en casa se descuenta de \"Comprar\" (no de \"Necesario\") — un Comprar menor que "
                "Necesario por esa razón es CORRECTO. Si la lista compra algo que la nota dice que ya hay en "
                "cantidad suficiente, corrígelo en la tabla (Comprar = \"0 — en casa\")."
            )

        costco_section = self._build_costco_verification(shopping_content)
        if costco_section:
            sections.append(costco_section)

        user_message = (
            "Audita la siguiente lista de compras contra el menú, las recetas y el meal prep de la semana.\n\n"
            + "\n\n---\n\n".join(sections)
            + (f"\n\n---\n\n{totals_section}" if totals_section else "")
            + "\n\n---\n\nGenera el reporte completo siguiendo el formato indicado."
        )

        raw = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=16000)
        return self._parse_verdict_result(raw)

    _ROW_RE = re.compile(
        r"^\|\s*(?P<ingrediente>[^|]+?)\s*\|\s*(?P<tipo>[^|]+?)\s*\|"
        r"\s*[^|]*\|\s*[^|]*\|\s*[^|]*\|\s*(?P<tienda>[^|]+?)\s*\|"
    )

    @classmethod
    def _parse_costco_despensa_rows(cls, shopping_content: str) -> list[str]:
        """Extract ingredient names claimed as Despensa + Costco in the
        shopping-list table — the only rows the Costco scraper is reliable
        for (see costco_scraper.py: it can't see fresh warehouse perishables,
        only items with their own online SKU)."""
        names = []
        for line in shopping_content.splitlines():
            m = cls._ROW_RE.match(line.strip())
            if not m:
                continue
            tipo = m.group("tipo").strip().lower()
            tienda = m.group("tienda").strip().lower()
            ingrediente = m.group("ingrediente").strip()
            if tipo == "despensa" and tienda == "costco" and ingrediente.lower() != "ingrediente":
                names.append(ingrediente)
        return names

    @classmethod
    def _build_costco_verification(cls, shopping_content: str) -> str:
        """Pre-verify Despensa/Costco rows against costco.com.mx via a free,
        local headless-browser search (costco_scraper.py, cached). Fails soft:
        if Chromium/Selenium isn't available or the lookup errors out, this
        returns "" and those rows fall back to the store criterion — never
        blocks the audit.

        SKIP_COSTCO_SCRAPER=1 forces that same fallback path — an escape
        hatch to isolate the scraper as a variable when debugging."""
        if os.environ.get("SKIP_COSTCO_SCRAPER"):
            return ""
        names = cls._parse_costco_despensa_rows(shopping_content)
        if not names:
            return ""

        try:
            from . import costco_scraper
            results = costco_scraper.lookup_many(names)
        except Exception:
            return ""

        lines = [
            "COSTCO — VERIFICADO POR SCRIPT (búsqueda real en costco.com.mx, no adivinado). "
            "IMPORTANTE — confianza asimétrica: un resultado POSITIVO es evidencia fuerte y es "
            "autoritativo para esa fila (márcala ✅ Costco). Un resultado "
            "NEGATIVO NO significa 'Costco no lo vende' — el catálogo en línea de Costco no "
            "representa bien su surtido completo. Para una fila NEGATIVA sigue el criterio del punto 5. "
            "Los títulos de los positivos muestran la presentación real a la venta:"
        ]
        for name, r in results.items():
            if r.get("found") is None:
                lines.append(f"- {name}: no se pudo verificar ({r.get('error', 'error desconocido')}) — trátalo como no verificado, sigue las reglas normales.")
            elif r.get("found"):
                sample = "; ".join(r.get("top_matches", [])[:3])
                lines.append(f"- {name}: POSITIVO, sí aparece en costco.com.mx ({sample})" if sample else f"- {name}: POSITIVO, sí aparece en costco.com.mx")
            else:
                lines.append(f"- {name}: negativo en la búsqueda del sitio — no concluyente, sigue el criterio del punto 5.")
        return "\n".join(lines)

    @classmethod
    def _build_totals_reference(cls, recipes_content: str) -> str:
        """Format the shared code-computed ingredient totals as an authoritative
        reference block for the audit prompt (see BaseSkill._ingredient_totals_table)."""
        table = cls._ingredient_totals_table(recipes_content)
        if not table:
            return ""
        return (
            "TOTALES SEMANALES CALCULADOS (crudo, suma exacta por código a partir de "
            "las recetas — referencia autoritativa para el punto 3, no la recalcules):\n"
            f"{table}"
        )
