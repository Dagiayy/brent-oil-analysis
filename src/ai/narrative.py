"""AI-assisted narrative generation for the change-point + event report.

The statistical/Bayesian pipeline produces precise but dry numbers (tau HDI,
r_hat, annualized vol). This module turns that structured result into a
short, readable analyst note - the kind of "so what does this mean"
paragraph a data analyst would otherwise have to write by hand for every run.

Design choices, deliberately conservative:
  * No new hard dependency. The ``anthropic`` package is imported lazily
    inside ``_call_claude`` so the rest of the pipeline (data, stats, the
    Bayesian model, the API) works with zero AI configuration.
  * Fully optional. If ``ANTHROPIC_API_KEY`` is not set, or the package
    is not installed, or the call fails for any reason, generation falls
    back to a deterministic template built from the same numbers. The
    pipeline must never fail, and the dashboard must never show nothing,
    because a paid API call is unavailable - that would make the "AI
    feature" a reliability liability instead of a value-add.
  * No hallucination surface for numbers. The prompt hands Claude the
    already-computed statistics and instructs it to use them verbatim
    rather than deriving new figures, and the fallback template uses the
    exact same numbers - so the two code paths never disagree.
"""
from __future__ import annotations

import os
from typing import Any

from src.utils import get_logger

logger = get_logger(__name__)

DEFAULT_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-5")

_SYSTEM_PROMPT = (
    "You are a commodities market analyst writing a short internal research "
    "note. You will be given precomputed statistics from a Bayesian change-point "
    "analysis of Brent crude oil log returns, plus the nearest catalogued "
    "real-world event. Write 3-5 sentences in plain English explaining what was "
    "found. Rules: use ONLY the numbers provided, do not invent statistics, do "
    "not claim causation between the event and the change point (correlation in "
    "time only), mention the model's reliability if diagnostics flagged the run "
    "as unreliable, and end with one sentence of appropriate uncertainty/caveat."
)


def _build_user_prompt(report: dict[str, Any]) -> str:
    lines = ["Change-point analysis result (JSON):", str(report)]
    return "\n".join(lines)


def _template_narrative(report: dict[str, Any]) -> str:
    """Deterministic, dependency-free fallback covering the same content
    an LLM call would produce, so the feature degrades gracefully."""
    cp = report.get("change_point", {})
    alignment = report.get("event_alignment", {})
    diagnostics = report.get("diagnostics", {})

    change_date = cp.get("change_date", "an unknown date")
    mean_before = alignment.get("mean_return_before")
    mean_after = alignment.get("mean_return_after")
    vol_before = alignment.get("annualized_vol_before")
    vol_after = alignment.get("annualized_vol_after")
    event = alignment.get("nearest_event")
    days = alignment.get("days_to_nearest_event")

    parts = [f"The model identifies the most probable structural break in Brent log returns at {change_date}."]

    if mean_before is not None and mean_after is not None:
        direction = "rose" if mean_after > mean_before else "fell"
        parts.append(
            f"The mean daily log return {direction} from {mean_before:.5f} before the break to "
            f"{mean_after:.5f} after it, while annualized volatility moved from {vol_before:.1%} to {vol_after:.1%}."
        )

    if event:
        when = f"{abs(days)} day(s) {'after' if (days or 0) >= 0 else 'before'}" if days is not None else "near"
        parts.append(f"The closest catalogued event in time is '{event}', occurring {when} the detected change point.")
    else:
        parts.append("No catalogued event falls within the configured time window of this change point.")

    if diagnostics and not diagnostics.get("reliable", True):
        parts.append(
            "Note: sampling diagnostics flagged this run as potentially unreliable "
            f"({'; '.join(diagnostics.get('warnings', []))}); treat the exact date with caution."
        )

    parts.append("Timing coincidence does not establish that the event caused the shift in oil price behavior.")
    return " ".join(parts)


def _call_claude(report: dict[str, Any], model: str) -> str | None:
    try:
        import anthropic
    except ImportError:
        logger.info("anthropic package not installed; using template narrative.")
        return None

    if not os.getenv("ANTHROPIC_API_KEY"):
        logger.info("ANTHROPIC_API_KEY not set; using template narrative.")
        return None

    try:
        client = anthropic.Anthropic()
        response = client.messages.create(
            model=model,
            max_tokens=512,
            system=_SYSTEM_PROMPT,
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": _build_user_prompt(report)}],
        )
        if response.stop_reason == "refusal":
            logger.warning("Claude declined to generate the narrative; using template instead.")
            return None
        text = "".join(block.text for block in response.content if block.type == "text").strip()
        return text or None
    except Exception:  # noqa: BLE001 - narrative generation must never break the pipeline
        logger.exception("Claude narrative generation failed; falling back to template.")
        return None


def generate_narrative(report: dict[str, Any], model: str = DEFAULT_MODEL) -> dict[str, Any]:
    """Return ``{"text": ..., "source": "claude"|"template"}`` for the report."""
    text = _call_claude(report, model)
    if text:
        return {"text": text, "source": "claude", "model": model}
    return {"text": _template_narrative(report), "source": "template", "model": None}
