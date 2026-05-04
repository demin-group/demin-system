"""Cliente Anthropic + Voyage para los workers.

`MODEL_FOR_TASK` enruta cada llamada al modelo correcto (Lección 3) — los
workers NUNCA hardcodean el `model_id`, siempre llaman a `call_llm(task=...)`.

Embeddings vía Voyage `voyage-multilingual-2` (1024 dim, validada al volver).

Retries con tenacity:
- 3 intentos, exponential backoff 1s/2s/4s.
- Solo sobre errores transitorios (rate limit, 5xx, timeout, conexión).
- 4xx (auth, bad request, etc.) NO se reintentan.

Pricing: tabla local. Mientras esté vacía, `cost_usd` queda en `None` y el
log emite warning. Las cifras reales hay que sacarlas de
https://www.anthropic.com/pricing#api y datarlas el día que se rellenen.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Literal

import anthropic
import voyageai
import voyageai.error as voyage_error
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .config import settings

logger = logging.getLogger("demin.llm")
if not logger.handlers:
    logging.basicConfig(
        level=settings.LOG_LEVEL,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

# ─── enrutamiento por tarea (Lección 3) ─────────────────────────────────────
MODEL_FOR_TASK: dict[str, str] = {
    "classify_descr": settings.ANTHROPIC_MODEL_CLASSIFY,
    "research_prospect": settings.ANTHROPIC_MODEL_RESEARCH,
    "generate_draft": settings.ANTHROPIC_MODEL_GENERATE,
    "classify_reply": settings.ANTHROPIC_MODEL_REPLY,
    "suggest_response": settings.ANTHROPIC_MODEL_GENERATE,
}

# ─── pricing local ──────────────────────────────────────────────────────────
# TODO(pricing): rellenar con cifras verificadas de
# https://www.anthropic.com/pricing#api y datar el día que se haga.
# Formato: USD por 1M tokens, separados input/output.
PRICING_USD_PER_MTOKENS: dict[str, dict[str, float]] = {
    # "claude-haiku-4-5-20251001": {"input": <USD/M>, "output": <USD/M>},
    # "claude-sonnet-4-6":         {"input": <USD/M>, "output": <USD/M>},
}

# ─── timeouts y clientes ────────────────────────────────────────────────────
_ANTHROPIC_TIMEOUT_S = 60.0

_anthropic_client = anthropic.Anthropic(
    api_key=settings.ANTHROPIC_API_KEY,
    timeout=_ANTHROPIC_TIMEOUT_S,
)

# voyageai 0.3.x no expone `timeout` ni en Client(...) ni en .embed(...).
# El SDK aplica un default interno (~120s). Si fuera necesario afinarlo,
# habría que parchear la sesión httpx subyacente o cambiar de SDK.
_voyage_client = voyageai.Client(api_key=settings.VOYAGE_API_KEY)

# ─── errores que se reintentan ──────────────────────────────────────────────
_ANTHROPIC_RETRYABLE: tuple[type[BaseException], ...] = (
    anthropic.RateLimitError,
    anthropic.APIConnectionError,
    anthropic.APITimeoutError,
    anthropic.InternalServerError,
)
_VOYAGE_RETRYABLE: tuple[type[BaseException], ...] = (
    voyage_error.RateLimitError,
    voyage_error.ServerError,
    voyage_error.ServiceUnavailableError,
    voyage_error.Timeout,
    voyage_error.APIConnectionError,
)


def _compute_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float | None:
    pricing = PRICING_USD_PER_MTOKENS.get(model)
    if pricing is None:
        logger.warning(
            "model %r no esta en PRICING_USD_PER_MTOKENS - cost_usd=None hasta "
            "rellenar tabla (https://www.anthropic.com/pricing#api)",
            model,
        )
        return None
    return (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000.0


@retry(
    retry=retry_if_exception_type(_ANTHROPIC_RETRYABLE),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)
def _anthropic_messages_create(
    model: str, system: str, user: str, max_tokens: int
) -> Any:
    return _anthropic_client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )


def call_llm(
    task: str,
    system: str,
    user: str,
    max_tokens: int = 1024,
    response_format: Literal["text", "json"] = "text",
) -> tuple[str, dict[str, Any]]:
    """Llama a Anthropic con el modelo asignado a `task`.

    Devuelve `(texto, meta)` donde `meta` incluye `task`, `model`,
    `tokens_in`, `tokens_out`, `cost_usd` (puede ser `None` si el modelo
    no está en la tabla de pricing) y `elapsed_ms`.

    Si `response_format="json"`, valida que el texto parsee como JSON
    (lanza `json.JSONDecodeError` si no). NO reintenta el formato.

    `task` debe ser una clave de `MODEL_FOR_TASK`. Cualquier otro valor
    es `ValueError` — no hay default silencioso (Lección 3).
    """
    if task not in MODEL_FOR_TASK:
        raise ValueError(
            f"task {task!r} no está en MODEL_FOR_TASK. "
            f"Tasks válidas: {sorted(MODEL_FOR_TASK)}"
        )
    model = MODEL_FOR_TASK[task]
    started = time.monotonic()
    msg = _anthropic_messages_create(model, system, user, max_tokens)
    elapsed_ms = int((time.monotonic() - started) * 1000)

    text = "".join(
        block.text for block in msg.content if getattr(block, "type", None) == "text"
    ).strip()

    if response_format == "json":
        json.loads(text)

    tokens_in = msg.usage.input_tokens
    tokens_out = msg.usage.output_tokens
    cost_usd = _compute_cost_usd(model, tokens_in, tokens_out)
    meta: dict[str, Any] = {
        "task": task,
        "model": model,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": cost_usd,
        "elapsed_ms": elapsed_ms,
    }
    logger.info(
        "llm_call task=%s model=%s tokens_in=%d tokens_out=%d cost_usd=%s elapsed_ms=%d",
        task,
        model,
        tokens_in,
        tokens_out,
        f"{cost_usd:.6f}" if cost_usd is not None else "None",
        elapsed_ms,
    )
    return text, meta


@retry(
    retry=retry_if_exception_type(_VOYAGE_RETRYABLE),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    reraise=True,
)
def _voyage_embed_call(texts: list[str]) -> list[list[float]]:
    res = _voyage_client.embed(
        texts,
        model=settings.VOYAGE_MODEL,
        input_type="document",
    )
    return res.embeddings


def embed(texts: list[str]) -> list[list[float]]:
    """Embeds un batch de textos con `settings.VOYAGE_MODEL`.

    Valida que la dim del primer vector coincida con
    `settings.VOYAGE_EMBEDDING_DIM` (default 1024 = `voyage-multilingual-2`).
    Si la dim no encaja, lanza `RuntimeError` — no se permite mezclar dims
    en `kb_chunks` (vector(1024) en el schema §6.2).
    """
    if not texts:
        return []
    started = time.monotonic()
    vectors = _voyage_embed_call(texts)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    if len(vectors) != len(texts):
        raise RuntimeError(
            f"Voyage devolvió {len(vectors)} vectores para {len(texts)} textos"
        )
    expected = settings.VOYAGE_EMBEDDING_DIM
    actual = len(vectors[0])
    if actual != expected:
        raise RuntimeError(
            f"Dim de embedding inesperada: esperado {expected}, recibido {actual} "
            f"(modelo {settings.VOYAGE_MODEL})"
        )
    logger.info(
        "voyage_embed n=%d dim=%d model=%s elapsed_ms=%d",
        len(texts),
        actual,
        settings.VOYAGE_MODEL,
        elapsed_ms,
    )
    return vectors
