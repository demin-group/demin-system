"""Tests de pipeline.generate_draft.

Sin red ni LLM real (monkeypatch sobre `call_llm`), sin BD (las funciones SQL
quedan cubiertas por el smoke E2E). Cubre:
- validate_post_generation (4 reglas §10.3)
- kb_retrieval_query_for_company
- format_kb_chunks
- parse_llm_json (tolerancia a code fences, casos inválidos)
- compose_user_vars (rellenado defensivo de defaults)
- render_user_template (no rompe con {} del JSON output literal)
- _load_prompt_for_angle (lee los 3 archivos reales del repo)
- process_one_contact con monkeypatch (happy path, kb fail, llm error,
  json_parse fail, validation warnings tras retries)
"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from pipeline.generate_draft import (
    KB_RETRIEVAL_TOP_N,
    MAX_REGENERATION_RETRIES,
    GeneratedDraft,
    PendingContact,
    _load_prompt_for_angle,
    compose_user_vars,
    format_kb_chunks,
    kb_retrieval_query_for_company,
    parse_llm_json,
    process_one_contact,
    render_user_template,
    validate_post_generation,
)

# ─── Helpers ───────────────────────────────────────────────────────────────


_DEFAULT_RESEARCH = {
    "tipo_actividad_concreta": "constructora obra residencial",
    "tipo_obra_que_hacen": ["residencial", "reforma"],
    "proyectos_recientes": ["torre Madrid", "edificio Salamanca"],
    "hooks_de_personalizacion": ["coordinan reformas integrales", "premium"],
}


def _make_contact(
    *,
    email_type: str = "decisor",
    nombre_contacto: str | None = "Juan Pérez",
    cargo_contacto: str | None = "Director Técnico",
    research_data: dict[str, Any] | None = None,
) -> PendingContact:
    rd = _DEFAULT_RESEARCH if research_data is None else research_data
    return PendingContact(
        contact_id="11111111-1111-1111-1111-111111111111",
        company_id="22222222-2222-2222-2222-222222222222",
        email="juan@acme.es",
        email_type=email_type,
        email_priority=1,
        nombre_contacto=nombre_contacto,
        cargo_contacto=cargo_contacto,
        nif="A12345678",
        nombre_empresa="ACME SL",
        tier="T3",
        research_data=rd,
    )


# ─── 1. validate_post_generation (4 reglas §10.3) ──────────────────────────


def _body_n(n: int) -> str:
    """Crea body con n palabras."""
    return " ".join(f"palabra{i}" for i in range(n))


def _subject_n(n: int) -> str:
    return " ".join(f"w{i}" for i in range(n))


def test_validate_passes_when_all_rules_ok() -> None:
    failures = validate_post_generation(_subject_n(5), _body_n(120))
    assert failures == []


@pytest.mark.parametrize("n_words,label", [(49, "body_too_short:49"), (181, "body_too_long:181")])
def test_validate_body_word_bounds(n_words: int, label: str) -> None:
    failures = validate_post_generation(_subject_n(5), _body_n(n_words))
    assert any(f.startswith(label) for f in failures), f"falta {label} en {failures}"


@pytest.mark.parametrize(
    "n_words,label",
    [(2, "subject_too_short:2"), (9, "subject_too_long:9")],
)
def test_validate_subject_word_bounds(n_words: int, label: str) -> None:
    failures = validate_post_generation(_subject_n(n_words), _body_n(120))
    assert any(f.startswith(label) for f in failures)


def test_validate_body_at_lower_bound_50_is_ok() -> None:
    assert validate_post_generation(_subject_n(5), _body_n(50)) == []


def test_validate_body_at_upper_bound_180_is_ok() -> None:
    assert validate_post_generation(_subject_n(5), _body_n(180)) == []


def test_validate_subject_at_bounds_3_and_8_are_ok() -> None:
    assert validate_post_generation(_subject_n(3), _body_n(120)) == []
    assert validate_post_generation(_subject_n(8), _body_n(120)) == []


@pytest.mark.parametrize(
    "subject,body",
    [
        ("hola que tal!", _body_n(120)),
        (_subject_n(5), "Esto es un cuerpo " * 30 + "!"),
    ],
)
def test_validate_detects_exclamation(subject: str, body: str) -> None:
    failures = validate_post_generation(subject, body)
    assert "has_exclamation" in failures


def test_validate_detects_emoji_in_body() -> None:
    body = "Esto es un cuerpo 🚀 " * 20
    failures = validate_post_generation(_subject_n(5), body)
    assert "has_emoji" in failures


@pytest.mark.parametrize(
    "phrase",
    [
        "garantizamos resultados",
        "lo hacemos en 3 días",
        "por 500 €",
        "en 24 horas",
        "precio cerrado 1000",
    ],
)
def test_validate_detects_promises(phrase: str) -> None:
    body = _body_n(50) + " " + phrase + " " + _body_n(50)
    failures = validate_post_generation(_subject_n(5), body)
    assert "has_promise" in failures, f"no pilló: {phrase!r}"


def test_validate_returns_multiple_failures_when_multiple_rules_fail() -> None:
    failures = validate_post_generation(_subject_n(2) + "!", _body_n(200) + " 🚀")
    assert "subject_too_short:3" in failures or any(
        f.startswith("subject_too_short") for f in failures
    )
    assert any(f.startswith("body_too_long") for f in failures)
    assert "has_exclamation" in failures
    assert "has_emoji" in failures


# ─── 2. kb_retrieval_query_for_company ─────────────────────────────────────


def test_kb_query_concatenates_actividad_and_first_hook() -> None:
    item = _make_contact()
    out = kb_retrieval_query_for_company(item)
    assert "constructora obra residencial" in out
    assert "coordinan reformas integrales" in out


def test_kb_query_falls_back_to_company_name_when_research_empty() -> None:
    item = _make_contact(research_data={})
    assert kb_retrieval_query_for_company(item) == "ACME SL"


def test_kb_query_handles_missing_hooks() -> None:
    item = _make_contact(
        research_data={
            "tipo_actividad_concreta": "constructora",
            "hooks_de_personalizacion": [],
        }
    )
    out = kb_retrieval_query_for_company(item)
    assert out == "constructora"


# ─── 3. format_kb_chunks ───────────────────────────────────────────────────


def test_format_kb_chunks_concatenates_with_headers() -> None:
    chunks = [
        {"category": "servicios", "titulo": "Doc1", "contenido": "DEMIN tira tabiques"},
        {"category": "icp", "titulo": "Doc2", "contenido": "Constructoras pequeñas"},
    ]
    out = format_kb_chunks(chunks)
    assert "chunk 1" in out
    assert "chunk 2" in out
    assert "DEMIN tira tabiques" in out
    assert "Constructoras pequeñas" in out


def test_format_kb_chunks_handles_empty() -> None:
    out = format_kb_chunks([])
    assert "sin chunks" in out.lower()


# ─── 4. parse_llm_json ─────────────────────────────────────────────────────


_VALID_DRAFT_JSON = json.dumps({
    "subject": "Vaciados interiores en obras Nozar",
    "body": "Texto del correo " + " palabra" * 60,
    "razonamiento_breve": "He elegido el hook de la calle Murcia",
})


def test_parse_valid_json() -> None:
    s, b, r = parse_llm_json(_VALID_DRAFT_JSON)
    assert s == "Vaciados interiores en obras Nozar"
    assert b.startswith("Texto del correo")
    assert r.startswith("He elegido")


def test_parse_strips_code_fences() -> None:
    raw = "```json\n" + _VALID_DRAFT_JSON + "\n```"
    s, b, _ = parse_llm_json(raw)
    assert s.startswith("Vaciados")


def test_parse_missing_subject_raises() -> None:
    raw = json.dumps({"body": "x", "razonamiento_breve": "y"})
    with pytest.raises(ValueError, match="subject"):
        parse_llm_json(raw)


def test_parse_empty_body_raises() -> None:
    raw = json.dumps({"subject": "x", "body": "", "razonamiento_breve": "y"})
    with pytest.raises(ValueError, match="body"):
        parse_llm_json(raw)


def test_parse_non_dict_raises() -> None:
    with pytest.raises(ValueError, match="objeto"):
        parse_llm_json('["lista", "no", "dict"]')


def test_parse_invalid_json_raises() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_llm_json("no soy json {{{")


def test_parse_razonamiento_optional_defaults_to_empty() -> None:
    raw = json.dumps({"subject": "x", "body": "y"})
    s, b, r = parse_llm_json(raw)
    assert r == ""


# ─── 5. compose_user_vars ──────────────────────────────────────────────────


def test_compose_user_vars_happy_path() -> None:
    item = _make_contact()
    out = compose_user_vars(item, kb_chunks_text="CHUNKS_AQUI", correos_previos=None)
    assert out["nombre"] == "ACME SL"
    assert out["email_type"] == "decisor"
    assert out["nombre_destinatario"] == "Juan Pérez"
    assert out["cargo_destinatario"] == "Director Técnico"
    assert "constructora obra residencial" in out["tipo_actividad_concreta"]
    assert "residencial, reforma" in out["tipo_obra_que_hacen"]
    assert "torre Madrid" in out["proyectos_recientes"]
    assert "coordinan reformas integrales" in out["hooks_de_personalizacion"]
    assert out["kb_chunks"] == "CHUNKS_AQUI"
    assert "correos_previos" not in out


def test_compose_user_vars_with_correos_previos() -> None:
    item = _make_contact()
    out = compose_user_vars(item, kb_chunks_text="K", correos_previos="prev1\nprev2")
    assert out["correos_previos"] == "prev1\nprev2"


def test_compose_user_vars_fills_missing_fields_with_defaults() -> None:
    item = _make_contact(research_data={})
    out = compose_user_vars(item, kb_chunks_text="K", correos_previos=None)
    assert out["tipo_actividad_concreta"] == ""
    assert out["tipo_obra_que_hacen"] == "(no identificado)"
    assert out["proyectos_recientes"] == "(no se han identificado)"
    assert out["hooks_de_personalizacion"] == "(no se han identificado)"


def test_compose_user_vars_handles_none_contacto_fields() -> None:
    item = _make_contact(nombre_contacto=None, cargo_contacto=None)
    out = compose_user_vars(item, "K", None)
    assert out["nombre_destinatario"] == ""
    assert out["cargo_destinatario"] == ""


# ─── 6. render_user_template ───────────────────────────────────────────────


def test_render_user_template_replaces_placeholders() -> None:
    template = "Hola {nombre}, eres {email_type}"
    out = render_user_template(template, {"nombre": "ACME", "email_type": "decisor"})
    assert out == "Hola ACME, eres decisor"


def test_render_user_template_does_not_break_with_json_braces() -> None:
    """Si el template contiene literalmente `{"subject": ...}` (output JSON
    del prompt), str.replace no debe interferir — confirmamos que el render
    no rompe con llaves JSON."""
    template = (
        'EMPRESA: {nombre}\n'
        'OUTPUT: {"subject": "x", "body": "y"}'
    )
    out = render_user_template(template, {"nombre": "ACME"})
    assert "EMPRESA: ACME" in out
    assert '{"subject": "x", "body": "y"}' in out


def test_render_user_template_unknown_placeholders_remain_literal() -> None:
    """Si una variable no está en vars_, su placeholder queda literal —
    no falla. Útil para detectar templates desincronizados con el código."""
    template = "Hola {desconocido}, {nombre}"
    out = render_user_template(template, {"nombre": "ACME"})
    assert "{desconocido}" in out
    assert "ACME" in out


# ─── 7. _load_prompt_for_angle (lee los archivos reales del repo) ──────────


@pytest.mark.parametrize("angle", ("opening", "reframe", "closing"))
def test_load_prompt_for_each_angle(angle: str) -> None:
    system, user = _load_prompt_for_angle(angle)  # type: ignore[arg-type]
    assert "DEMIN" in system
    assert "Gonzalo" in system
    assert "{nombre}" in user
    assert "{email_type}" in user
    assert "{kb_chunks}" in user


# ─── 8. process_one_contact (monkeypatch sobre call_llm + retrieval) ──────


def _patch_call_llm(
    monkeypatch: pytest.MonkeyPatch,
    response_text: str,
    *,
    raises: Exception | None = None,
    sequence: list[str] | None = None,
) -> dict[str, Any]:
    """Si `sequence` se pasa, devuelve un response distinto cada llamada
    (útil para tests de retry de validation)."""
    captured: dict[str, Any] = {"calls": 0, "users": []}

    def fake_call_llm(
        task: str, system: str, user: str, max_tokens: int = 1024,
    ) -> tuple[str, dict[str, Any]]:
        captured["calls"] += 1
        captured["users"].append(user)
        if raises is not None:
            raise raises
        if sequence is not None:
            idx = min(captured["calls"] - 1, len(sequence) - 1)
            return sequence[idx], {"task": task, "model": "claude-sonnet-4-6",
                                    "tokens_in": 1000, "tokens_out": 200,
                                    "cost_usd": 0.005, "elapsed_ms": 1234}
        return response_text, {
            "task": task, "model": "claude-sonnet-4-6",
            "tokens_in": 1000, "tokens_out": 200, "cost_usd": 0.005, "elapsed_ms": 1234,
        }

    import shared.llm
    monkeypatch.setattr(shared.llm, "call_llm", fake_call_llm)
    return captured


def _patch_kb_retrieval(monkeypatch: pytest.MonkeyPatch, chunks: list[dict[str, Any]]) -> None:
    import pipeline.generate_draft as gd
    monkeypatch.setattr(gd, "kb_retrieval", lambda env, q: chunks)


def test_process_one_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_kb_retrieval(monkeypatch, [{"category": "servicios", "titulo": "x", "contenido": "DEMIN demolición"}])
    captured = _patch_call_llm(monkeypatch, _VALID_DRAFT_JSON)

    item = _make_contact()
    result = process_one_contact("dev", item, "opening", "SYS", "USR {nombre}")

    assert result.success is True
    assert result.draft is not None
    assert result.draft.failed_validations == []
    assert "ACME SL" in captured["users"][0]
    assert captured["calls"] == 1


def test_process_one_kb_retrieval_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import pipeline.generate_draft as gd

    def fail(env: str, q: str) -> list[dict[str, Any]]:
        raise RuntimeError("voyage timeout")
    monkeypatch.setattr(gd, "kb_retrieval", fail)

    item = _make_contact()
    result = process_one_contact("dev", item, "opening", "SYS", "USR {nombre}")
    assert result.success is False
    assert result.draft is None
    assert "kb_retrieval_failed" in (result.error or "")


def test_process_one_llm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_kb_retrieval(monkeypatch, [])
    _patch_call_llm(monkeypatch, "", raises=RuntimeError("anthropic 503"))

    item = _make_contact()
    result = process_one_contact("dev", item, "opening", "SYS", "USR {nombre}")
    assert result.success is False
    assert "llm_error" in (result.error or "")


def test_process_one_json_parse_retries_then_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_kb_retrieval(monkeypatch, [])
    captured = _patch_call_llm(
        monkeypatch, "no soy json", sequence=["no soy json"] * (MAX_REGENERATION_RETRIES + 1)
    )

    item = _make_contact()
    result = process_one_contact("dev", item, "opening", "SYS", "USR {nombre}")
    assert result.success is False
    assert "json_parse" in (result.error or "")
    assert captured["calls"] == MAX_REGENERATION_RETRIES + 1


def test_process_one_validation_warnings_after_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si el LLM nunca produce un draft que pase validaciones, tras los
    reintentos el draft entra como success=True con failed_validations
    rellenas — el HITL lo verá marcado."""
    _patch_kb_retrieval(monkeypatch, [])
    bad = json.dumps({
        "subject": "uno!",  # subject_too_short + has_exclamation
        "body": _body_n(30),  # body_too_short
        "razonamiento_breve": "x",
    })
    captured = _patch_call_llm(monkeypatch, bad, sequence=[bad] * (MAX_REGENERATION_RETRIES + 1))

    item = _make_contact()
    result = process_one_contact("dev", item, "opening", "SYS", "USR {nombre}")
    assert result.success is True
    assert result.draft is not None
    assert len(result.draft.failed_validations) > 0
    assert any("body_too_short" in f for f in result.draft.failed_validations)
    assert captured["calls"] == MAX_REGENERATION_RETRIES + 1


def test_process_one_validation_passes_on_second_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Si el primer draft falla validación pero el segundo pasa, success
    sin failed_validations y solo 2 llamadas LLM."""
    _patch_kb_retrieval(monkeypatch, [])
    bad = json.dumps({"subject": "uno!", "body": _body_n(30), "razonamiento_breve": "x"})
    good = _VALID_DRAFT_JSON
    captured = _patch_call_llm(monkeypatch, "", sequence=[bad, good])

    item = _make_contact()
    result = process_one_contact("dev", item, "opening", "SYS", "USR {nombre}")
    assert result.success is True
    assert result.draft is not None
    assert result.draft.failed_validations == []
    assert captured["calls"] == 2
