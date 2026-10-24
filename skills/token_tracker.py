"""
Module-level token accumulator — one instance per Python process.
Call record() after every API response; call print_summary() at process exit.
check_budget() runs before every API call and stops the run once the per-run
or per-day spending cap in config/user_profile.yaml (api_budget) is reached.
"""
import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import List

import yaml

# USD per million tokens: input, output, cache write (5-min TTL), cache read.
_PRICES = {
    "claude-opus-5":    (5.00, 25.00, 6.25, 0.50),
    "claude-sonnet-5":  (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-4-5": (1.00,  5.00, 1.25, 0.10),
}
_DEFAULT_MODEL = "claude-opus-5"

LOG_PATH = Path("data/token_usage_latest.jsonl")
PROFILE_PATH = Path("config/user_profile.yaml")
DEFAULT_BUDGET = {"per_run_usd": 15.0, "per_day_usd": 25.0}
# Escape hatch for a deliberate one-off overspend: NUTRI_SIN_LIMITE=1
OVERRIDE_ENV = "NUTRI_SIN_LIMITE"


class BudgetExceeded(RuntimeError):
    pass


@dataclass
class _Record:
    skill:          str
    input_tokens:   int
    output_tokens:  int
    cache_creation: int
    cache_read:     int
    ts:             float = field(default_factory=time.time)
    model:          str = _DEFAULT_MODEL

    @property
    def cost_usd(self) -> float:
        # usage.input_tokens already excludes cached tokens — cache reads and
        # writes are billed on top of it, never subtracted from it.
        p_in, p_out, p_cw, p_cr = _PRICES.get(self.model, _PRICES[_DEFAULT_MODEL])
        return (
            self.input_tokens     * p_in
            + self.output_tokens  * p_out
            + self.cache_creation * p_cw
            + self.cache_read     * p_cr
        ) / 1_000_000


_records: List[_Record] = []
_warned = False


def record(skill: str, usage, model: str = _DEFAULT_MODEL) -> None:
    """Append one API-call record. `usage` is the Anthropic Usage object."""
    r = _Record(
        skill          = skill,
        input_tokens   = getattr(usage, "input_tokens", 0),
        output_tokens  = getattr(usage, "output_tokens", 0),
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read     = getattr(usage, "cache_read_input_tokens", 0) or 0,
        model          = model,
    )
    _records.append(r)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(r)) + "\n")


def run_cost() -> float:
    return sum(r.cost_usd for r in _records)


def day_cost(day: date | None = None) -> float:
    """Spend logged today across every run (this process's calls are in the log too)."""
    day = day or date.today()
    if not LOG_PATH.exists():
        return 0.0
    total = 0.0
    with open(LOG_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if datetime.fromtimestamp(d.get("ts", 0)).date() == day:
                total += _Record(**{k: d[k] for k in d if k in _Record.__dataclass_fields__}).cost_usd
    return total


def budget() -> dict:
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            cfg = (yaml.safe_load(f) or {}).get("api_budget") or {}
    except OSError:
        cfg = {}
    return {k: float(cfg.get(k, v)) for k, v in DEFAULT_BUDGET.items()}


def check_budget() -> None:
    """Raise BudgetExceeded before an API call once a cap is reached; warn once at 80 %."""
    global _warned
    if os.environ.get(OVERRIDE_ENV):
        return
    b = budget()
    run, day = run_cost(), day_cost()
    if run >= b["per_run_usd"]:
        raise BudgetExceeded(
            f"Límite por ejecución alcanzado: ${run:.2f} de ${b['per_run_usd']:.2f} USD. "
            f"Se detuvo antes de la siguiente llamada a la API."
        )
    if day >= b["per_day_usd"]:
        raise BudgetExceeded(
            f"Límite diario alcanzado: ${day:.2f} de ${b['per_day_usd']:.2f} USD hoy. "
            f"Se detuvo antes de la siguiente llamada a la API."
        )
    if not _warned and (run >= 0.8 * b["per_run_usd"] or day >= 0.8 * b["per_day_usd"]):
        _warned = True
        print(f"  ⚠️  Gasto API: ${run:.2f} esta ejecución · ${day:.2f} hoy "
              f"(límites ${b['per_run_usd']:.0f} / ${b['per_day_usd']:.0f} USD)")


def print_summary(label: str = "") -> None:
    """Print a per-skill token and cost table to stdout."""
    if not _records:
        return

    by_skill: dict = {}
    for r in _records:
        s = by_skill.setdefault(r.skill, dict(calls=0, inp=0, out=0, cw=0, cr=0, cost=0.0))
        s["calls"] += 1
        s["inp"]   += r.input_tokens
        s["out"]   += r.output_tokens
        s["cw"]    += r.cache_creation
        s["cr"]    += r.cache_read
        s["cost"]  += r.cost_usd

    title = f"Tokens API{' — ' + label if label else ''}"
    W = 84
    print(f"\n  ┌─ {title} {'─' * max(1, W - len(title) - 3)}┐")
    print(f"  {'Paso':<32} {'Calls':>5} {'Input':>9} {'Output':>8} {'Cache↑':>7} {'Cache↓':>7} {'USD':>8}")
    print("  " + "─" * W)

    total_cost = total_calls = total_inp = total_out = 0
    for skill, s in by_skill.items():
        name = skill if len(skill) <= 32 else skill[:29] + "..."
        print(
            f"  {name:<32} {s['calls']:>5} {s['inp']:>9,} {s['out']:>8,} "
            f"{s['cw']:>7,} {s['cr']:>7,} ${s['cost']:>7.4f}"
        )
        total_cost  += s["cost"]
        total_calls += s["calls"]
        total_inp   += s["inp"]
        total_out   += s["out"]

    b = budget()
    print("  " + "─" * W)
    print(
        f"  {'TOTAL':<32} {total_calls:>5} {total_inp:>9,} {total_out:>8,} "
        f"{'':>7} {'':>7} ${total_cost:>7.4f}"
    )
    print(f"  Hoy: ${day_cost():.2f} USD · límites ${b['per_run_usd']:.0f} por ejecución / ${b['per_day_usd']:.0f} por día")
    print(f"  └{'─' * W}┘")
