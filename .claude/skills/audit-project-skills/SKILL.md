---
name: audit-project-skills
description: Audits the Python "skills" in skills/*.py (diet_parser, menu_generator, shopping_list, recipe_finder, meal_prep_planner, and their *_validator.py counterparts) for consistency with the shared BaseSkill patterns, validator correctness, prompt drift between generator/validator pairs, and general code quality. Use this whenever the user asks to "audit the skills", "review skills/", "check the [X] skill", "did I break anything editing base_skill.py", or after a batch of edits across the skills/ directory to sanity-check they still cohere before running semana-completa.
---

# Audit Project Skills

This project's `skills/*.py` files are not independent scripts — they're a family that all extend `BaseSkill` (`skills/base_skill.py`) and lean on a few shared conventions: the `_call_claude` retry/escalation wrapper, the `VEREDICTO`/`FEEDBACK_GENERADOR`/`REPORTE_HUMANO` contract parsed by `_parse_verdict_result`, and code-computed reference tables (`_ingredient_totals_table`) that exist specifically so the model never has to freehand arithmetic it's bad at.

The failure mode this audit exists to catch isn't "does this file have a bug" in the generic sense — it's **drift**: a generator and its validator prompt slowly diverging (duplicated text blocks edited in only one place), a skill quietly bypassing the shared retry/caching path, or a validator whose VEREDICTO logic no longer actually gates on the failure it claims to catch. See the project's own [[project_shopping_list_freehand_sum_bug]]-shaped history: the shopping list generator used to have the model sum ingredient quantities by hand, which drifted from the real recipe totals. That bug class — "the model is asked to compute something code already computed correctly" — is exactly what this audit should keep hunting for across every skill, not just the one it was first found in.

## Procedure

1. **Read `skills/base_skill.py` first**, every time — don't rely on memory of it from a previous audit. It changes, and the whole point of the audit is to check other files against its *current* shape.

2. **Read `CLAUDE.md`** for the household context that should be encoded consistently across skill prompts (2 people all meals, 3rd person Mon/Wed/Fri lunch, 1 cheat meal/week, gym +150kcal Mon/Wed/Fri, salsa +100kcal Tue/Thu, Costco vs. City Market split).

3. **For each skill in `skills/`** (skip `__init__.py`, `base_skill.py`, `token_tracker.py`, `ratings_loader.py`, `site_builder.py` unless the user asks to include them — those are infrastructure, not the generator/validator family), and its validator counterpart if one exists, check the four dimensions below.

4. **Write findings straight to a report** as you go — don't hold the whole audit in your head and dump it at the end. Use the template in "Output format".

## What to check

### 1. Consistency with base_skill.py patterns
- Does the skill call `self._call_claude(...)` rather than hitting `self.client.messages.*` directly? A direct call bypasses the max_tokens escalation, the connection-retry loop, and token tracking — silent regressions here are easy to miss because they only bite on a truncated or flaky-network run, not in normal testing.
- Do `max_tokens` values look sized to the content (a single-recipe call at 2000 is fine; a full-week menu or validator report needs headroom — compare against similar existing calls rather than a fixed number).
- Does a generator use `self._save_output(...)` rather than writing files itself?
- Does anything duplicate logic that `base_skill.py` already provides (a hand-rolled retry loop, a second ingredient-totals calculation, a second VEREDICTO parser)? If `base_skill.py` grew a new shared helper recently, check whether older skills should have been migrated to use it.

### 2. Validator correctness
For each `*_validator.py`:
- Does it use `_parse_verdict_result` and the exact `VEREDICTO: APROBADO`/`RECHAZADO` + `FEEDBACK_GENERADOR:` + `REPORTE_HUMANO:` markers? A validator whose prompt format has drifted from what `_parse_verdict_result` expects will silently parse as `passed=False` (fails safe, but the human report will be garbled — check for this by considering whether the prompt's FORMATO DE RESPUESTA block still matches exactly).
- Does the VEREDICTO logic in the prompt actually gate on the things it claims are critical? E.g. "RECHAZADO si existe AL MENOS UN ❌ Problema Crítico" is only meaningful if the "critical vs. warning" categorization above it is unambiguous — check for vague criteria that could let a real problem get bucketed as a non-blocking ⚠️ Advertencia.
- If the validator is handed a code-computed reference table (like `TOTALES SEMANALES CALCULADOS`), does its prompt correctly say that table is authoritative and forbid recalculating it — the same discipline the shopping list bug fix established? Any validator that asks the model to independently re-derive a number that code already computed accurately is a regression toward the freehand-sum bug class, just in a new place.
- Cross-check the validator's tolerance thresholds (e.g. ±10%, ±15%) against the generator's stated rounding rules — a validator stricter than what the generator is instructed to produce will reject correct output; looser, and it'll wave through real errors.

### 3. Prompt quality / drift between generator and validator pairs
- Diff the shared reference blocks between a generator and its validator (e.g. `CRITERIO DE TIENDA` currently appears near-verbatim in both `shopping_list.py` and `shopping_validator.py`). Any divergence between the two copies — an ingredient added to one list but not the other, a store reassigned — means the generator and its own auditor disagree about the rules, which makes the validator's rejections meaningless (it'll reject correct output against a stale rule, or approve output that violates the generator's actual current rules). Flag every such duplicated block you find, whether or not it's currently diverged — duplication is the risk even before it drifts.
- Check that the household context constants (2+1 people, 3rd-comensal days, cheat meal day, gym/salsa kcal bumps) are the same across every skill that states them. A number changed in one prompt and not another produces a menu and a shopping list that silently disagree on serving counts.
- Read the prompt as if you were the model executing it cold: is there an instruction that's ambiguous enough that two reasonable readings would produce different output? That ambiguity is a drift risk even with no code bug involved.
- **When two prompts state different numbers for what looks like the same tolerance or rule (e.g. a generator's target vs. a validator's acceptance threshold), don't stop at noting the discrepancy — work out whether it's actually a bug.** A generator being told to aim tighter than the validator strictly requires is normal and fine (the generator's number is a target, the validator's is a gate — a stricter target than the gate is not a defect). It's only a real finding if: the *validator* is stricter than what the generator is told to produce (which would reject correct output), or the two numbers govern the literal same computation with no plausible reason to differ, or the relationship between the two is never explained anywhere and a reasonable edit could plausibly break it. If you can resolve which case it is, report the concrete conclusion ("this is fine because X" goes in 🟢, "this is a real mismatch because Y" goes in 🔴/🟡) rather than reporting the bare discrepancy with a hedge like "might be intentional, hard to tell." An audit finding should tell the reader what to do next, not hand them your own uncertainty.

### 4. General code quality
Standard review scope, but only flag things that would actually bite in this codebase: unhandled `Path` that may not exist before `.read_text()`, an `f-string` that could KeyError on missing YAML keys, a swallowed exception, dead code, or logic that's been superseded by a newer shared helper but not cleaned up. Don't flag style nits (formatting, naming taste) — this audit is about correctness and drift, not linting.

## Output format

Write the report to `outputs/audits/skill_audit_YYYY-MM-DD.md` (create the directory if needed) using today's date, structured like this:

```markdown
# Audit de Skills — YYYY-MM-DD

## Resumen
One paragraph: what was audited, overall health, count of findings by severity.

## 🔴 Crítico
Findings that would produce wrong output or a silent failure in real weekly use. One entry per finding:
- **[file:line]** — what's wrong, why it matters, concrete fix.

## 🟡 Advertencia
Findings worth fixing but not currently causing wrong output (drift risk, duplicated logic, fragile pattern).

## 🟢 Correcto
Brief note on what's holding up well — don't skip this section; it's what tells the user the audit actually looked rather than just fishing for problems.

## Archivos auditados
List of skills/*.py files covered and which check categories applied to each.
```

Report findings the same way `/code-review` does: cite `file:line`, state the concrete failure scenario, don't pad with generic praise. If you find nothing in a category for a given file, say so briefly rather than omitting the category — that tells the user the check ran, not that it was skipped.

After writing the report, summarize the 🔴 Crítico and 🟡 Advertencia counts directly in the conversation and point to the report path — don't paste the whole report into chat.
