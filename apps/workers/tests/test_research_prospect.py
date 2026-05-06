"""Tests de pipeline.research_prospect.

Sin red real (httpx.MockTransport). Sin LLM real (monkeypatch sobre
`call_llm`). Sin BD (las funciones SQL `fetch_pending` / `write_result`
quedan cubiertas por el smoke real en dev).
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from pipeline.research_prospect import (
    _MAX_TEXT_CHARS,
    Pending,
    Result,
    ScrapeOutcome,
    _load_prompt,
    clean_personas_extraidas,
    compose_pages_text,
    extract_text_from_html,
    parse_research_json,
    process_one,
    resolve_base_url,
    scrape_company_web,
    truncate_to_budget,
)

# ─── 1. resolve_base_url ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("acme.es", "https://acme.es"),
        ("https://acme.es", "https://acme.es"),
        ("http://www.acme.es", "https://acme.es"),
        ("ACME.ES/contacto", "https://acme.es"),
        ("https://acme.co.uk/about", "https://acme.co.uk"),
        ("  acme.es  ", "https://acme.es"),
    ],
)
def test_resolve_base_url_canonicalizes(raw: str, expected: str) -> None:
    assert resolve_base_url(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None, "garbage", "no-suffix"])
def test_resolve_base_url_returns_none_for_invalid(raw: str | None) -> None:
    assert resolve_base_url(raw) is None


# ─── 2. extract_text_from_html ─────────────────────────────────────────────


def test_extract_text_strips_script_style_nav_footer() -> None:
    html = """
    <html><head><style>body { color: red; }</style></head>
    <body>
      <nav>menu</nav>
      <header>cabecera</header>
      <main>
        <h1>Bienvenidos</h1>
        <p>Somos ACME.</p>
        <script>alert('x')</script>
      </main>
      <footer>pie</footer>
    </body></html>
    """
    out = extract_text_from_html(html)
    assert "Bienvenidos" in out
    assert "Somos ACME." in out
    for noise in ("alert", "color: red", "menu", "cabecera", "pie"):
        assert noise not in out


def test_extract_text_collapses_whitespace() -> None:
    html = "<body><p>  hola    mundo  </p>\n\n<p>  segunda  línea  </p></body>"
    out = extract_text_from_html(html)
    assert "hola mundo" in out
    assert "segunda línea" in out
    assert "  " not in out


def test_extract_text_handles_empty() -> None:
    assert extract_text_from_html("") == ""
    assert extract_text_from_html("   ") == ""


def test_extract_text_handles_no_body() -> None:
    """HTML sin <body> (ej. solo <head>) devuelve cadena vacía sin crashear."""
    assert extract_text_from_html("<html><head><title>x</title></head></html>") == ""


# ─── 3. truncate_to_budget ─────────────────────────────────────────────────


def test_truncate_returns_input_if_within_budget() -> None:
    text = "hola mundo"
    assert truncate_to_budget(text, max_chars=100) == text


def test_truncate_cuts_at_word_boundary_with_marker() -> None:
    text = "palabra " * 100  # 800 chars
    out = truncate_to_budget(text, max_chars=50)
    assert len(out) <= 50 + 50  # cut + marker
    assert "[... truncado por longitud ...]" in out
    # No debería partir una palabra
    assert not out.split("\n\n[")[0].endswith("palabr")


def test_truncate_default_budget_is_32k() -> None:
    assert _MAX_TEXT_CHARS == 32_000


# ─── 4. compose_pages_text ─────────────────────────────────────────────────


def test_compose_pages_text_separates_with_url_headers() -> None:
    pages = {
        "https://acme.es": "<body><p>Home: ACME</p></body>",
        "https://acme.es/equipo": "<body><p>Director: Juan Pérez</p></body>",
    }
    out = compose_pages_text(pages)
    assert "--- https://acme.es ---" in out
    assert "--- https://acme.es/equipo ---" in out
    assert "Home: ACME" in out
    assert "Director: Juan Pérez" in out


def test_compose_pages_text_skips_empty_extracts() -> None:
    pages = {
        "https://acme.es": "<body><p>texto</p></body>",
        "https://acme.es/empty": "<html><head></head></html>",  # sin body
    }
    out = compose_pages_text(pages)
    assert "texto" in out
    assert "/empty" not in out


# ─── 5. clean_personas_extraidas ───────────────────────────────────────────


def test_clean_personas_keeps_valid_entries() -> None:
    raw = [
        {"nombre": "Juan Pérez", "cargo_si_aparece": "Director", "fuente_url": "x"},
        {"nombre": "María", "cargo_si_aparece": "", "fuente_url": ""},  # cargo vacío permitido
    ]
    out = clean_personas_extraidas(raw)
    assert len(out) == 2
    assert out[0] == {"nombre": "Juan Pérez", "cargo_si_aparece": "Director", "fuente_url": "x"}
    assert out[1] == {"nombre": "María", "cargo_si_aparece": "", "fuente_url": ""}


@pytest.mark.parametrize(
    "raw",
    [
        [{"nombre": "", "cargo_si_aparece": "x"}],
        [{"nombre": None, "cargo_si_aparece": "x"}],
        [{"cargo_si_aparece": "x"}],  # sin clave nombre
        [{"nombre": "  "}],
        ["string-en-vez-de-dict"],
        [None],
        [42],
    ],
)
def test_clean_personas_drops_invalid_entries(raw: list[Any]) -> None:
    assert clean_personas_extraidas(raw) == []


def test_clean_personas_handles_non_list() -> None:
    assert clean_personas_extraidas(None) == []
    assert clean_personas_extraidas("string") == []
    assert clean_personas_extraidas({"nombre": "x"}) == []


def test_clean_personas_strips_whitespace() -> None:
    raw = [{"nombre": "  Juan  ", "cargo_si_aparece": "  CEO  ", "fuente_url": "  url  "}]
    assert clean_personas_extraidas(raw) == [
        {"nombre": "Juan", "cargo_si_aparece": "CEO", "fuente_url": "url"},
    ]


def test_clean_personas_coerces_non_string_cargo_to_empty() -> None:
    """Si el LLM devuelve cargo como número o null, lo silenciamos a "" en lugar
    de descartar la entrada — el nombre solo ya es útil para el cruce."""
    raw = [{"nombre": "Juan", "cargo_si_aparece": 42, "fuente_url": None}]
    assert clean_personas_extraidas(raw) == [
        {"nombre": "Juan", "cargo_si_aparece": "", "fuente_url": ""},
    ]


# ─── 6. parse_research_json ────────────────────────────────────────────────


_VALID_JSON = """
{
  "tipo_actividad_concreta": "constructora obra residencial",
  "tamano_aparente": "mediano",
  "tipo_obra_que_hacen": ["residencial", "reforma"],
  "proyectos_recientes": ["torre Madrid", "edificio Salamanca"],
  "noticias_o_novedades": "premio 2025",
  "lenguaje_que_usan": "corporativo",
  "valores_que_destacan": ["calidad", "puntualidad"],
  "hooks_de_personalizacion": ["coordinan reformas integrales", "cliente premium"],
  "personas_extraidas": [
    {"nombre": "Juan Pérez", "cargo_si_aparece": "Director Técnico", "fuente_url": "https://x.es/equipo"}
  ]
}
"""


def test_parse_valid_json_returns_clean_dict() -> None:
    out = parse_research_json(_VALID_JSON)
    assert out["tipo_actividad_concreta"] == "constructora obra residencial"
    assert out["tamano_aparente"] == "mediano"
    assert out["tipo_obra_que_hacen"] == ["residencial", "reforma"]
    assert len(out["proyectos_recientes"]) == 2
    assert out["lenguaje_que_usan"] == "corporativo"
    assert len(out["personas_extraidas"]) == 1


def test_parse_strips_code_fences() -> None:
    raw = "```json\n" + _VALID_JSON + "\n```"
    out = parse_research_json(raw)
    assert out["tipo_actividad_concreta"] == "constructora obra residencial"


def test_parse_invalid_tamano_falls_back_to_incierto() -> None:
    raw = json.dumps({"tamano_aparente": "enorme"})
    assert parse_research_json(raw)["tamano_aparente"] == "incierto"


def test_parse_filters_unknown_tipo_obra() -> None:
    raw = json.dumps({"tipo_obra_que_hacen": ["residencial", "espacial", "comercial"]})
    out = parse_research_json(raw)
    assert out["tipo_obra_que_hacen"] == ["residencial", "comercial"]


def test_parse_invalid_lenguaje_becomes_empty_string() -> None:
    raw = json.dumps({"lenguaje_que_usan": "alienígena"})
    assert parse_research_json(raw)["lenguaje_que_usan"] == ""


def test_parse_truncates_proyectos_to_3() -> None:
    raw = json.dumps({"proyectos_recientes": ["a", "b", "c", "d", "e"]})
    assert parse_research_json(raw)["proyectos_recientes"] == ["a", "b", "c"]


def test_parse_truncates_valores_to_4() -> None:
    raw = json.dumps({"valores_que_destacan": ["1", "2", "3", "4", "5", "6"]})
    assert parse_research_json(raw)["valores_que_destacan"] == ["1", "2", "3", "4"]


def test_parse_missing_fields_default_to_empty() -> None:
    out = parse_research_json("{}")
    assert out["tipo_actividad_concreta"] == ""
    assert out["tamano_aparente"] == "incierto"
    assert out["tipo_obra_que_hacen"] == []
    assert out["proyectos_recientes"] == []
    assert out["personas_extraidas"] == []
    assert out["hooks_de_personalizacion"] == []


def test_parse_non_dict_raises() -> None:
    with pytest.raises(ValueError, match="objeto"):
        parse_research_json('["lista", "en lugar", "de dict"]')


def test_parse_invalid_json_raises_decode_error() -> None:
    with pytest.raises(json.JSONDecodeError):
        parse_research_json("no soy json {{{")


# ─── 7. _load_prompt (real, lee el .md del repo) ───────────────────────────


def test_load_prompt_returns_system_and_user_template() -> None:
    system, user_template = _load_prompt()
    assert "investigador comercial" in system.lower() or "demin" in system.lower()
    assert "{nombre}" in user_template
    assert "{texto_web}" in user_template


# ─── 8. scrape_company_web (httpx mockeado) ────────────────────────────────


def _make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_scrape_home_ok_with_subpaths() -> None:
    # Home con texto >500 chars para no caer en thin_html.
    home_body = "<body><h1>ACME</h1>" + "<p>somos constructores con experiencia en obra residencial y comercial.</p>" * 8 + "</body>"
    served = {
        "/": home_body,
        "/contacto": "<body><p>info@acme.es</p></body>",
        "/equipo": "<body><p>Juan Pérez, Director</p></body>",
    }

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path or "/"
        if path in served:
            return httpx.Response(200, html=served[path])
        return httpx.Response(404)

    with _make_client(handler) as client:
        out = scrape_company_web("https://acme.es", client)
    assert out.failure is None
    assert out.thin_html is False
    assert "https://acme.es" in out.pages
    assert any("contacto" in u for u in out.pages)
    assert any("equipo" in u for u in out.pages)


def test_scrape_aborts_after_4_consecutive_404() -> None:
    """Si los 4 primeros subpaths dan 404, los 4 restantes no se piden."""
    requested: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path or "/"
        requested.append(path)
        if path == "/":
            return httpx.Response(200, html="<body><p>home content texto suficiente para no ser thin</p></body>")
        return httpx.Response(404)

    with _make_client(handler) as client:
        scrape_company_web("https://acme.es", client, max_consecutive_fails=4)
    # home + 4 subpaths probados = 5 requests; los siguientes 4 saltados
    assert len(requested) == 5


def test_scrape_home_unreachable_returns_failure() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("simulated dns failure")

    with _make_client(handler) as client:
        out = scrape_company_web("https://acme.es", client)
    assert out.pages == {}
    assert out.failure is not None
    assert "connect_error" in out.failure or "home_unreachable" in out.failure


def test_scrape_home_4xx_returns_failure() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/":
            return httpx.Response(403)
        return httpx.Response(404)

    with _make_client(handler) as client:
        out = scrape_company_web("https://acme.es", client)
    assert out.pages == {}
    assert out.failure == "home_http_403"


def test_scrape_thin_html_warning() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/":
            return httpx.Response(200, html="<body><div>X</div></body>")
        return httpx.Response(404)

    with _make_client(handler) as client:
        out = scrape_company_web("https://acme.es", client)
    assert out.failure is None
    assert out.thin_html is True


def test_scrape_https_falls_back_to_http() -> None:
    """Si https falla con ConnectError, intentamos http://."""
    seen_schemes: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen_schemes.append(req.url.scheme)
        if req.url.scheme == "https":
            raise httpx.ConnectError("ssl error")
        if req.url.path == "/":
            return httpx.Response(200, html="<body><p>contenido suficiente con muchas palabras y texto</p></body>")
        return httpx.Response(404)

    with _make_client(handler) as client:
        out = scrape_company_web("https://acme.es", client)
    assert out.failure is None
    assert "http" in seen_schemes
    assert "https" in seen_schemes


# ─── 9. process_one (E2E con httpx + LLM mockeados) ────────────────────────


def _make_pending() -> Pending:
    return Pending(
        id="11111111-1111-1111-1111-111111111111",
        nif="A12345678",
        nombre="ACME SL",
        web="https://acme.es",
    )


def _patch_call_llm(
    monkeypatch: pytest.MonkeyPatch,
    response_text: str,
    *,
    raises: Exception | None = None,
) -> dict[str, Any]:
    """Monkeypatcha shared.llm.call_llm para que devuelva `response_text`
    (o levante `raises`). Devuelve dict que el test puede inspeccionar."""
    captured: dict[str, Any] = {}

    def fake_call_llm(
        task: str, system: str, user: str, max_tokens: int = 1024,
        response_format: str = "text",
    ) -> tuple[str, dict[str, Any]]:
        captured.update({"task": task, "system": system, "user": user})
        if raises is not None:
            raise raises
        return response_text, {
            "task": task, "model": "claude-sonnet-4-6",
            "tokens_in": 1000, "tokens_out": 200,
            "cost_usd": 0.005, "elapsed_ms": 1234,
        }

    import shared.llm
    monkeypatch.setattr(shared.llm, "call_llm", fake_call_llm)
    return captured


def test_process_one_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = _patch_call_llm(monkeypatch, _VALID_JSON)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/":
            return httpx.Response(200, html="<body><p>somos constructores con texto suficiente</p></body>")
        if req.url.path == "/equipo":
            return httpx.Response(200, html="<body><p>Juan Pérez Director</p></body>")
        return httpx.Response(404)

    with _make_client(handler) as client:
        system, user_template = _load_prompt()
        result = process_one(_make_pending(), client, system, user_template)

    assert result.failed is False
    assert result.research_data["tipo_actividad_concreta"] == "constructora obra residencial"
    assert len(result.research_data["personas_extraidas"]) == 1
    assert result.tokens_in == 1000
    assert "ACME SL" in captured["user"]


def test_process_one_invalid_web_returns_failed() -> None:
    item = Pending(id="x", nif="N", nombre="X", web="garbage-no-tld")
    with _make_client(lambda req: httpx.Response(200)) as client:
        result = process_one(item, client, "system", "user {nombre} {texto_web}")
    assert result.failed is True
    assert result.research_data["_failed"] == "invalid_web"


def test_process_one_scraping_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns")

    with _make_client(handler) as client:
        result = process_one(_make_pending(), client, "sys", "u {nombre} {texto_web}")
    assert result.failed is True
    assert result.research_data["_failed"] == "scraping_failed"


def test_process_one_llm_error_returns_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call_llm(monkeypatch, "", raises=RuntimeError("anthropic 503"))

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/":
            return httpx.Response(200, html="<body><p>contenido suficiente con texto</p></body>")
        return httpx.Response(404)

    with _make_client(handler) as client:
        result = process_one(_make_pending(), client, "sys", "u {nombre} {texto_web}")
    assert result.failed is True
    assert result.research_data["_failed"] == "llm_error"


def test_process_one_json_parse_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call_llm(monkeypatch, "no soy json válido {{{")

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/":
            return httpx.Response(200, html="<body><p>contenido suficiente con texto</p></body>")
        return httpx.Response(404)

    with _make_client(handler) as client:
        result = process_one(_make_pending(), client, "sys", "u {nombre} {texto_web}")
    assert result.failed is True
    assert result.research_data["_failed"] == "json_parse"
    assert "raw_excerpt" in result.research_data


def test_process_one_thin_html_marks_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call_llm(monkeypatch, _VALID_JSON)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/":
            return httpx.Response(200, html="<body><p>X</p></body>")
        return httpx.Response(404)

    with _make_client(handler) as client:
        result = process_one(_make_pending(), client, "sys", "u {nombre} {texto_web}")
    assert result.failed is False
    assert result.research_data.get("_warning") == "thin_html_possibly_spa"


def test_process_one_attaches_meta(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_call_llm(monkeypatch, _VALID_JSON)

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path in ("/", "/equipo"):
            return httpx.Response(200, html="<body><p>contenido suficiente con muchas palabras</p></body>")
        return httpx.Response(404)

    with _make_client(handler) as client:
        result = process_one(_make_pending(), client, "sys", "u {nombre} {texto_web}")
    assert result.research_data["_meta"]["base_url"] == "https://acme.es"
    assert result.research_data["_meta"]["n_pages_scraped"] >= 1
