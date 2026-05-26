"""research_t4_nowebsite.py -- research IA SIN web (Opcion C T4).

Sub-modulo invocado por `option_c_t4.py` para hacer research sobre una
company T4 fit sin web declarada. Prompt corto que infiere sub-sector y
hooks conservadores desde nombre + localidad + descripcion Sabi +
facturacion. Sin scraping (no hay web).

Coste estimado por empresa: ~$0.005-0.010 (Sonnet 4.6, prompt ~800
tokens in + ~250 out).

Ver doc: docs/option_c_t4_pipeline.md (2) research_t4_nowebsite.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.llm import call_llm

logger = logging.getLogger("demin.research_t4_nowebsite")

PROMPT_PATH = (
    Path(__file__).resolve().parent.parent / "shared" / "prompts"
    / "research_t4_nowebsite.md"
)


@dataclass(slots=True)
class T4ResearchResult:
    research_data: dict[str, Any]
    tokens_in: int
    tokens_out: int
    cost_usd: float | None


def _load_prompt() -> tuple[str, str]:
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    parts = raw.split("## System", 1)
    if len(parts) != 2:
        raise RuntimeError("research_t4_nowebsite.md falta '## System'")
    after = parts[1]
    sys_user = after.split("## User template", 1)
    if len(sys_user) != 2:
        raise RuntimeError("research_t4_nowebsite.md falta '## User template'")
    return sys_user[0].strip(), sys_user[1].strip()


_SYSTEM, _USER_TEMPLATE = _load_prompt()


def research_company_nowebsite(company: dict[str, Any]) -> T4ResearchResult:
    """Llama Sonnet con los datos de Sabi. Devuelve research_data ya
    parseado a dict + meta de coste.

    company debe tener: nombre, nif, localidad, descripcion, rev_y0_keur,
    rev_y1_keur, rev_growth_pct, tier.
    """
    user_filled = _USER_TEMPLATE.format(
        nombre=company.get("nombre") or "",
        nif=company.get("nif") or "",
        localidad=company.get("localidad") or "",
        descripcion=(company.get("descripcion") or "")[:500],
        rev_y0_keur=company.get("rev_y0_keur") if company.get("rev_y0_keur") is not None else "",
        rev_y1_keur=company.get("rev_y1_keur") if company.get("rev_y1_keur") is not None else "",
        rev_growth_pct=company.get("rev_growth_pct") if company.get("rev_growth_pct") is not None else "",
        tier=company.get("tier") or "",
    )
    text, meta = call_llm(
        task="research_t4_nowebsite",
        system=_SYSTEM,
        user=user_filled,
        max_tokens=500,
        response_format="json",
    )
    # response_format="json" del helper ya valida que parsee.
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        # Fallback: marca _failed pero devuelve estructura minima.
        logger.warning("research_t4_nowebsite JSON parse fail nif=%s: %s", company.get("nif"), e)
        data = {
            "_failed": True,
            "_failed_reason": "json_parse_error",
            "_research_method": "option_c_nowebsite",
            "_raw_text": text[:500],
        }
    # Garantiza marker para distinguir de research con scraping.
    data.setdefault("_research_method", "option_c_nowebsite")
    return T4ResearchResult(
        research_data=data,
        tokens_in=int(meta.get("tokens_in", 0)),
        tokens_out=int(meta.get("tokens_out", 0)),
        cost_usd=meta.get("cost_usd"),
    )
