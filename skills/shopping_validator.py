from .base_skill import BaseSkill, ValidationResult
from pathlib import Path


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

5. ASIGNACIÓN DE TIENDA: para cada fila, determina si la tienda asignada realmente vende ese ingrediente, consultando el criterio de tienda de abajo (y si hace falta, https://www.costco.com.mx/ o https://www.lacomer.com.mx/lacomer/#!/home?succId=449&succFmt=200):
   - Si la tienda asignada SÍ lo vende → mantener, Estado = ✅
   - Si la tienda asignada NO lo vende pero la otra tienda física sí → cambiar tienda, Estado = ⚠️ Corregido
   - Si ninguna tienda física lo vende → cambiar a "Amazon-MercadoLibre" (elige el más lógico), Estado = 🌐 Online
   Un error de tienda es una corrección aplicada en la tabla, no por sí solo motivo de RECHAZADO — pero cuéntalo en el reporte.

CRITERIO DE TIENDA:
COSTCO: pollo (pechuga/muslo), salmón, camarones congelados, atún en agua, res molida, huevos, leche, yogurt griego, mantequilla, queso crema, mozzarella, cheddar, parmesano Kraft, jitomate, cebolla, ajo, limones, aguacate, espinaca, zanahoria, pimiento, plátano, fresas, arroz, pasta regular, avena, aceite de oliva, aceite de coco, vinagre balsámico, soya Kikkoman, mostaza Dijon, garbanzos/frijoles en lata, leche de coco, caldo Kirkland, almendras, nueces, proteína whey, chile en polvo, especias secas comunes
CITY MARKET: pato, cordero, wagyu, bacalao, pulpo, callo de hacha, trucha, burrata, queso de cabra, brie, ricotta fresca, halloumi, mascarpone, crème fraîche, hierbas frescas premium, miso, mirin, sake, vinagre de arroz, pasta curry, za'atar, sumac, harissa, tahini artesanal, aceite de sésamo, hongos frescos, chiles secos especiales (mulato/negro/chihuacle/pasilla), chocolate de Oaxaca, pasta italiana premium
AMAZON/MERCADO LIBRE — cuando ningún supermercado lo tiene: ingredientes muy específicos importados, especias ultra-nicho (galanga fresca, hojas pandanus, pimienta szechuan, asafétida, pasta shrimp fermentado), miso premium de importación, vinagres especiales (champaña, jerez añejo), licores/vinos para cocinar inusuales, utensilios especiales, ingredientes coreanos/japoneses de nicho. En caso de duda entre Costco/City Market → City Market.

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

        user_message = (
            "Audita la siguiente lista de compras contra el menú, las recetas y el meal prep de la semana.\n\n"
            + "\n\n---\n\n".join(sections)
            + (f"\n\n---\n\n{totals_section}" if totals_section else "")
            + "\n\n---\n\nGenera el reporte completo siguiendo el formato indicado."
        )

        raw = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=16000)
        return self._parse_verdict_result(raw)

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
