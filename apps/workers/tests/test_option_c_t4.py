"""Tests Opcion C T4 -- funciones puras de los 4 submódulos.

Cobertura:
- infer_domain.slugify_company_name (regex + stopwords + sufijos legales).
- permute_emails: orden, prefijos, catch_all probe.
- research_t4_nowebsite._load_prompt parsea estructura.

infer_domain.infer_domain() y smtp_probe requieren red, quedan como smoke
manual del CLI (option_c_t4 --dry-run --limit 3).
"""
from __future__ import annotations

import pytest

from pipeline.infer_domain import GENERIC_DOMAIN_BLACKLIST, slugify_company_name
from pipeline.permute_emails import (
    T4_PREFIXES,
    catch_all_probe,
    permute_emails,
    CATCH_ALL_PROBE_LOCAL,
)


# ─── slugify ───────────────────────────────────────────────────────────────


def test_slugify_strips_sl_suffix() -> None:
    assert slugify_company_name("DEMOLICIONES PEREZ SL")[0] == "demolicionesperez"


def test_slugify_strips_sa_suffix() -> None:
    assert slugify_company_name("CONSTRUCCIONES MADRID SA")[0] == "construccionesmadrid"


def test_slugify_strips_long_suffix() -> None:
    assert slugify_company_name(
        "REFORMAS GARCIA SOCIEDAD LIMITADA"
    )[0] == "reformasgarcia"


def test_slugify_handles_accents() -> None:
    out = slugify_company_name("DEMOLICIÓN ESPAÑA SL")
    assert "ñ" not in out[0] and "ó" not in out[0]
    assert out[0] == "demolicionespana"


def test_slugify_returns_multiple_variants() -> None:
    out = slugify_company_name("REFORMAS GARCIA HERMANOS SL")
    # variante 1: juntas, variante 2: con guiones.
    # Variante "primera palabra" REMOVIDA tras smoke 2026-05-26 (causaba
    # falsos positivos: 'constructora' matchea constructora.es de OTRA empresa).
    assert "reformasgarciahermanos" in out
    assert "reformas-garcia-hermanos" in out
    assert "reformas" not in out, (
        "variante primera-palabra debe haberse removido (smoke 2026-05-26)"
    )


def test_slugify_no_variante_primera_palabra_constructora() -> None:
    """Regresion guard: 'CONSTRUCTORA TEPEYAC SA' NO debe producir
    'constructora' como variante -- matchearia constructora.es de OTRA
    empresa y mandariamos email a tercero."""
    out = slugify_company_name("CONSTRUCTORA TEPEYAC SA")
    assert "constructora" not in out
    assert "constructoratepeyac" in out
    assert "constructora-tepeyac" in out


def test_slugify_strips_stopwords_when_useful() -> None:
    # "GRUPO DE CONSTRUCCION MADRID SL" - "de" se quita
    out = slugify_company_name("GRUPO DE CONSTRUCCION MADRID SL")
    assert out[0] == "grupoconstruccionmadrid"


def test_slugify_empty_input() -> None:
    assert slugify_company_name("") == []
    assert slugify_company_name("   ") == []


def test_slugify_only_legal_suffix() -> None:
    # Solo el sufijo no debe devolver nada util.
    assert slugify_company_name("SL") == []


def test_slugify_dedup_variants() -> None:
    """Una sola palabra no debe duplicar entre variante-junta y guiones."""
    out = slugify_company_name("DEMOLICIONES SL")
    assert out == ["demoliciones"]


def test_generic_blacklist_contains_known_offenders() -> None:
    """Smoke 2026-05-26 vio 'constructora.es' y 'urbanismo.com' como
    falsos positivos -- deben estar en blacklist."""
    assert "constructora.es" in GENERIC_DOMAIN_BLACKLIST
    assert "constructora.com" in GENERIC_DOMAIN_BLACKLIST
    assert "urbanismo.com" in GENERIC_DOMAIN_BLACKLIST
    assert "urbanismo.es" in GENERIC_DOMAIN_BLACKLIST


# ─── permute_emails ────────────────────────────────────────────────────────


def test_permute_emails_5_prefixes() -> None:
    out = permute_emails("ejemplo.es")
    assert len(out) == 5
    assert "info@ejemplo.es" in out
    assert "contacto@ejemplo.es" in out
    assert "administracion@ejemplo.es" in out
    assert "gerencia@ejemplo.es" in out
    assert "oficina@ejemplo.es" in out


def test_permute_emails_empty_domain() -> None:
    assert permute_emails("") == []


def test_permute_order_matches_t4_prefixes() -> None:
    out = permute_emails("dom.es")
    for i, prefix in enumerate(T4_PREFIXES):
        assert out[i] == f"{prefix}@dom.es"


def test_catch_all_probe_uses_unique_random() -> None:
    probe = catch_all_probe("ejemplo.es")
    assert probe.endswith("@ejemplo.es")
    assert probe.startswith(CATCH_ALL_PROBE_LOCAL + "@")
    # NO debe coincidir con ningun prefijo real -- detectaria catch-all
    # falso si lo hiciera.
    for prefix in T4_PREFIXES:
        assert prefix != CATCH_ALL_PROBE_LOCAL


def test_catch_all_probe_local_part_obvio_no_real() -> None:
    # La local-part debe ser obviamente sintetica -- no algo que un
    # gerente pueda haber elegido.
    assert "demin" in CATCH_ALL_PROBE_LOCAL or "probe" in CATCH_ALL_PROBE_LOCAL
    assert len(CATCH_ALL_PROBE_LOCAL) >= 10


# ─── research_t4_nowebsite prompt parse ────────────────────────────────────


def test_research_t4_nowebsite_prompt_parses() -> None:
    """El modulo debe poder cargar y partir el prompt en system + user."""
    from pipeline import research_t4_nowebsite as mod
    assert mod._SYSTEM, "system vacio"
    assert mod._USER_TEMPLATE, "user template vacio"
    assert "{nombre}" in mod._USER_TEMPLATE
    assert "{nif}" in mod._USER_TEMPLATE
    assert "{localidad}" in mod._USER_TEMPLATE
    assert "{descripcion}" in mod._USER_TEMPLATE


def test_research_t4_nowebsite_system_forbids_inventions() -> None:
    """Apendice A regla 3: cero invenciones."""
    from pipeline import research_t4_nowebsite as mod
    sys_lower = mod._SYSTEM.lower()
    assert "no inventes" in sys_lower or "cero invenciones" in sys_lower


def test_research_t4_nowebsite_system_lists_subsectores() -> None:
    """El prompt debe limitar sub_sector a un enum cerrado."""
    from pipeline import research_t4_nowebsite as mod
    for cat in (
        "constructora_obra_nueva", "reformas", "promotora",
        "arquitectura_ejecuta", "demolicion", "instalaciones",
        "gestion_patrimonio", "otro",
    ):
        assert cat in mod._SYSTEM, f"sub_sector {cat!r} ausente del prompt"
