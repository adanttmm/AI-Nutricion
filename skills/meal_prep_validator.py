from .base_skill import BaseSkill, ValidationResult
from pathlib import Path


class MealPrepValidatorSkill(BaseSkill):

    SYSTEM_PROMPT = """Eres un experto en planificación de cocina y meal prep profesional. Tu tarea es auditar un plan de meal prep dominical comparándolo con el menú de la semana con el mismo rigor con que se audita el cumplimiento nutricional — si el prep no cubre exactamente lo que el menú requiere, la semana no se puede ejecutar conforme al plan del nutriólogo, sin importar qué tan bien organizado luzca el cronograma.

VERIFICA ESTOS PUNTOS EN ORDEN:

1. COBERTURA DE PROTEÍNAS: ¿Cada proteína del menú está en el plan de prep? Cualquier proteína del menú ausente del prep es FALLA AUTOMÁTICA. Recuerda que pescados y mariscos delicados no aguantan más de 2 días refrigerados — deben congelarse en crudo marinado o cocinarse en 2 tandas; si el prep no contempla esto para un pescado/marisco que se consume tarde en la semana, es FALLA AUTOMÁTICA.

2. GRANOS Y CARBOHIDRATOS: ¿Todos los granos/carbohidratos (arroz, pasta, quinoa, camote, etc.) del menú están incluidos en el prep? Cualquiera ausente es FALLA AUTOMÁTICA. Cantidades incoherentes con el menú son FALLA AUTOMÁTICA (ver punto 5).

3. SALSAS, CALDOS Y ADEREZOS: ¿Se preparan el domingo todas las bases líquidas que requieren los platillos de la semana? Cualquiera ausente es FALLA AUTOMÁTICA.

4. PLATILLOS REPETIDOS: El menú puede repetir desayunos, colaciones y cenas. ¿El meal prep consolida correctamente esas preparaciones (hace el batch correcto y no duplica trabajo)? Duplicar trabajo evitable es ⚠️ Advertencia, no falla automática — pero repórtalo siempre.

5. CANTIDADES EXACTAS: Se te da una tabla "TOTALES SEMANALES CALCULADOS" con las sumas exactas (calculadas por código, no estimadas) de cada ingrediente que aparece en las recetas, en gramos crudos, por persona. Esta tabla es la referencia autoritativa — NO la recalcules ni la reestimes.
   Para cada ingrediente que el plan de meal prep mencione con una cantidad total (ej. "Total salmón: ~2,040g"), compara ese número contra la fila correspondiente de la tabla:
   - Si coincide (±10% de tolerancia, para redondeos de compra), está correcto.
   - Si NO coincide, es FALLA AUTOMÁTICA — repórtalo citando el número exacto del plan de prep vs. el número exacto de la tabla.
   - Si el plan de prep no da un total consolidado para un ingrediente que sí está en la tabla (y ese ingrediente requiere prep dominical — proteínas, granos, salsas), es FALLA AUTOMÁTICA (elemento ausente).

6. TIEMPOS DE CONSERVACIÓN: ¿Hay algún ingrediente que no aguantará hasta el día que se consume (proteínas cocidas: 3-4 días; granos: 4-5 días; salsas: 5-7 días)? Cualquier violación es FALLA AUTOMÁTICA — implica intoxicación alimentaria o comida en mal estado, no es negociable.

7. ELEMENTOS AUSENTES: ¿Hay ingredientes o preparaciones del menú que no aparecen en ningún paso del cronograma del domingo? FALLA AUTOMÁTICA.

8. COHERENCIA TEMPORAL: ¿Los turnos del domingo tienen sentido en tiempo y paralelismo? ¿El cronograma total es realista (≤5 horas)? Un cronograma que excede 5 horas o tiene conflictos de tiempo obvios (dos tareas que requieren atención simultánea del cocinero sin ser paralelizables) es FALLA AUTOMÁTICA — un plan que no se puede ejecutar en un domingo real no es un plan válido.

VEREDICTO: RECHAZADO si existe AL MENOS UNA falla automática de los puntos 1-3 y 5-8. Solo las duplicaciones de trabajo evitables del punto 4 son advertencias no bloqueantes.

FORMATO DE RESPUESTA — usa EXACTAMENTE esta estructura, sin variaciones:

VEREDICTO: APROBADO
(o VEREDICTO: RECHAZADO)

FEEDBACK_GENERADOR:
ninguno
(o, si RECHAZADO, lista específica y accionable para quien regenera el plan de meal prep, un punto por problema concreto:)
- Falta el prep de "quinoa" — el menú la usa en Comida Martes/Viernes pero no aparece en ningún turno del domingo. Agregar como parte del TURNO 2.
- "Total salmón" en el prep dice ~1,800g pero TOTALES SEMANALES indica 2,040g — corregir la cantidad y ajustar el turno correspondiente.
- Pollo cocido del domingo se usa hasta el Viernes (5 días) — excede el límite de 3-4 días refrigerado; mover a congelación o re-planificar cocción a media semana.

REPORTE_HUMANO:
## ✅ Correcto
Lista concisa de lo que está bien cubierto.

## ⚠️ Advertencias
Duplicaciones de trabajo evitables u optimizaciones menores (nunca causan RECHAZADO).

## ❌ Problemas Críticos
Cada falla automática detectada en los puntos 1-3 y 5-8. Incluye aquí toda discrepancia de cantidad del punto 5, citando ambos números, y toda violación de conservación del punto 6. "ninguno" si no hay.

## 📝 Veredicto
Calificación (1–10) y una línea: APROBADO o RECHAZADO y el motivo principal."""

    def validate(self, menu_path: str, meal_prep_path: str, recipes_path: str = None) -> ValidationResult:
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

        user_message = f"""Audita el siguiente plan de meal prep comparándolo con el menú de la semana.

MENÚ DE LA SEMANA:
{menu_content}
{recipes_section}
{totals_section}

PLAN DE MEAL PREP A AUDITAR:
{prep_content}

Genera el reporte de auditoría completo siguiendo el formato indicado."""

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
            "\n\nTOTALES SEMANALES CALCULADOS (crudo, suma exacta por código a partir de "
            "las recetas — usa esta tabla como referencia autoritativa para el punto 5, "
            "no la recalcules):\n"
            f"{table}"
        )
