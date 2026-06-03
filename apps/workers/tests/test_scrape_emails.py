"""Tests de las funciones puras de pipeline/scrape_emails.py (sin red, sin BD).

Sesión 2026-06-03 — recuperación T2 sin contactos vía scraping de webs.
"""
from __future__ import annotations

from pipeline.scrape_emails import extract_emails, rank_email


# ─── rank_email: orden PM 2026-06-03 ───────────────────────────────────────


def test_rank_persona_va_primero() -> None:
    assert rank_email("paula.otin@empresa.es") == 0
    assert rank_email("dlepa@geneop.com") == 0


def test_rank_orden_pm() -> None:
    """persona > comercial > obras > proyectos > genéricos operativos >
    info > contacto > administracion > resto genérico."""
    ranks = [
        rank_email("nombre.apellido@x.es"),
        rank_email("comercial@x.es"),
        rank_email("obras@x.es"),
        rank_email("proyectos@x.es"),
        rank_email("gerencia@x.es"),
        rank_email("info@x.es"),
        rank_email("contacto@x.es"),
        rank_email("administracion@x.es"),
        rank_email("ventas@x.es"),
    ]
    assert ranks == sorted(ranks)
    assert len(set(ranks)) == len(ranks) - 0  # estrictamente creciente aquí


def test_rank_descarta_negativa_d20_y_legales() -> None:
    for local in ("rrhh", "prensa", "noreply", "soporte", "dpo", "rgpd", "privacidad"):
        assert rank_email(f"{local}@x.es") is None, local


def test_rank_empresa_arroba_empresa_es_generico() -> None:
    """`empresa@empresa.es` es buzón corporativo de marca, no persona
    (caso real run 2026-06-03: iycsa@iycsa.es, trauxia@trauxia.es)."""
    assert rank_email("iycsa@iycsa.es") == 8
    assert rank_email("divegon@divegon.com") == 8


# ─── extract_emails ────────────────────────────────────────────────────────

_HTML = """
<html><body>
<a href="mailto:info@acme.es">escríbenos</a>
<a href="mailto:Maria.Lopez@acme.es?subject=hola">María</a>
<p>obras@acme.es | comercial@tercero.com | logo@2x.png</p>
<p>soporte@acme.es</p>
</body></html>
"""


def test_extract_prioriza_persona_y_filtra() -> None:
    out = extract_emails(_HTML, "acme.es")
    emails = [e.email for e in out]
    assert emails[0] == "maria.lopez@acme.es"  # persona primero
    assert "obras@acme.es" in emails
    assert "info@acme.es" in emails
    assert "comercial@tercero.com" not in emails  # dominio ajeno
    assert "soporte@acme.es" not in emails        # whitelist negativa D20
    assert all("@2x" not in e for e in emails)    # junk de assets


def test_extract_mailto_gana_sobre_regex() -> None:
    out = extract_emails(_HTML, "acme.es")
    by_email = {e.email: e for e in out}
    assert by_email["info@acme.es"].via_mailto is True


def test_extract_dedup_case_insensitive() -> None:
    html = '<a href="mailto:Info@acme.es">x</a> info@acme.es INFO@ACME.ES'
    out = extract_emails(html, "acme.es")
    assert len([e for e in out if e.email == "info@acme.es"]) == 1
