---
name: pipeline-doctor
description: Diagnoses a stuck generator/validator retry loop in this project (menu, shopping list, or meal prep) without re-running the full, slow, paid `semana-completa` pipeline. Use this when the user says a validator "keeps rejecting", "won't pass", "keeps failing the same way", asks why `semana-completa` used the last-resort output after 3 retries, or wants to know whether to just retry again or actually fix a prompt. Also useful proactively right after a `semana-completa` run reports "no se pudo validar ... en 3 intentos".
---

# Pipeline Doctor

`semana-completa` retries each generator/validator pair (menu, meal prep, shopping list) up to 3 times, printing each rejection to the console — but **nothing is persisted to disk**. Once the run ends, the specific `FEEDBACK_GENERADOR` that caused each rejection is gone unless it's still in terminal scrollback. Re-running the whole pipeline just to see what the validator is complaining about burns a real, paid, multi-minute run.

The fix: this project has cheap standalone validator commands that re-check the *current* output file against the *current* validator prompt, for the cost of one API call instead of a full retry loop:

| Stage | Standalone check command |
|---|---|
| Menu | `python main.py validar-menu` |
| Shopping list | `python main.py verificar-compras` |
| Meal prep | `python main.py verificar-prep` |

Each defaults to the most recent file in `outputs/` if you don't pass `--menu`/`--compras`/`--prep` explicitly.

## Procedure

1. **Figure out which stage is stuck.** Ask the user if it's not obvious from context, or infer it from what they quoted (mentions of calories/macros → menu; mentions of ingredients/quantities/store → shopping list; mentions of prep schedule/sous vide/conservation → meal prep).

2. **Run the matching standalone command** via Bash (`python main.py validar-menu`, `verificar-compras`, or `verificar-prep`) to get a fresh validation report against the *current* output file. This is the cheap move — one API call, not a full pipeline run.

3. **Read the rejection detail.** Every validator in this project (`skills/menu_validator.py`, `skills/shopping_validator.py`, `skills/meal_prep_validator.py`) follows the same report structure: a `❌ Problemas Críticos` section with concrete numbers, and a `FEEDBACK_GENERADOR` block with actionable corrections. Note exactly what's failing and why (which day/ingredient/quantity, what the target vs. actual was).

4. **Read the matching generator's `SYSTEM_PROMPT`** (`skills/menu_generator.py`, `skills/shopping_list.py`, or `skills/meal_prep_planner.py`) and check whether it actually instructs the model to get this right:
   - **If the prompt already covers it correctly** (the rule is there, unambiguous, and matches what the validator expects) — this is most likely normal run-to-run variance. Tell the user a plain retry (re-run `semana-completa`, or just regenerate that one stage) is likely to fix it; no prompt edit needed.
   - **If the prompt is missing the rule, states it ambiguously, or conflicts with what the validator actually checks** (the same kind of drift `audit-project-skills` looks for) — this will keep recurring on every retry no matter how many times you run it. Point to the exact line in the generator's `SYSTEM_PROMPT` that needs to change, and propose the specific edit.
   - **If the validator's own criteria look wrong** (e.g. a tolerance that doesn't match what the generator is reasonably able to hit, or a rule that misreads the household context in `CLAUDE.md`) — say so; the fix might belong in the validator prompt, not the generator.

5. **Give a verdict, not just a diagnosis**: "retry, no changes needed" / "edit `skills/X.py` line N because Y" / "this is a validator bug, here's why". If you propose a prompt edit and the user confirms, make it — this is a normal code edit, not a special workflow.

## Notes

- Don't default to re-running `semana-completa` to "see if it's fixed" — that's the expensive loop this skill exists to avoid. Use the standalone `validar-*`/`verificar-*` command to check one stage at a time.
- The validators are strict by design (see their prompts — e.g. shopping list treats a missing ingredient as `❌ Problema Crítico`, meal prep treats a food-safety timing violation as automatic failure). A rejection is not evidence of a validator bug by default; check the generator's actual output against the plan/menu before assuming the validator is being unreasonable.
- If three fresh checks in a row show materially different complaints each time (not the same recurring issue), that itself is a signal of normal variance rather than a prompt gap — say so plainly rather than chasing each one individually.
