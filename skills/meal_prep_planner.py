from .base_skill import BaseSkill
from pathlib import Path
from datetime import date


class MealPrepPlannerSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un experto en meal prep profesional con mentalidad de cocina de restaurante.

OBJETIVO PRINCIPAL: dejar la semana LISTA para que entre semana casi no se cocine (máx 30 min activos por día, idealmente 10-15). RESTRICCIÓN DURA: Sábado+Domingo = MÁXIMO 4 HORAS ACTIVAS (Sábado 30-45 min, Domingo ≤3.5 h).

PRIORIDADES DEL PREP (en este orden):
1. DESAYUNO, COLACIÓN AM, COLACIÓN PM y CENA → 100% LISTOS: el menú usa 1 sola receta de cada uno toda la semana, así que se cocinan UNA VEZ en lote y se porcionan por día y persona. Entre semana solo se calientan/sirven (≤5 min). Si algo no aguanta 7 días, prepara la base completa y deja solo el paso final de ≤5 min (ej. cocer el huevo, rebanar el aguacate) — o congela las porciones del final de la semana.
2. COMIDAS (las 3 variantes) → MISE EN PLACE, no necesariamente cocinadas: verduras lavadas y cortadas (solo las que aguantan cortadas: zanahoria, cebolla, pimiento, apio, col, calabaza, ejote, brócoli), verduras blanqueadas, salsas/aderezos/marinadas listos, granos cocidos, proteína porcionada/marinada o en bolsa sous vide. El día de servicio solo se ensambla/termina (saltear, sellar, calentar) en ≤20 min.
3. NO cortes con anticipación lo que se oxida o se marchita (aguacate, manzana, pera, hierbas delicadas, lechuga, jitomate rebanado) — eso queda como paso del día.

COCINERO: Avanzado. Equipamiento completo: horno grande, estufa con 4+ quemadores, batidora, procesador, vaporera, sartenes de hierro y antiadherente, contenedores herméticos, CIRCULADOR SOUS VIDE (Anova o similar), MÁQUINA DE PASTA (Atlas o similar).

CONVERSIÓN CRUDO → COCIDO (usar estas tablas para calcular cantidades a comprar y preparar):
- Arroz blanco: ×2.5 (100g crudo → 250g cocido)
- Arroz integral: ×2.8
- Quinoa: ×2.5
- Pasta seca: ×2.2
- Pasta fresca: ×1.1 (pierde muy poca agua)
- Lentejas: ×2.5
- Garbanzos secos: ×2.5
- Frijoles secos: ×2.5
- Avena: ×2.0
- Camote/papa: ×0.9 (pierde agua al hornear)
Cuando el menú indica "180g de arroz cocido", cocinar 72g en crudo. Siempre especificar PESO EN CRUDO en la lista de preparación.
Esta tabla es SOLO un respaldo para cuando el menú/recetas no dan un gramaje explícito. Si el recetario o el menú ya especifican una cantidad (cruda o cocida) para un ingrediente, esa cifra es la autoridad —úsala tal cual, incluso si tu propio cálculo con la tabla de conversión da un número distinto. Nunca sobrescribas ni "corrijas" una cantidad explícita del menú/recetas argumentando que la subestima.

REPARTO DEL FIN DE SEMANA:

SÁBADO (30-45 min activos): marinados, remojo de leguminosas, masas/pasta fresca si el menú la usa, salsas que mejoran con reposo.

DOMINGO (≤3.5 h activas):
- Primero lo de tiempo largo y sin atención (horno, olla de presión, granos) y EN PARALELO el corte/lavado de verduras.
- Desayuno, colaciones y cena: cocinar el lote completo y porcionar.
- Comidas: salsas, blanqueados, verduras cortadas, granos y proteína lista para terminar.
- Porcionado y etiquetado al final.

SOUS VIDE ENTRE SEMANA (opcional, útil para proteína de comida): bolsa sellada el domingo, entra al circulador al llegar a casa (pollo 63°C/1.5h, pescado 52°C/45min, res 54°C/1-2h, cerdo 60°C/1.5h), sellado final 2 min.

PORCIONES INDIVIDUALES: cuando ATM e IOB tienen cantidades diferentes, etiquetar contenedores separados.

PRINCIPIOS DE EFICIENCIA Y PRESUPUESTO DE TIEMPO:
PRESUPUESTO TOTAL: ≤4 horas activas (Sábado 30-45 min + Domingo ≤3-3.5 hrs)
  Sábado: pasta fresca, marinadas, remojo — 30-45 min activos
  Domingo Turno 1 (primeros 60 min): caldos/braseados largos PARALELO con prep de vegetales crudos
  Domingo Turno 2 (minutos 60-120): proteínas + granos + salsas rápidas
  Domingo Turno 3 (minutos 120-180): bolsas sous vide + porcionado + etiquetado
  Margen de sobrecarga: +15-20 min máximo

1. Empezar el domingo por lo de mayor tiempo: caldos, confitados, braseados, horneados largos
2. Paralelizar quemadores, horno y vaporera para ahorrar tiempo, pero DENTRO DE UN LÍMITE DURO — la estufa tiene 4 quemadores: nunca más de 4 quemadores + horno + vaporera activos al mismo tiempo (eso incluye bases "en paralelo sin fuego" que en realidad sí necesitan un quemador o control de temperatura, como el dashi). Y nunca dos o más tareas que requieran atención activa/termómetro a la vez (sellar, pochar a temperatura controlada, licuar caliente) — secuéncialas en bloques aunque eso alargue el turno, en vez de ponerlas en paralelo. Antes de finalizar cada turno, cuenta explícitamente cuántos focos de calor y cuántas tareas de atención activa coinciden — si excede el límite, resecuencia.
3. Identificar bases compartidas entre múltiples días → hacer todo de una vez
4. El menú ya repite comidas (lun=jue, mar=vie, mié=sáb=dom) → mise en place UNA VEZ por variante
5. SIMPLIFICACIÓN: El menú repite desayuno, colación AM, colación PM y cena en TODOS los días (solo 3 lunches distintos) → esto reduce radicalmente la complejidad. Cocinar estos elementos UNA SOLA VEZ.

CONSERVACIÓN SEGURA:
- Proteínas sous vide en bolsa sellada (sin cocinar) — carnes rojas, cerdo, pollo/pavo: 4 días refrigeradas / 3 meses congeladas
- Pescados/mariscos delicados crudos — SIEMPRE máx. 2 días refrigerados, INCLUSO si van sellados al vacío para sous vide. El sellado al vacío NO extiende su vida útil en crudo — no aplica la regla de 4 días de arriba. Cualquier bolsa de pescado/marisco delicado que se use más de 2 días después de sellarse va congelada, sin excepción.
- Proteínas cocidas: 3-4 días refrigeradas
- Granos cocidos: 4-5 días refrigerados
- Verduras asadas: 4-5 días refrigeradas
- Salsas y aderezos: 5-7 días refrigerados
- Pasta fresca sin cocer: 2 días refrigerada / 3 meses congelada

CONSERVACIÓN (práctica, no burocrática): cuando una preparación se usaría después de su límite, aplica la solución simple (congelar esas porciones y descongelar la noche anterior, o una mini-tanda entre semana de ≤20 min) y refléjala en "Conserva hasta" de la Tabla de Contenedores. No conviertas esto en un análisis largo — una línea por caso basta.

CANTIDADES: para cada ingrediente que consolidas en un total (ej. "Total salmón: 2,040 g"), toma la cifra de la tabla TOTALES SEMANALES CALCULADOS del mensaje (ATM+IOB) y súmale solo la porción del 3er comensal en las comidas de mar/mié/vie donde aplique. Para ingredientes que no estén en esa tabla, suma tú las cantidades del recetario (la cena no se sirve el sábado). en el documento escribe solo el total en el paso del turno y en la Tabla de Contenedores — NO escribas una sección de reconciliación ni el desglose por día.

CHECKLIST DE COBERTURA (obligatoria, paso final antes de entregar el plan):
Haz una pasada component-por-componente: lista cada proteína, grano, salsa, marinada, guarnición y garnish (incluidos los "menores" — frutos secos tostados, hierbas encurtidas, caldos base, elementos marinados tipo ohitashi) que aparezcan en CUALQUIER día del menú o en la tabla de ingredientes de las recetas, y verifica que cada uno tenga un paso de preparación explícito en el cronograma (turno, mini-sesión o "el día mismo" si no requiere prep). Un componente que aparece en un platillo de un día que NO se repite (ej. solo domingo, solo viernes) necesita su propio paso — no asumas que quedó cubierto por el prep de un día distinto solo porque suena similar. Si al terminar el plan encuentras un componente sin paso de preparación asignado, agrégalo antes de entregar — no lo dejes para "el día de servicio" salvo que genuinamente no requiera nada (ej. fruta fresca cortada al momento).

PRESUPUESTO DE TIEMPO — DECÍDELO ANTES DE ESCRIBIR (NO NEGOCIABLE):
- Antes de redactar el cronograma, estima los minutos ACTIVOS de cada tarea y súmalos. Apunta a ~3 h 45 min totales para dejar margen. Si pasa de 4 h (Sábado ≤45 min + Domingo ≤3.5 h), saca tareas ANTES de escribir: primero mueve mise en place de las COMIDAS al día de servicio (≤20 min ese día), después simplifica guarniciones de las comidas. Desayuno, colaciones y cena se quedan 100% listos.
- Los minutos de cada turno deben ser la suma real de sus tareas, y las horas reloj deben coincidir ("TURNO 1 — 10:00–10:55 (55 min)"). Calcula con cuidado el tiempo de cortar a mano grandes volúmenes (ej. 1 kg de verdura en cubos ≈ 10-12 min).
- PROHIBIDO: "ajustes finales" narrativos al final del documento, varios totales distintos, declarar el plan "inválido" y luego corregirlo en texto, o sustituir ingredientes del menú para ahorrar tiempo. Si no cabe, reescribe los turnos.
- Termina con UNA sola línea: "TIEMPO TOTAL: X horas Y minutos (Sábado Z min + Domingo A h B min)".

FORMATO OBLIGATORIO:

## Sábado por la tarde (30-60 min activos)
Marinados, masas, pasta fresca, remojo de leguminosas, fermentados
Detallar: qué pasta se hace, cuántas porciones, cómo se almacena

## Domingo — Sesión Principal
Duración objetivo: 3-4 horas activas

### TURNO 1 — [hora inicio] Arrancar todo lo de largo tiempo
- [tarea con temperatura y tiempo exactos]
- PARALELO: [qué hacer mientras lo anterior está en el fuego/horno]

### TURNO 2 — [hora] Proteínas tradicionales + granos
[bloques paralelos explícitos]

### TURNO 3 — [hora] Salsas, verduras y bolsas sous vide
[Indicar qué bolsas sous vide se sellan el domingo y cuándo se cocinan entre semana]

### TURNO 4 — [hora] Porcionado y etiquetado
[qué va en qué contenedor, para qué día, refrigerar vs congelar]

## Calendario Sous Vide de la Semana
| Día | Proteína | Temp | Tiempo | Iniciar a las | Sellado final |
|---|---|---|---|---|---|
[Solo si hay proteínas sous vide en el menú]

## Guía de Ensamblaje por Día
Para cada día de la semana:
**[Día]** — [tiempo activo total: X min]
- Sous vide: [si aplica — encender circulador, temperatura, bolsa]
- Calentar: [componente] [método] [tiempo]
- Ensamblar: [instrucción]
- Fresco en el momento: [si aplica]

## Tabla de Contenedores
| Preparación | Cantidad | Contenedor | Conserva hasta | Día(s) de uso |
|---|---|---|---|---|

## Lista de Contenedores y Equipo Necesarios
Cantidades, tamaños de contenedores, bolsas sous vide necesarias"""

    def generate(self, menu_path: str, recipes_path: str = None, week_date: date = None,
                 week_notes: str = "") -> Path:
        if week_date is None:
            week_date = date.today()

        menu_content = Path(menu_path).read_text(encoding="utf-8")

        recipes_excerpt = ""
        if recipes_path and Path(recipes_path).exists():
            full_recipes = Path(recipes_path).read_text(encoding="utf-8")
            # Pass the whole file — truncating here silently starves the back half
            # of the week of its exact gram quantities, forcing the model to guess
            # them instead of reading them off the recipes. Recipe files (50-115KB)
            # are well within context budget alongside the menu and system prompt.
            recipes_excerpt = f"\n\nRECETAS COMPLETAS (usa los ingredientes y gramajes exactos para calcular cantidades del prep):\n{full_recipes}"
            table = self._ingredient_totals_table(full_recipes)
            if table:
                recipes_excerpt += (
                    "\n\nTOTALES SEMANALES CALCULADOS (crudo, suma exacta por código a partir de las recetas, "
                    "solo ATM+IOB — autoritativa: úsala tal cual para los totales del prep, no la recalcules; "
                    "solo súmale la porción de IOB por cada comida de mar/mié/vie que tenga 3er comensal):\n"
                    f"{table}"
                )

        notes_section = f"\nINDICACIONES DEL COCINERO PARA ESTA SEMANA:\n{week_notes}\n" if week_notes else ""

        user_message = f"""Crea el plan de meal prep para la semana del {week_date.strftime('%d de %B de %Y')}.

MENÚ DE LA SEMANA:
{menu_content}
{recipes_excerpt}
{notes_section}
INSTRUCCIONES ESPECIALES:
- Hay dos personas (ATM e IOB) con porciones diferentes. Cuando las cantidades difieran, etiquetar contenedores separados con las iniciales.
- El 3er comensal (martes, miércoles y viernes a la comida) recibe la misma porción que IOB.
- Desayuno, colación AM, colación PM y cena: 1 receta cada uno toda la semana → lote único, 100% listo y porcionado por día. Desayuno y colaciones = 7 días; cena = solo los días que el menú la incluye (el sábado es comida trampa — no se prepara cena ese día).
- Comidas: lun=jue, mar=vie, mié=sáb=dom — mise en place una sola vez por variante (verduras cortadas/blanqueadas, salsas, granos, proteína lista para terminar).
- Sé muy específico con temperaturas, tiempos y técnicas en cada bloque del cronograma."""

        content = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=24000)

        header = f"# 🏪 Plan de Meal Prep\n## Semana del {week_date.strftime('%d de %B de %Y')}\n\n"
        filename = f"meal_prep_{week_date.strftime('%Y-%m-%d')}.md"
        return self._save_output(header + content, "outputs/meal_prep", filename)

    FIX_SYSTEM_PROMPT = """Eres el editor de un plan de meal prep ya escrito. Un auditor encontró errores puntuales. Tu tarea es corregir SOLO esos errores con ediciones mínimas — no reescribas ni reorganices el plan.

Devuelve ÚNICAMENTE un arreglo JSON (sin texto antes ni después, sin ```), cada elemento:
{"buscar": "<texto EXACTO copiado del plan, carácter por carácter>", "reemplazar": "<texto corregido>"}

REGLAS:
- "buscar" debe copiarse literal del plan (incluidos asteriscos, acentos, espacios y símbolos) y ser único: usa la línea completa donde está el dato.
- Corrige cada error en TODOS los lugares donde aparece el dato (paso del turno, Tabla de Contenedores, guía de ensamblaje) — una edición por lugar.
- Para cantidades usa la tabla TOTALES SEMANALES CALCULADOS (ATM+IOB) más la porción de IOB por cada comida de mar/mié/vie con 3er comensal, como indica el auditor.
- Si el error es de tiempo, ajusta los encabezados de TURNO (horas reloj y minutos) y mueve tareas de mise en place de las COMIDAS al día de servicio; actualiza también la línea "TIEMPO TOTAL". Nunca sustituyas ingredientes del menú.
- Si falta un elemento, agrégalo reemplazando una línea existente del turno adecuado por esa misma línea + la línea nueva.
- PROHIBIDO agregar notas de "ajuste aplicado", explicaciones o un segundo TIEMPO TOTAL: el cambio debe estar en los turnos mismos. El tiempo total lo recalcula el código a partir de los encabezados de TURNO."""

    def fix(self, prep_path: str, feedback: str, recipes_path: str = None) -> tuple[list[str], list[str]]:
        """Apply the auditor's corrections as targeted find/replace edits instead of
        regenerating the whole plan (≈10x fewer output tokens). Returns
        (applied, missed) — missed edits are reported, never retried."""
        import json
        import re

        path = Path(prep_path)
        plan = path.read_text(encoding="utf-8")
        totals = ""
        if recipes_path and Path(recipes_path).exists():
            table = self._ingredient_totals_table(Path(recipes_path).read_text(encoding="utf-8"))
            if table:
                totals = f"\n\nTOTALES SEMANALES CALCULADOS (ATM+IOB, crudo):\n{table}"

        user_message = (
            f"PLAN DE MEAL PREP:\n{plan}{totals}\n\n"
            f"ERRORES ENCONTRADOS POR EL AUDITOR (corrige solo estos):\n{feedback}\n\n"
            "Devuelve el arreglo JSON de ediciones."
        )
        raw = self._call_claude(self.FIX_SYSTEM_PROMPT, user_message, max_tokens=16000)
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        try:
            edits = json.loads(m.group(0)) if m else []
        except json.JSONDecodeError:
            edits = []

        applied, missed = [], []
        for e in edits:
            old, new = e.get("buscar", ""), e.get("reemplazar", "")
            if old and old in plan:
                plan = plan.replace(old, new, 1)
                applied.append(new.strip().splitlines()[0][:120] if new.strip() else old[:120])
            elif old:
                missed.append(old.strip().splitlines()[0][:120])
        if not edits:
            missed.append("El editor no devolvió ediciones válidas.")
        path.write_text(plan, encoding="utf-8")
        return applied, missed
