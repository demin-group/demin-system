"""Tests de pipeline.find_contacts.

Sin red real: usa `unittest.mock.MagicMock` como adapter. Sin BD: las
funciones que tocan la base (`fetch_pending`, `insert_contacts`,
`mark_no_contacts`) NO se testean unitariamente — quedan cubiertas por el
smoke real en dev (Sprint 4 paso 4 cierre).

Cubrimos:
- Funciones puras: resolve_domain_from_company, assign_priority,
  select_top_candidates, enrich_with_personas_extraidas, classify_and_filter
- Orquestación por empresa: process_company con HunterAdapter mockeado
"""
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from pipeline.find_contacts import (
    DECISOR_HIGH_CONFIDENCE,
    MAX_CONTACTS_PER_COMPANY,
    CandidateContact,
    CompanyRow,
    assign_priority,
    classify_and_filter,
    enrich_with_personas_extraidas,
    process_company,
    resolve_domain_from_company,
    select_top_candidates,
)
from shared.email_finder import Contact

# ─── Helpers ───────────────────────────────────────────────────────────────


def _company(
    *,
    tier: str = "T3",
    web: str | None = "https://acme.es",
    research_data: dict[str, Any] | None = None,
) -> CompanyRow:
    return CompanyRow(
        id="11111111-1111-1111-1111-111111111111",
        nif="A12345678",
        nombre="ACME SL",
        web=web,
        tier=tier,
        research_data=research_data,
    )


def _contact(
    email: str,
    *,
    position: str | None = None,
    person_name: str | None = None,
    confidence: int | None = None,
) -> Contact:
    return Contact(
        email=email,
        position=position,
        person_name=person_name,
        confidence=confidence,
        source="hunter",
    )


# ─── 1. resolve_domain_from_company ────────────────────────────────────────


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://www.acme.es", "acme.es"),
        ("https://acme.es/contacto", "acme.es"),
        ("acme.es", "acme.es"),
        ("www.acme.es", "acme.es"),
        ("http://ACME.es", "acme.es"),
        ("https://www.acme.co.uk", "acme.co.uk"),
        ("acme.es/quienes-somos", "acme.es"),
        ("  https://acme.es  ", "acme.es"),
    ],
)
def test_resolve_domain_extracts_registrable_domain(raw: str, expected: str) -> None:
    assert resolve_domain_from_company(raw) == expected


@pytest.mark.parametrize("raw", ["", "   ", None])
def test_resolve_domain_returns_none_for_empty(raw: str | None) -> None:
    assert resolve_domain_from_company(raw) is None


@pytest.mark.parametrize("raw", ["garbage", "no-suffix-here", "..."])
def test_resolve_domain_returns_none_for_unparseable(raw: str) -> None:
    assert resolve_domain_from_company(raw) is None


# ─── 2. assign_priority ────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "email_type,confidence,position,expected",
    [
        # Decisor: confidence threshold, ignora position (siempre es alto rango).
        ("decisor", 95, "CEO", 1),
        ("decisor", 80, "Director", 1),  # frontera inclusiva
        ("decisor", 79, "Director", 2),
        ("decisor", 0, "Gerente", 2),
        ("decisor", None, "Gerente", 2),
        ("decisor", 95, None, 1),  # position no afecta a decisor
        # Nominal: el cargo (position no vacío tras strip) decide bucket 3 vs 4.
        # Paso 6.6: distinción explícita.
        ("nominal", 90, "Project Manager", 3),  # con cargo
        ("nominal", 0, "Engineer", 3),         # con cargo bajo confidence sigue 3
        ("nominal", None, "Architect", 3),     # con cargo sin confidence sigue 3
        ("nominal", 95, None, 4),              # SIN cargo (None)
        ("nominal", 95, "", 4),                # SIN cargo (string vacío)
        ("nominal", 95, "   ", 4),             # SIN cargo (solo espacios)
        ("nominal", None, None, 4),
        # Corporativo_pequeno: bucket 5 (era 4 hasta paso 6.5; paso 6.6 lo
        # desplaza para abrir hueco al sub-bucket nominal-sin-cargo en 4).
        ("corporativo_pequeno", 95, None, 5),
        ("corporativo_pequeno", None, None, 5),
    ],
)
def test_assign_priority_table(
    email_type: str, confidence: int | None, position: str | None, expected: int
) -> None:
    assert (
        assign_priority(email_type, confidence, position)  # type: ignore[arg-type]
        == expected
    )


def test_assign_priority_nominal_con_cargo_gana_a_sin_cargo() -> None:
    """Caso operativo de LENA (paso 6.6): jaime nominal-con-cargo
    'Business Development Director' debe quedar priority=3, zaragoza
    nominal-sin-cargo priority=4 — independientemente de confidence Hunter."""
    jaime = assign_priority("nominal", 60, "Business Development Director")
    zaragoza = assign_priority("nominal", 95, None)
    assert jaime == 3
    assert zaragoza == 4
    assert jaime < zaragoza, "con-cargo debe preceder a sin-cargo en sort"


def test_assign_priority_rejects_descartado() -> None:
    """Descartado no debería llegar a priority — fail loud si pasa."""
    with pytest.raises(ValueError, match="descartado"):
        assign_priority("descartado", 50)  # type: ignore[arg-type]


def test_decisor_high_confidence_threshold_is_80() -> None:
    """Documenta el umbral: si se baja, este test fuerza revisarlo."""
    assert DECISOR_HIGH_CONFIDENCE == 80


# ─── 3. select_top_candidates ──────────────────────────────────────────────


def _cand(
    email: str, *, priority: int, confidence: int | None = None,
    email_type: str = "decisor",
) -> CandidateContact:
    return CandidateContact(
        email=email,
        email_type=email_type,  # type: ignore[arg-type]
        email_priority=priority,
        nombre=None,
        cargo=None,
        confidence=confidence,
        classification_reason="test",
    )


def test_select_top_orders_by_priority_then_confidence() -> None:
    candidates = [
        _cand("c@x.es", priority=2, confidence=70),
        _cand("a@x.es", priority=1, confidence=90),
        _cand("d@x.es", priority=2, confidence=85),
        _cand("b@x.es", priority=1, confidence=75),
    ]
    out = select_top_candidates(candidates, max_n=4)
    assert [c.email for c in out] == ["a@x.es", "b@x.es", "d@x.es", "c@x.es"]


def test_select_top_truncates_to_max_n() -> None:
    candidates = [_cand(f"c{i}@x.es", priority=1, confidence=90 - i) for i in range(5)]
    out = select_top_candidates(candidates, max_n=3)
    assert len(out) == 3
    assert [c.email for c in out] == ["c0@x.es", "c1@x.es", "c2@x.es"]


def test_select_top_default_max_is_d18() -> None:
    candidates = [_cand(f"c{i}@x.es", priority=1, confidence=90) for i in range(5)]
    out = select_top_candidates(candidates)
    assert len(out) == MAX_CONTACTS_PER_COMPANY == 3


def test_select_top_handles_none_confidence_last() -> None:
    candidates = [
        _cand("none@x.es", priority=1, confidence=None),
        _cand("low@x.es", priority=1, confidence=10),
    ]
    out = select_top_candidates(candidates, max_n=2)
    assert [c.email for c in out] == ["low@x.es", "none@x.es"]


def test_select_top_empty_input_returns_empty() -> None:
    assert select_top_candidates([], max_n=3) == []


def test_select_top_nominal_con_cargo_gana_a_nominal_sin_cargo_alto_conf() -> None:
    """Regresión paso 6.6: en LENA, jaime (nominal-con-cargo 'Business Development
    Director', conf 60 por hipótesis) debe quedar primary antes que zaragoza
    (nominal-sin-cargo, conf 95). El sort `(priority asc, confidence desc)`
    enterraba esta distinción cuando ambos caían en priority=3; tras 6.6
    jaime cae en bucket 3 y zaragoza en bucket 4 → orden correcto sin depender
    del confidence."""
    jaime = _cand("jaime@nozar.es", priority=3, confidence=60, email_type="nominal")
    zaragoza = _cand("zaragoza@nozar.es", priority=4, confidence=95, email_type="nominal")
    info = _cand("info@nozar.es", priority=5, confidence=70, email_type="corporativo_pequeno")
    out = select_top_candidates([info, zaragoza, jaime], max_n=3)
    assert [c.email for c in out] == [
        "jaime@nozar.es",
        "zaragoza@nozar.es",
        "info@nozar.es",
    ]


# ─── 4. enrich_with_personas_extraidas ─────────────────────────────────────


def test_enrich_noop_when_contact_already_has_position() -> None:
    contact = _contact("juan@x.es", person_name="Juan Pérez", position="Director")
    research = {"personas_extraidas": [{"nombre": "Juan Pérez", "cargo_si_aparece": "CEO"}]}
    assert enrich_with_personas_extraidas(contact, research) is contact


def test_enrich_noop_when_contact_has_no_name() -> None:
    contact = _contact("info@x.es", person_name=None)
    research = {"personas_extraidas": [{"nombre": "Juan Pérez", "cargo_si_aparece": "CEO"}]}
    assert enrich_with_personas_extraidas(contact, research) is contact


def test_enrich_noop_when_research_data_is_none() -> None:
    contact = _contact("juan@x.es", person_name="Juan Pérez")
    assert enrich_with_personas_extraidas(contact, None) is contact


def test_enrich_noop_when_personas_key_missing() -> None:
    contact = _contact("juan@x.es", person_name="Juan Pérez")
    assert enrich_with_personas_extraidas(contact, {"otra_clave": "x"}) is contact


def test_enrich_noop_when_personas_list_empty() -> None:
    contact = _contact("juan@x.es", person_name="Juan Pérez")
    assert enrich_with_personas_extraidas(contact, {"personas_extraidas": []}) is contact


def test_enrich_match_exact_returns_contact_with_position() -> None:
    contact = _contact("juan@x.es", person_name="Juan Pérez")
    research = {
        "personas_extraidas": [
            {"nombre": "Juan Pérez", "cargo_si_aparece": "Director Técnico"}
        ]
    }
    out = enrich_with_personas_extraidas(contact, research)
    assert out.position == "Director Técnico"
    assert out.email == "juan@x.es"
    assert out.person_name == "Juan Pérez"


def test_enrich_match_normalizes_accents_and_case() -> None:
    """`Juan Perez` (sin acento, en email) debe matchear `Juán Pérez` en research."""
    contact = _contact("juan@x.es", person_name="Juan Perez")
    research = {
        "personas_extraidas": [
            {"nombre": "Juán PÉREZ", "cargo_si_aparece": "Gerente"}
        ]
    }
    out = enrich_with_personas_extraidas(contact, research)
    assert out.position == "Gerente"


def test_enrich_no_match_returns_contact_unchanged() -> None:
    contact = _contact("juan@x.es", person_name="Juan Pérez")
    research = {
        "personas_extraidas": [
            {"nombre": "María González", "cargo_si_aparece": "CEO"}
        ]
    }
    out = enrich_with_personas_extraidas(contact, research)
    assert out is contact


def test_enrich_match_but_empty_cargo_no_change() -> None:
    contact = _contact("juan@x.es", person_name="Juan Pérez")
    research = {
        "personas_extraidas": [
            {"nombre": "Juan Pérez", "cargo_si_aparece": ""}
        ]
    }
    out = enrich_with_personas_extraidas(contact, research)
    assert out.position is None


def test_enrich_skips_malformed_persona_entries() -> None:
    contact = _contact("juan@x.es", person_name="Juan Pérez")
    research = {
        "personas_extraidas": [
            "no-es-dict",
            {"nombre": None, "cargo_si_aparece": "X"},
            {"nombre": "Juan Pérez", "cargo_si_aparece": "Gerente"},
        ]
    }
    out = enrich_with_personas_extraidas(contact, research)
    assert out.position == "Gerente"


# ─── 5. classify_and_filter ────────────────────────────────────────────────


def test_classify_and_filter_t3_accepts_decisor_corporativo_and_nominal() -> None:
    company = _company(tier="T3")
    raw = [
        _contact("juan@acme.es", position="Director General", person_name="Juan", confidence=92),
        _contact("info@acme.es", confidence=70),
        _contact("maria@acme.es", position="Project Manager", person_name="María", confidence=80),
        _contact("pedro@acme.es", person_name="Pedro Sin Cargo", confidence=85),
    ]
    out = classify_and_filter(raw, company)
    types = {c.email_type for c in out}
    assert types == {"decisor", "corporativo_pequeno", "nominal"}
    # Paso 6.6: prio 1 decisor, 3 nominal-con-cargo, 4 nominal-sin-cargo, 5 corporativo.
    by_email = {c.email: c for c in out}
    assert by_email["juan@acme.es"].email_priority == 1
    assert by_email["maria@acme.es"].email_priority == 3
    assert by_email["pedro@acme.es"].email_priority == 4
    assert by_email["info@acme.es"].email_priority == 5


def test_classify_and_filter_t2_blocks_corporativo_pequeno() -> None:
    company = _company(tier="T2")
    raw = [
        _contact("info@x.es", confidence=70),  # corporativo → blocked en T2
        _contact("ana@x.es", position="CEO", person_name="Ana", confidence=88),
    ]
    out = classify_and_filter(raw, company)
    assert {c.email for c in out} == {"ana@x.es"}


def test_classify_and_filter_t2_blocks_nominal_sin_cargo_via_a3() -> None:
    """T2 sin personas_extraidas: nominal-sin-cargo cae por A3 → descartado."""
    company = _company(tier="T2", research_data=None)
    raw = [
        _contact("juan@x.es", person_name="Juan Pérez"),  # A3 en T2 → descartado
    ]
    out = classify_and_filter(raw, company)
    assert out == []


def test_classify_and_filter_t2_with_personas_extraidas_recovers_nominal() -> None:
    """T2 con cruce: nombre-sin-cargo + research enriquece con cargo no-decisor
    → reclasifica a nominal-con-cargo (en vez de caer por A3 a descartado)."""
    company = _company(
        tier="T2",
        research_data={
            "personas_extraidas": [
                {"nombre": "Juan Pérez", "cargo_si_aparece": "Coordinador de Proyectos"}
            ]
        },
    )
    raw = [_contact("juan@x.es", person_name="Juan Pérez", confidence=85)]
    out = classify_and_filter(raw, company)
    assert len(out) == 1
    assert out[0].email_type == "nominal"
    assert out[0].cargo == "Coordinador de Proyectos"
    assert out[0].email_priority == 3


def test_classify_and_filter_t2_with_personas_extraidas_can_promote_to_decisor() -> None:
    """T2 con cruce: si el cargo enriquecido es decisor estricto, sube a decisor."""
    company = _company(
        tier="T2",
        research_data={
            "personas_extraidas": [
                {"nombre": "Juan Pérez", "cargo_si_aparece": "Director Técnico"}
            ]
        },
    )
    raw = [_contact("juan@x.es", person_name="Juan Pérez", confidence=85)]
    out = classify_and_filter(raw, company)
    assert len(out) == 1
    assert out[0].email_type == "decisor"
    assert out[0].cargo == "Director Técnico"
    # confidence 85 ≥ 80 → priority 1
    assert out[0].email_priority == 1


def test_classify_and_filter_t1_accepts_a3_nominal_sin_cargo() -> None:
    """T1 acepta nombre-sin-cargo como nominal (regla A3 §8.5).
    Paso 6.6: ahora priority=4 (era 3 hasta 6.5)."""
    company = _company(tier="T1", web="x.es")
    raw = [_contact("juan@x.es", person_name="Juan Pérez")]
    out = classify_and_filter(raw, company)
    assert len(out) == 1
    assert out[0].email_type == "nominal"
    assert out[0].email_priority == 4


def test_classify_and_filter_descarta_negativos() -> None:
    company = _company(tier="T3")
    raw = [
        _contact("noreply@x.es"),
        _contact("rrhh@x.es"),
        _contact("marketing@x.es", position="Marketing Director"),
        _contact("juan@x.es", position="CEO", person_name="Juan", confidence=90),
    ]
    out = classify_and_filter(raw, company)
    assert {c.email for c in out} == {"juan@x.es"}


def test_classify_and_filter_lowercases_email() -> None:
    company = _company(tier="T3")
    raw = [_contact("CEO@AcMe.Es", position="CEO", confidence=90)]
    out = classify_and_filter(raw, company)
    assert out[0].email == "ceo@acme.es"


def test_classify_and_filter_skips_invalid_email() -> None:
    company = _company(tier="T3")
    raw = [
        _contact("", position="CEO"),
        _contact("not-an-email", position="CEO"),
        _contact("good@x.es", position="CEO", confidence=90),
    ]
    out = classify_and_filter(raw, company)
    assert [c.email for c in out] == ["good@x.es"]


def test_classify_and_filter_empty_input() -> None:
    company = _company(tier="T3")
    assert classify_and_filter([], company) == []


# ─── 6. process_company (HunterAdapter mockeado) ───────────────────────────


def test_process_company_with_domain_calls_find_by_domain() -> None:
    company = _company(tier="T3", web="https://acme.es")
    hunter = MagicMock()
    hunter.find_contacts_by_domain.return_value = [
        _contact("juan@acme.es", position="CEO", confidence=92),
    ]
    selected, calls = process_company(company, hunter)
    hunter.find_contacts_by_domain.assert_called_once_with("acme.es", "ACME SL")
    hunter.find_contacts_by_company.assert_not_called()
    assert calls == 1
    assert len(selected) == 1
    assert selected[0].email == "juan@acme.es"


def test_process_company_t1_no_web_falls_back_to_company_search() -> None:
    company = _company(tier="T1", web=None)
    hunter = MagicMock()
    hunter.find_contacts_by_company.return_value = [
        _contact("info@somewhere.es"),
    ]
    selected, calls = process_company(company, hunter)
    hunter.find_contacts_by_domain.assert_not_called()
    hunter.find_contacts_by_company.assert_called_once_with("ACME SL", "")
    assert calls == 1
    # T1 acepta corporativo_pequeno
    assert len(selected) == 1
    assert selected[0].email_type == "corporativo_pequeno"


def test_process_company_t4_no_web_falls_back_to_company_search() -> None:
    company = _company(tier="T4", web=None)
    hunter = MagicMock()
    hunter.find_contacts_by_company.return_value = []
    _, calls = process_company(company, hunter)
    hunter.find_contacts_by_company.assert_called_once_with("ACME SL", "")
    assert calls == 1


def test_process_company_t2_no_web_skips_silently() -> None:
    company = _company(tier="T2", web=None)
    hunter = MagicMock()
    selected, calls = process_company(company, hunter)
    hunter.find_contacts_by_domain.assert_not_called()
    hunter.find_contacts_by_company.assert_not_called()
    assert calls == 0
    assert selected == []


def test_process_company_t3_no_web_skips_silently() -> None:
    company = _company(tier="T3", web=None)
    hunter = MagicMock()
    selected, calls = process_company(company, hunter)
    hunter.find_contacts_by_domain.assert_not_called()
    hunter.find_contacts_by_company.assert_not_called()
    assert calls == 0
    assert selected == []


def test_process_company_truncates_to_max_3() -> None:
    company = _company(tier="T3", web="acme.es")
    hunter = MagicMock()
    hunter.find_contacts_by_domain.return_value = [
        _contact(f"dec{i}@acme.es", position="CEO", confidence=90 - i)
        for i in range(5)
    ]
    selected, _ = process_company(company, hunter)
    assert len(selected) == 3
    # Mejor confidence primero
    assert [c.email for c in selected] == ["dec0@acme.es", "dec1@acme.es", "dec2@acme.es"]


def test_process_company_all_filtered_returns_empty_but_calls_hunter_once() -> None:
    """Empresa T3 con web pero todos los emails filtrados (rrhh, noreply, etc.).
    Hunter se llamó (calls=1) → la empresa se marca como sin contactos."""
    company = _company(tier="T3", web="acme.es")
    hunter = MagicMock()
    hunter.find_contacts_by_domain.return_value = [
        _contact("noreply@acme.es"),
        _contact("rrhh@acme.es", position="HR"),
    ]
    selected, calls = process_company(company, hunter)
    assert calls == 1
    assert selected == []
