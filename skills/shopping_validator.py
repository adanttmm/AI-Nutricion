from .base_skill import BaseSkill, ValidationResult
from pathlib import Path
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

5. ASIGNACIÓN DE TIENDA: para cada fila, determina si la tienda asignada realmente vende ese ingrediente.
   - Si el bloque "COSTCO — VERIFICADO POR SCRIPT" (más abajo, cuando esté presente) cubre ese ingrediente con resultado POSITIVO, eso es autoritativo — no la vuelvas a buscar, márcala ✅ Costco directamente. Un resultado NEGATIVO del script NO es autoritativo (ver nota de confianza asimétrica en ese bloque) — para esa fila sigue las reglas normales de abajo como si el script no la hubiera cubierto.
   - Para cualquier fila que el script no cubra o haya dado negativo (ingredientes City Market, Perecederos, o Despensa/Costco sin confirmación positiva) tienes una herramienta de búsqueda web real — úsala, no adivines:
     - Para ingredientes comunes que están claramente en el criterio de abajo (pollo, jitomate, arroz, etc.) puedes confiar en el criterio sin buscar.
     - Para CUALQUIER ingrediente que NO aparezca explícitamente en el criterio de abajo, o que sea una especialidad étnica/importada/de nicho (pastas de curry, ajíes, salsas asiáticas específicas, quesos poco comunes, hierbas o especias poco comunes en México, etc.), DEBES usar la búsqueda web para verificar si Costco México, City Market o La Comer realmente lo venden antes de decidir la tienda o marcarlo ✅. No asumas que "suena gourmet" significa que City Market lo tiene — confírmalo.
   - Si la verificación (script o búsqueda) confirma que la tienda asignada SÍ lo vende → mantener, Estado = ✅
   - Si la tienda asignada NO lo vende pero la otra tienda física sí (confirmado) → cambiar tienda, Estado = ⚠️ Corregido
   - Si no hay evidencia de que NINGUNA tienda física mexicana lo venda → cambiar a "Amazon-MercadoLibre" (elige el más lógico), Estado = 🌐 Online, y dilo explícitamente en Advertencias/Problemas — este es exactamente el caso que hace que una receta sea difícil de comprar en CDMX si se deja pasar.
   Un error de tienda es una corrección aplicada en la tabla, no por sí solo motivo de RECHAZADO — pero cuéntalo en el reporte. Cita brevemente qué encontraste (script o búsqueda) para cada ingrediente que verificaste (p. ej. "City Market Santa Fe no lista pasta de ají amarillo en su catálogo en línea — reasignado a Amazon/MercadoLibre").

CRITERIO DE TIENDA (referencia rápida para lo obviamente común — para todo lo demás, verifica con la búsqueda):
COSTCO: pollo (pechuga/muslo), salmón, camarones congelados, atún en agua, res molida, huevos, leche, yogurt griego, mantequilla, queso crema, mozzarella, cheddar, parmesano Kraft, jitomate, cebolla, ajo, limones, aguacate, espinaca, zanahoria, pimiento, plátano, fresas, arroz, pasta regular, avena, aceite de oliva, aceite de coco, vinagre balsámico, soya Kikkoman, mostaza Dijon, garbanzos/frijoles en lata, leche de coco, caldo Kirkland, almendras, nueces, proteína whey, chile en polvo, especias secas comunes
CITY MARKET: pato, cordero, wagyu, bacalao, pulpo, callo de hacha, trucha, burrata, queso de cabra, brie, ricotta fresca, halloumi, mascarpone, crème fraîche, hierbas frescas premium, miso, mirin, sake, vinagre de arroz, pasta curry (tailandesa, la más común), za'atar, sumac, harissa, tahini artesanal, aceite de sésamo, hongos frescos, chiles secos especiales (mulato/negro/chihuacle/pasilla), chocolate de Oaxaca, pasta italiana premium
AMAZON/MERCADO LIBRE — cuando la búsqueda confirma que ningún supermercado físico lo tiene: ingredientes muy específicos importados, especias ultra-nicho (galanga fresca, hojas pandanus, pimienta szechuan, asafétida, pasta shrimp fermentado, ají amarillo peruano, gochujang, etc.), miso premium de importación, vinagres especiales (champaña, jerez añejo), licores/vinos para cocinar inusuales, utensilios especiales, ingredientes coreanos/japoneses/peruanos de nicho. En caso de duda entre Costco/City Market tras buscar → City Market.

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
Tabla completa corregida con TODAS las columnas originales más una columna extra al final "Estado":
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
                  recipes_path: str = None, prep_path: str = None) -> ValidationResult:
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

        costco_section = self._build_costco_verification(shopping_content)
        if costco_section:
            sections.append(costco_section)

        user_message = (
            "Audita la siguiente lista de compras contra el menú, las recetas y el meal prep de la semana.\n\n"
            + "\n\n---\n\n".join(sections)
            + (f"\n\n---\n\n{totals_section}" if totals_section else "")
            + "\n\n---\n\nGenera el reporte completo siguiendo el formato indicado."
        )

        raw = self._call_claude(
            self.SYSTEM_PROMPT, user_message, max_tokens=16000,
            tools=[self._web_search_tool(max_uses=12)],
        )
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
        local headless-browser search (costco_scraper.py) instead of burning
        LLM web-search calls on them. Fails soft: if Chromium/Selenium isn't
        available or the lookup errors out, this just returns "" and the
        validator falls back to its normal web-search behavior for those
        rows too — never blocks the audit."""
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
            "autoritativo para esa fila (no la vuelvas a buscar, márcala ✅ Costco). Un resultado "
            "NEGATIVO NO significa 'Costco no lo vende' — el catálogo en línea de Costco no "
            "representa bien su surtido completo (ni todos los productos empacados tienen página "
            "propia). Para una fila NEGATIVA, sigue las reglas normales (criterio conocido de abajo "
            "o búsqueda web) en vez de reasignarla automáticamente — el script solo te ahorra "
            "buscar en los casos positivos, nunca decide un negativo por sí solo. Ingredientes no "
            "listados aquí siguen las reglas normales de búsqueda/criterio:"
        ]
        for name, r in results.items():
            if r.get("found") is None:
                lines.append(f"- {name}: no se pudo verificar ({r.get('error', 'error desconocido')}) — trátalo como no verificado, sigue las reglas normales.")
            elif r.get("found"):
                sample = "; ".join(r.get("top_matches", [])[:3])
                lines.append(f"- {name}: POSITIVO, sí aparece en costco.com.mx ({sample})" if sample else f"- {name}: POSITIVO, sí aparece en costco.com.mx")
            else:
                lines.append(f"- {name}: negativo en la búsqueda del sitio — no concluyente, verifica con el criterio conocido o búsqueda web antes de reasignar.")
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
