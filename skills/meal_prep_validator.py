from .base_skill import BaseSkill, ValidationResult
from pathlib import Path
import re


class MealPrepValidatorSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un experto en planificación de cocina y meal prep profesional. Tu tarea es auditar un plan de meal prep dominical comparándolo con el menú de la semana con el mismo rigor con que se audita el cumplimiento nutricional — si el prep no cubre exactamente lo que el menú requiere, la semana no se puede ejecutar conforme al plan del nutriólogo, sin importar qué tan bien organizado luzca el cronograma.

VERIFICA ESTOS PUNTOS EN ORDEN:

1. COBERTURA DE PROTEÍNAS: ¿Cada proteína del menú está en el plan de prep? Cualquier proteína del menú ausente del prep es FALLA AUTOMÁTICA.

2. GRANOS Y CARBOHIDRATOS: ¿Todos los granos/carbohidratos (arroz, pasta, quinoa, camote, etc.) del menú están incluidos en el prep? Cualquiera ausente es FALLA AUTOMÁTICA. Cantidades incoherentes con el menú son FALLA AUTOMÁTICA (ver punto 5).

3. SALSAS, CALDOS Y ADEREZOS: ¿Se preparan el domingo todas las bases líquidas que requieren los platillos de la semana? Cualquiera ausente es FALLA AUTOMÁTICA.

4. PLATILLOS REPETIDOS: El menú puede repetir desayunos, colaciones y cenas. ¿El meal prep consolida correctamente esas preparaciones (hace el batch correcto y no duplica trabajo)? Duplicar trabajo evitable es ⚠️ Advertencia, no falla automática — pero repórtalo siempre.

5. CANTIDADES EXACTAS: Se te da una tabla "TOTALES SEMANALES CALCULADOS" con las sumas exactas (calculadas por código, no estimadas) de cada ingrediente que aparece en las recetas, en gramos crudos, por persona. Esa tabla suma SOLO ATM+IOB (dos personas) — NO incluye al 3er comensal, que es un ajuste aparte.
   La cifra correcta a comparar contra el plan de meal prep es ATM+IOB de la tabla, MÁS una porción extra igual a la de IOB por cada instancia en que ese platillo se sirve en la Comida de martes, miércoles o viernes (el 3er comensal come solo en la Comida esos días, con la misma porción que IOB — ver el menú para confirmar en qué días aplica cada platillo). Esto es una suma legítima, no una discrepancia: si el plan de prep muestra un total mayor que la tabla y ese excedente cuadra con el número de instancias de 3er comensal × porción de IOB, está CORRECTO — no lo marques como falla.
   Para cada ingrediente que el plan de meal prep mencione con una cantidad total (ej. "Total salmón: ~2,040g"), compara ese número contra tabla+3er comensal (cuando aplique):
   - Si coincide (±10% de tolerancia, para redondeos de compra), está correcto.
   - Si NO coincide siquiera considerando el ajuste del 3er comensal, es FALLA AUTOMÁTICA — repórtalo citando el número exacto del plan de prep vs. el número exacto esperado (tabla + 3er comensal si aplica).
   - Si el plan de prep no da un total consolidado para un ingrediente que sí está en la tabla (y ese ingrediente requiere prep dominical — proteínas, granos, salsas), es FALLA AUTOMÁTICA (elemento ausente).

6. TIEMPOS DE CONSERVACIÓN (solo ⚠️ Advertencia, NUNCA causa RECHAZADO): ¿algo se usaría después de su límite (pescado/marisco delicado crudo: 2 días; proteínas cocidas: 3-4 días; granos: 4-5 días; salsas: 5-7 días)? Repórtalo en Advertencias con una sugerencia concreta de una línea (ej. "congelar las porciones de jue-dom y descongelar la noche anterior", "comprar el pescado fresco el martes"). No lo incluyas en FEEDBACK_GENERADOR.

7. PRIORIDAD DEL PREP: desayuno, colaciones y cena deben quedar 100% listos y porcionados (entre semana solo calentar/servir). Las comidas pueden quedar como mise en place (verduras cortadas/blanqueadas, salsas, granos, proteína lista para terminar). Si desayuno/colaciones/cena requieren cocción real entre semana (más allá de un paso final de ≤5 min), es ⚠️ Advertencia.

8. ELEMENTOS AUSENTES: ¿Hay ingredientes o preparaciones del menú que no aparecen en ningún paso del plan (fin de semana, mini-sesión o paso del día de servicio)? FALLA AUTOMÁTICA.

9. COHERENCIA TEMPORAL Y PRESUPUESTO: ¿Los turnos del domingo tienen sentido en tiempo y paralelismo? ¿El cronograma total respeta el presupuesto de 4 horas Sab+Dom (Sábado ≤45 min + Domingo ≤3.5 hrs)? Un cronograma que excede 4 horas TOTALES, o que no declara explícitamente sus tiempos estimados por turno, o que tiene conflictos de tiempo obvios (dos tareas que requieren atención simultánea del cocinero sin ser paralelizables) es FALLA AUTOMÁTICA — un plan que no se puede ejecutar en un fin de semana real no es un plan válido. El plan DEBE incluir la línea "TIEMPO TOTAL: X horas Y minutos" al final.

VEREDICTO: RECHAZADO solo si existe AL MENOS UNA falla automática de los puntos 1-3, 5, 8 o 9. Los puntos 4, 6 y 7 (duplicaciones, conservación, prioridad del prep) son advertencias no bloqueantes — van en el reporte, nunca en FEEDBACK_GENERADOR.

FORMATO DE RESPUESTA — usa EXACTAMENTE esta estructura, sin variaciones:

VEREDICTO: APROBADO
(o VEREDICTO: RECHAZADO)

FEEDBACK_GENERADOR:
ninguno
(o, si RECHAZADO, lista específica y accionable para quien regenera el plan de meal prep, un punto por problema concreto:)
- Falta el prep de "quinoa" — el menú la usa en Comida Martes/Viernes pero no aparece en ningún turno del domingo. Agregar como parte del TURNO 2.
- "Total salmón" en el prep dice ~1,800g pero TOTALES SEMANALES indica 2,040g — corregir la cantidad y ajustar el turno correspondiente.

REPORTE_HUMANO:
## ✅ Correcto
Lista concisa de lo que está bien cubierto.

## ⚠️ Advertencias
Duplicaciones evitables, avisos de conservación con su sugerencia, y prioridad del prep (nunca causan RECHAZADO).

## ❌ Problemas Críticos
Cada falla automática detectada en los puntos 1-3, 5, 8 y 9. Incluye aquí toda discrepancia de cantidad del punto 5, citando ambos números. "ninguno" si no hay.

## 📝 Veredicto
Calificación (1–10) y una línea: APROBADO o RECHAZADO y el motivo principal."""

    def validate(self, menu_path: str, meal_prep_path: str, recipes_path: str = None,
                 week_notes: str = "") -> ValidationResult:
        menu_content = Path(menu_path).read_text(encoding="utf-8")
        prep_content = Path(meal_prep_path).read_text(encoding="utf-8")

        recipes_section = ""
        totals_section = ""
        if recipes_path and Path(recipes_path).exists():
            # Pass the whole file — truncating here blinds the audit to exactly the
            # back half of the week whose quantities most need checking.
            recipes_content = Path(recipes_path).read_text(encoding="utf-8")
            recipes_section = f"\n\nRECETAS (ingredientes y técnicas de referencia):\n{recipes_content}"
            totals_section = self._build_totals_reference(recipes_content)

        notes_section = (
            "\nNOTA DE LA SEMANA DEL COCINERO (sobrantes / inventario — lo que ya está preparado no "
            f"necesita paso de prep; respeta lo que la nota indica):\n{week_notes}\n"
        ) if week_notes else ""

        user_message = f"""Audita el siguiente plan de meal prep comparándolo con el menú de la semana.

MENÚ DE LA SEMANA:
{menu_content}
{recipes_section}
{totals_section}
{self._time_check(prep_content)}
{notes_section}

PLAN DE MEAL PREP A AUDITAR:
{prep_content}

Genera el reporte de auditoría completo siguiendo el formato indicado."""

        raw = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=16000)
        return self._parse_verdict_result(raw)

    _CLOCK_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(?:–|-|a)\s*(\d{1,2}):(\d{2})")
    _MIN_RE = re.compile(r"\((\d+)\s*min")

    @classmethod
    def _heading_minutes(cls, heading: str) -> int | None:
        """Minutes for one heading: clock range if present (harder to fudge),
        otherwise the "(NN min)" it declares."""
        m = cls._CLOCK_RE.search(heading)
        if m:
            h1, m1, h2, m2 = map(int, m.groups())
            return (h2 * 60 + m2) - (h1 * 60 + m1)
        m = cls._MIN_RE.search(heading) or re.search(r"(\d+)\s*min", heading)
        return int(m.group(1)) if m else None

    @classmethod
    def compute_weekend_minutes(cls, prep_content: str) -> tuple[int | None, int | None]:
        """(saturday_min, sunday_min) summed by code from the plan's own headings —
        the planner's self-reported TIEMPO TOTAL has been wrong in both directions."""
        sat = None
        turnos = []
        for line in prep_content.splitlines():
            s = line.strip()
            if sat is None and re.match(r"^#{1,2} .*s[áa]bado", s, re.IGNORECASE):
                sat = cls._heading_minutes(s)
            elif re.match(r"^#{2,4}\s*TURNO", s, re.IGNORECASE):
                mins = cls._heading_minutes(s)
                if mins is not None:
                    turnos.append(mins)
        return sat, (sum(turnos) if turnos else None)

    @classmethod
    def _time_check(cls, prep_content: str) -> str:
        sat, sun = cls.compute_weekend_minutes(prep_content)
        if sun is None:
            return ""
        total = (sat or 0) + sun
        return (
            "\nTIEMPO CALCULADO POR CÓDIGO (suma de los encabezados del propio plan — autoritativo para el "
            "punto 9; si el TIEMPO TOTAL que declara el plan no coincide, es un error del plan): "
            f"Sábado {sat if sat is not None else '?'} min + Domingo {sun} min (suma de TURNOS) = "
            f"{total // 60} h {total % 60:02d} min. Límite: 4 h 00 min.\n"
        )

    @classmethod
    def _build_totals_reference(cls, recipes_content: str) -> str:
        """Format the shared code-computed ingredient totals as an authoritative
        reference block for the audit prompt (see BaseSkill._ingredient_totals_table)."""
        table = cls._ingredient_totals_table(recipes_content)
        if not table:
            return ""
        return (
            "\n\nTOTALES SEMANALES CALCULADOS (crudo, suma exacta por código a partir de "
            "las recetas — usa esta tabla como referencia autoritativa para el punto 5, "
            "no la recalcules; es solo ATM+IOB, ver punto 5 para cómo sumar el 3er comensal "
            "cuando aplique):\n"
            f"{table}"
        )
