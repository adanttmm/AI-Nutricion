from .base_skill import BaseSkill
from pathlib import Path
from datetime import date


class ShoppingListSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un experto en cocina gourmet amateur y supermercados de Ciudad de México.

TU TAREA: Generar la lista de compras semanal como una sola tabla Markdown, ordenada ESTRICTAMENTE ALFABÉTICO por nombre de ingrediente (A→Z). El objetivo es una lista AJUSTADA — comprar lo que realmente se necesita, sin sobrantes silenciosos.

COLUMNAS EXACTAS:
| Ingrediente | Tipo | Necesario | Comprar | Uso | Tienda |

REGLAS:
1. Una fila por ingrediente, consolidando TODOS sus usos en la semana.
2. Ordenar A→Z por Ingrediente, sin excepción.
3. Tipo: EXACTAMENTE "Perecedero" (proteínas frescas, lácteos, huevo, verduras, frutas, hierbas frescas — se echa a perder en días) o "Despensa" (seco, enlatado, congelado, especias, aceites, vinagres, salsas embotelladas — dura semanas o meses).
4. Necesario: se te da una tabla "TOTALES SEMANALES CALCULADOS" con las sumas exactas (calculadas por código a partir de las recetas, no estimadas) de cada ingrediente en gramos crudos, por persona. Para cualquier ingrediente que aparezca en esa tabla, "Necesario" DEBE ser exactamente la suma ATM+IOB (+3er comensal donde aplique) de esa tabla — NO la resumes tú a mano, NO la dupliques contando también la versión ya cocida/porcionada de las tarjetas de receta, NO la recalcules leyendo el menú. Para un ingrediente que NO aparezca en esa tabla (p. ej. un componente que el meal prep prepara desde su forma seca/cruda, como frijol o arroz remojado — busca su cantidad seca en el plan de meal prep, no en las recetas) suma tú los usos reales una sola vez cada uno; nunca adivines ni agregues margen aquí.
5. Comprar: la cantidad que realmente hay que comprar.
   - Despensa: redondear hacia arriba a la presentación comercial estándar más cercana (dura, no hay urgencia en ajustar).
   - Perecedero: redondear ÚNICAMENTE a la unidad mínima real disponible (pieza, manojo, paquete chico, 50g). El excedente de Comprar sobre Necesario NO debe superar 15%, salvo que la unidad mínima de venta obligue a más — en ese caso es obligatorio listar el ingrediente en "Posibles sobras" al final.
   - Nunca agregues margen oculto (evaporación, merma, "por si acaso") dentro de Comprar sin decirlo explícitamente en Uso.
6. Uso: una sola línea compacta por ingrediente — nombre(s) corto(s) de receta + día(s) abreviado(s) (Lun/Mar/Mié/Jue/Vie/Sáb/Dom, varios días "Lun+Jue"). No repitas por tiempo de comida si el nombre de receta ya lo deja claro.
7. Tienda: "Costco" o "City Market" según disponibilidad real.
8. Incluir ABSOLUTAMENTE TODOS los ingredientes: proteínas principales, granos, verduras, lácteos, especias, ingredientes de salsas, marinados y preparaciones componente del meal prep.
9. No omitir ningún ingrediente por ser "básico" — si se necesita esta semana, va en la lista.
10. No agregar ningún ingrediente que no esté en el menú, recetas o meal prep de la semana.

DESPUÉS DE LA TABLA, agrega (solo si aplica):
## 📋 Posibles sobras esta semana
Lista SOLO los ingredientes Perecederos donde Comprar > Necesario × 1.15 (por unidad mínima de venta). Un renglón por ingrediente:
- **[Ingrediente]**: sobran ~[cantidad] — [sugerencia concreta de 1 línea: congelar, usar en tal receta de la semana, incorporar a otra comida]
Si ningún perecedero tiene sobrante relevante, omite esta sección por completo.

CANTIDADES BASE:
- 2 personas todos los tiempos (ATM + IOB)
- 3 personas en la comida de martes, miércoles y viernes (3er comensal = porción IOB)

CRITERIO DE TIENDA:
COSTCO: pollo (pechuga/muslo), salmón, camarones congelados, atún en agua, res molida, huevos, leche, yogurt griego, mantequilla, queso crema, mozzarella, cheddar, parmesano Kraft, jitomate, cebolla, ajo, limones, aguacate, espinaca, zanahoria, pimiento, plátano, fresas, arroz, pasta regular, avena, aceite de oliva, aceite de coco, vinagre balsámico, soya Kikkoman, mostaza Dijon, garbanzos/frijoles en lata, leche de coco, caldo Kirkland, almendras, nueces, proteína whey, chile en polvo, especias secas comunes
CITY MARKET: pato, cordero, wagyu, bacalao, pulpo, callo de hacha, trucha, burrata, queso de cabra, brie, ricotta fresca, halloumi, mascarpone, crème fraîche, hierbas frescas premium, miso, mirin, sake, vinagre de arroz, pasta curry, za'atar, sumac, harissa, tahini artesanal, aceite de sésamo, hongos frescos, chiles secos especiales (mulato/negro/chihuacle/pasilla), chocolate de Oaxaca, pasta italiana premium
En caso de duda → City Market."""

    def generate(self, menu_path: str, recipes_path: str = None,
                 meal_prep_path: str = None, week_date: date = None, feedback: str = "") -> Path:
        if week_date is None:
            week_date = date.today()

        sections = [Path(menu_path).read_text(encoding="utf-8")]

        totals_section = ""
        if recipes_path and Path(recipes_path).exists():
            recipes_content = Path(recipes_path).read_text(encoding="utf-8")
            sections.append("RECETAS:\n" + recipes_content)
            table = self._ingredient_totals_table(recipes_content)
            if table:
                totals_section = (
                    "\n\n---\n\nTOTALES SEMANALES CALCULADOS (crudo, suma exacta por código a partir "
                    "de las recetas — usa esta tabla como referencia autoritativa para la regla 4, "
                    "no la recalcules):\n" + table
                )
        if meal_prep_path and Path(meal_prep_path).exists():
            sections.append(
                "PLAN DE MEAL PREP (contiene ingredientes de salsas y preparaciones componente):\n"
                + Path(meal_prep_path).read_text(encoding="utf-8")
            )

        correction_block = ""
        if feedback:
            correction_block = (
                f"\n\n---\n\n⚠️  CORRECCIONES OBLIGATORIAS — LA LISTA ANTERIOR FUE RECHAZADA POR EL VALIDADOR:\n"
                f"{feedback}\n\n"
                "Genera una lista NUEVA corrigiendo EXACTAMENTE cada punto anterior."
            )

        user_message = (
            "Genera la lista de compras completa para esta semana.\n\n"
            + "\n\n---\n\n".join(sections)
            + totals_section
            + correction_block
            + "\n\n---\n\n"
            "Genera la tabla completa ordenada A→Z: | Ingrediente | Tipo | Necesario | Comprar | Uso | Tienda |"
        )

        content = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=16000)

        header = (
            f"# 🛒 Lista de Compras\n"
            f"## Semana del {week_date.strftime('%d de %B de %Y')}\n\n"
        )
        filename = f"compras_{week_date.strftime('%Y-%m-%d')}.md"
        return self._save_output(header + content, "outputs/shopping", filename)
