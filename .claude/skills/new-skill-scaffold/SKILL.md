---
name: new-skill-scaffold
description: Scaffolds a new skills/<name>.py generator (and optional <name>_validator.py) in this project, pre-wired to the shared BaseSkill conventions — _call_claude, _save_output, the VEREDICTO/FEEDBACK_GENERADOR/REPORTE_HUMANO contract, and _ingredient_totals_table where relevant. User-invoked only (/new-skill-scaffold) since it creates files — never trigger this automatically.
disable-model-invocation: true
---

# New Skill Scaffold

Every generator in `skills/` (`menu_generator.py`, `shopping_list.py`, `recipe_finder.py`, `meal_prep_planner.py`) follows the same shape, and every validator (`menu_validator.py`, `shopping_validator.py`, `meal_prep_validator.py`) follows another shape shared with `base_skill.py`. A previous audit of this project (see `audit-project-skills`) found a skill that bypassed these conventions simply because it predated them — not malice, just drift. Scaffolding a new skill from the current, correct templates keeps that from happening again: the convention becomes the path of least resistance instead of something to remember.

## Before writing anything

Ask the user (don't guess):
1. **What does this skill produce?** (a new Markdown output file, a data transform, something else)
2. **What's the class/file name?** (e.g. `snack_planner` → `skills/snack_planner.py`, class `SnackPlannerSkill`)
3. **Does it need a validator** — i.e. does its output have concrete right/wrong criteria worth auditing (like calorie targets, ingredient completeness, food-safety timing), or is it more freeform (like `recipe_finder`, which has no validator)?
4. **What does it read as input?** (menu path, recipes path, plan YAML, etc. — determines the `generate()`/`validate()` signature)
5. **Where does output go?** (`outputs/<subdir>/`, following the `<prefix>_YYYY-MM-DD.md` naming every other skill uses)
6. **Does it need the code-computed ingredient totals** (`_ingredient_totals_table`) as an authoritative reference, the way shopping list and meal prep do? Only relevant if the skill reasons about ingredient quantities — never let the model freehand-sum something code can compute exactly (this is the exact bug class the shopping list generator was fixed for).

## Generator template

```python
from .base_skill import BaseSkill
from pathlib import Path
from datetime import date


class <Name>Skill(BaseSkill):

    SYSTEM_PROMPT = """<role and task, in Spanish, matching the voice of the other skill prompts>

REGLAS:
1. ...
"""

    def generate(self, <inputs>, feedback: str = "") -> Path:
        if week_date is None:
            week_date = date.today()

        sections = [<read and label each input file>]

        correction_block = ""
        if feedback:
            correction_block = (
                f"\n\n---\n\n⚠️  CORRECCIONES OBLIGATORIAS — LA SALIDA ANTERIOR FUE RECHAZADA POR EL VALIDADOR:\n"
                f"{feedback}\n\n"
                "Genera una versión NUEVA corrigiendo EXACTAMENTE cada punto anterior."
            )

        user_message = (
            "<task instruction>\n\n"
            + "\n\n---\n\n".join(sections)
            + correction_block
        )

        content = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=16000)

        header = f"# <título>\n## Semana del {week_date.strftime('%d de %B de %Y')}\n\n"
        filename = f"<prefix>_{week_date.strftime('%Y-%m-%d')}.md"
        return self._save_output(header + content, "outputs/<subdir>", filename)
```

**Every `_call_claude` call, never `self.client.messages.create` directly** — that's what gives every skill connection-retry, max_tokens auto-escalation, and token tracking for free. The only legitimate exception in this codebase is a Vision call sending image content blocks instead of plain text, and even then `_call_claude` accepts a list of content blocks (see `diet_parser.py`), so there's no longer a reason to bypass it at all.

**Always route the "validator rejected this, try again" feedback back into `generate()` as a `feedback` parameter**, formatted as its own clearly-marked block — this is what the retry loop in `semana-completa` (see `main.py`) depends on.

## Validator template (only if the skill needs one)

```python
from .base_skill import BaseSkill, ValidationResult
from pathlib import Path


class <Name>ValidatorSkill(BaseSkill):

    SYSTEM_PROMPT = """<role: an expert auditor for this domain, same strict framing as the other validators — a rejection means the week can't actually be executed as planned, not just a style nitpick>

VERIFICA ESTOS PUNTOS EN ORDEN:
1. ...

VEREDICTO: RECHAZADO si existe AL MENOS UN ❌ Problema Crítico.

FORMATO DE RESPUESTA — usa EXACTAMENTE esta estructura, sin variaciones:

VEREDICTO: APROBADO
(o VEREDICTO: RECHAZADO)

FEEDBACK_GENERADOR:
ninguno
(o lista específica y accionable, un punto por problema)

REPORTE_HUMANO:
<sections: what's correct, warnings, critical problems, one-line verdict>
"""

    def validate(self, <inputs>) -> ValidationResult:
        sections = [<read and label each input file>]
        user_message = "<audit instruction>\n\n" + "\n\n---\n\n".join(sections)
        raw = self._call_claude(self.SYSTEM_PROMPT, user_message, max_tokens=16000)
        return self._parse_verdict_result(raw)
```

**Never deviate from the exact `VEREDICTO:` / `FEEDBACK_GENERADOR:` / `REPORTE_HUMANO:` marker text** — `BaseSkill._parse_verdict_result` parses on those literal strings, and a malformed match is treated as a failed validation (fails safe, but silently — the human report will look garbled instead of erroring loudly).

If the validator needs the authoritative ingredient totals table, add:
```python
    @classmethod
    def _build_totals_reference(cls, recipes_content: str) -> str:
        table = cls._ingredient_totals_table(recipes_content)
        if not table:
            return ""
        return (
            "TOTALES SEMANALES CALCULADOS (crudo, suma exacta por código — "
            "referencia autoritativa, no la recalcules):\n" + table
        )
```
and tell the prompt explicitly not to recompute it — every existing validator that uses this table says so in the same words, and it's there specifically because the model can't be trusted to sum quantities correctly by hand.

## After scaffolding

1. Write the file(s) with the Write tool, filled in from the interview answers — not the literal placeholder text above.
2. Run `python3 -m py_compile skills/<name>.py` (and the validator file, if any) to catch typos immediately.
3. Tell the user this skill still needs to be wired into `main.py` as a `@cli.command(...)` (and, if it should run as part of the weekly pipeline, into the retry loop in `semana-completa`) — offer to do that too, but don't do it silently without asking, since it changes the CLI surface and the weekly workflow.
