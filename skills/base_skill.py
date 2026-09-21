import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
import anthropic
import httpx
import yaml
from anthropic import Anthropic
from dotenv import load_dotenv
from . import token_tracker

load_dotenv()


@dataclass
class ValidationResult:
    passed: bool
    feedback: str   # Structured corrections → injected back into the generator on retry
    report: str     # Human-readable report → shown in console / stored


class BaseSkill:
    MODEL = "claude-opus-5"

    def __init__(self, config_dir: str = "config"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY no encontrada.\n"
                "Copia .env.example → .env y agrega tu clave de https://console.anthropic.com/settings/keys"
            )
        self.client = Anthropic(api_key=api_key)
        self.config_dir = Path(config_dir)
        self.user_profile = self._load_yaml("user_profile.yaml")

    def _load_yaml(self, filename: str) -> dict:
        with open(self.config_dir / filename, encoding="utf-8") as f:
            return yaml.safe_load(f)

    MAX_TOKENS_CEILING = 64000

    # Hard wall-clock cap per streaming attempt. httpx's default read timeout
    # (600s) only resets on each individual chunk, so a response that keeps
    # trickling bytes without finishing — e.g. a web_search-tool audit stuck
    # in a bad loop — can block forever with no error (observed: shopping-list
    # audit hung 2h27m, 2026-09-20). This bounds each attempt independently of
    # what the underlying client/library considers "still receiving data".
    STREAM_TIMEOUT_S = 900

    # Server-side web search (runs on Anthropic's infrastructure — no client-side
    # tool loop needed; get_final_message() already returns the model's answer
    # after its internal search iterations). No beta header required.
    WEB_SEARCH_TOOL_TYPE = "web_search_20260209"

    @classmethod
    def _web_search_tool(cls, max_uses: int = 8) -> dict:
        return {"type": cls.WEB_SEARCH_TOOL_TYPE, "name": "web_search", "max_uses": max_uses}

    def _call_claude(self, system: str, user_message: str | list, max_tokens: int = 4096,
                      tools: list | None = None) -> str:
        """Call Claude, auto-escalating max_tokens if the response gets truncated.

        Some reports (menu validation, meal-prep audits) vary a lot in length run to
        run — a fixed budget that was safe last week can still get clipped this week.
        Rather than fail and wait for a manual max_tokens bump, retry with a bigger
        budget (capped at MAX_TOKENS_CEILING) before giving up.

        user_message can be plain text or a list of content blocks (e.g. images +
        text, for Vision calls) — the Messages API accepts either as `content`.

        tools, when given, is passed straight through to the API (e.g. a server-side
        web_search tool via _web_search_tool()). Keep the tool list identical across
        calls from the same skill — it renders before `system` in the prompt-cache
        prefix, so a varying tool set would invalidate the system-prompt cache.
        """
        budget = max_tokens
        attempt = 0
        while True:
            attempt += 1
            response = self._stream_with_retry(system, user_message, budget, tools=tools)
            token_tracker.record(self.__class__.__name__, response.usage)
            if response.stop_reason != "max_tokens":
                return self._extract_text(response.content)

            if budget >= self.MAX_TOKENS_CEILING or attempt >= 3:
                raise RuntimeError(
                    f"{self.__class__.__name__}: la respuesta de Claude se truncó al alcanzar "
                    f"max_tokens={budget} incluso tras reintentar — el resultado habría quedado "
                    "incompleto. Reduce el contenido de entrada o revisa el prompt."
                )
            budget = min(budget * 2, self.MAX_TOKENS_CEILING)

    @staticmethod
    def _extract_text(content_blocks) -> str:
        """Concatenate just the text blocks, in order — content[0] is not reliably
        the answer (with thinking enabled the first block is a thinking block,
        which has no .text at all)."""
        return "".join(b.text for b in content_blocks if getattr(b, "type", None) == "text")

    def _stream_with_retry(self, system: str, user_message: str | list, max_tokens: int,
                            max_attempts: int = 3, tools: list | None = None):
        """Open a streaming request, retrying on transient connection drops.

        Large max_tokens requests must stream (see
        https://github.com/anthropics/anthropic-sdk-python#long-requests), and a
        long-lived stream is more exposed to a mid-response network hiccup — the
        server or an intermediate proxy closing the connection before the chunked
        body finishes (httpx.RemoteProtocolError / anthropic.APIConnectionError).
        That's a transient fault, not a data problem, so retry with backoff instead
        of failing the whole run.
        """
        last_err = None
        kwargs = dict(
            model=self.MODEL,
            max_tokens=max_tokens,
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
            # "high" is the model default; "medium" cuts thinking-token spend and
            # latency substantially (measured: ~4x faster, ~3.5x cheaper on a real
            # menu generation) with no measured compliance regression — the
            # menu-validator retry loop in `semana-completa` still catches whatever
            # gap remains on the first pass, same as it always has.
            output_config={"effort": "medium"},
        )
        if tools:
            kwargs["tools"] = tools
        for attempt in range(1, max_attempts + 1):
            outcome: dict = {}

            def _run(kwargs=kwargs, outcome=outcome):
                try:
                    with self.client.messages.stream(**kwargs) as stream:
                        outcome["message"] = stream.get_final_message()
                except Exception as e:  # noqa: BLE001 — re-raised on the caller's thread below
                    outcome["error"] = e

            # Daemon thread + join(timeout=...): a plain call can't be cancelled once
            # blocked on a socket read, and a non-daemon thread would make the whole
            # process hang at exit waiting for it. Abandoning the thread on timeout
            # lets the retry (or the caller) proceed; the leaked thread dies with the
            # process.
            worker = threading.Thread(target=_run, daemon=True)
            worker.start()
            worker.join(timeout=self.STREAM_TIMEOUT_S)

            if worker.is_alive():
                last_err = TimeoutError(
                    f"sin respuesta tras {self.STREAM_TIMEOUT_S}s (intento {attempt})"
                )
            elif "message" in outcome:
                return outcome["message"]
            else:
                err = outcome["error"]
                if not isinstance(err, (anthropic.APIConnectionError, httpx.TransportError)):
                    raise err
                last_err = err

            if attempt < max_attempts:
                time.sleep(2 ** attempt)  # 2s, 4s
        raise RuntimeError(
            f"{self.__class__.__name__}: se perdió la conexión con la API de Claude tras "
            f"{max_attempts} intentos ({last_err.__class__.__name__}: {last_err}). "
            "Probablemente un problema de red transitorio — intenta de nuevo."
        ) from last_err

    def _save_output(self, content: str, output_dir: str, filename: str) -> Path:
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        output_path = path / filename
        output_path.write_text(content, encoding="utf-8")
        return output_path

    @staticmethod
    def _ingredient_totals_table(recipes_content: str) -> str:
        """Deterministically compute each ingredient's exact weekly raw-gram total
        from the recipes (same canonicalization the site uses, so name variants
        like "Salmón" / "Salmón filete" / "Filete de salmón" are already merged).
        Code-computed sums, shared by every skill that needs an authoritative
        quantity reference instead of asking the model to re-derive them itself
        (generating a shopping list, or auditing one against the recipes)."""
        from .site_builder import SiteBuilderSkill

        totals = SiteBuilderSkill._parse_recipe_ingredient_totals(recipes_content)
        if not totals:
            return ""

        rows = "\n".join(
            f"| {v['name']} | {v['atm_g']:.0f}g | {v['iob_g']:.0f}g |"
            for v in sorted(totals.values(), key=lambda x: x['name'].lower())
        )
        return (
            "| Ingrediente | 🧔 ATM total | 👤 IOB total |\n"
            "|---|---|---|\n"
            f"{rows}"
        )

    @staticmethod
    def _parse_verdict_result(raw: str) -> ValidationResult:
        """Parse the shared VEREDICTO / FEEDBACK_GENERADOR / REPORTE_HUMANO format
        used by every strict auditor (menu, shopping list, meal prep). Malformed
        output (missing markers) is treated as a failed validation rather than
        silently passing — an auditor that can't be parsed can't be trusted."""
        passed = "VEREDICTO: APROBADO" in raw

        feedback = ""
        report = raw

        try:
            if "FEEDBACK_GENERADOR:" in raw and "REPORTE_HUMANO:" in raw:
                fb_start = raw.index("FEEDBACK_GENERADOR:") + len("FEEDBACK_GENERADOR:")
                fb_end   = raw.index("REPORTE_HUMANO:")
                feedback = raw[fb_start:fb_end].strip()
                if feedback.lower() in ("ninguno", "ninguno."):
                    feedback = ""

                rpt_start = raw.index("REPORTE_HUMANO:") + len("REPORTE_HUMANO:")
                report = raw[rpt_start:].strip()
            else:
                passed = False
        except ValueError:
            passed = False
            report = raw

        return ValidationResult(passed=passed, feedback=feedback, report=report)
