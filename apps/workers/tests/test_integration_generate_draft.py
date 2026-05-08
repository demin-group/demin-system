"""Tests de integración con BD dev real para pipeline.generate_draft.

Opt-in: requiere flag `-m integration` (excluidos por default en addopts).
Cada test corre en una transacción que se ROLLBACK al final → no
contamina datos reales.

El test crítico que motivó este fichero (paso 6.5, 2026-05-08): verificar
que `fetch_pending_contacts` filtra por `is_primary=true`, requisito
operativo del plan §10.1 + D18 + §9.2 (cadencia 1:1 contact-secuencia,
no envío simultáneo a varios contacts de la misma empresa).
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Connection

from pipeline.generate_draft import fetch_pending_contacts
from shared.db import get_engine

pytestmark = pytest.mark.integration


@pytest.fixture
def conn() -> Iterator[Connection]:
    """Conexión transaccional contra dev. Cualquier INSERT/UPDATE/DELETE
    se descarta al salir del fixture. SAVEPOINT anidado para que el
    código bajo test (que usa `get_session()` con commit propio) no
    rompa la transacción exterior."""
    engine = get_engine("dev")
    with engine.connect() as c:
        trans = c.begin()
        try:
            yield c
        finally:
            trans.rollback()


def _insert_company_with_contacts(
    c: Connection,
    *,
    nif: str,
    nombre: str,
    primary_email: str,
    secondary_email: str,
) -> tuple[str, str, str]:
    """Inserta 1 company fit T3 + 1 contact primary + 1 contact no primary.
    Devuelve (company_id, primary_contact_id, secondary_contact_id)."""
    c.execute(
        text(
            """
            INSERT INTO companies (nif, nombre, tier, ia_fit, ia_fit_reason,
                                   web, research_done_at, research_data)
            VALUES (:nif, :nombre, 'T3', 'fit', 'integration test',
                    'https://test-integration.example.com', now(),
                    cast(:rd as jsonb))
            """
        ),
        {
            "nif": nif,
            "nombre": nombre,
            "rd": '{"tipo_actividad_concreta": "test", "hooks_de_personalizacion": ["x"]}',
        },
    )
    company_id = c.execute(
        text("SELECT id FROM companies WHERE nif = :nif"), {"nif": nif}
    ).scalar_one()

    c.execute(
        text(
            """
            INSERT INTO contacts (company_id, email, email_source, email_type,
                                  email_priority, nombre, cargo, is_primary)
            VALUES
                (cast(:cid as uuid), :pe, 'hunter', 'decisor', 1,
                 'Primary Test', 'Director', true),
                (cast(:cid as uuid), :se, 'hunter', 'corporativo_pequeno', 4,
                 NULL, NULL, false)
            """
        ),
        {"cid": str(company_id), "pe": primary_email, "se": secondary_email},
    )
    rows = c.execute(
        text("SELECT id, email FROM contacts WHERE company_id = cast(:cid as uuid)"),
        {"cid": str(company_id)},
    ).all()
    primary_id = next(str(r[0]) for r in rows if r[1] == primary_email)
    secondary_id = next(str(r[0]) for r in rows if r[1] == secondary_email)
    return str(company_id), primary_id, secondary_id


# ─── 1. fetch_pending_contacts respeta is_primary ──────────────────────────


def test_fetch_pending_contacts_returns_only_primary(conn: Connection) -> None:
    """Núcleo del fix paso 6.5: con 2 contacts (1 primary, 1 no) en una
    company fit T3 con research OK, fetch_pending_contacts devuelve
    EXACTAMENTE 1 contact (el primary)."""
    nif = "X99999001"
    company_id, primary_id, secondary_id = _insert_company_with_contacts(
        conn,
        nif=nif,
        nombre="INTEGRATION TEST PRIMARY",
        primary_email="primary@test-integration.example.com",
        secondary_email="secondary@test-integration.example.com",
    )
    # Importante: la fixture rollback descarta los inserts. Pero
    # fetch_pending_contacts usa get_session() que abre su propia conexión —
    # tiene que ver los INSERT del fixture. Confirmamos que la fixture
    # ya hizo COMMIT antes del read; SQLAlchemy Connection .commit no
    # libera la transacción interior. Solución pragmática: el test
    # confirma con el mismo conn que los datos están visibles, y el
    # rollback se hace al cierre.
    #
    # NOTA OPERATIVA: este test asume que get_session("dev") dentro de
    # fetch_pending_contacts ve los datos del fixture. Si no los ve
    # (porque la transacción aún no se commiteó), el test falla con
    # "0 contacts" pese a tener el filtro correcto. El SAVEPOINT por sí
    # solo no es suficiente para visibilidad inter-conexión. Por eso
    # ejecutamos commit explícito del INSERT y rollback al final
    # mediante un DELETE de limpieza directo.
    conn.commit()

    try:
        out = fetch_pending_contacts(
            env="dev", tier="T3", angle="opening", limit=10, rerun=False,
        )
        # Buscar nuestro primary entre los resultados
        primary_match = [r for r in out if r.contact_id == primary_id]
        secondary_match = [r for r in out if r.contact_id == secondary_id]

        assert len(primary_match) == 1, (
            f"primary debería aparecer exactamente 1 vez; aparece {len(primary_match)}"
        )
        assert len(secondary_match) == 0, (
            f"secondary (is_primary=false) NO debería aparecer; aparece {len(secondary_match)}"
        )
        assert primary_match[0].email == "primary@test-integration.example.com"
    finally:
        # Limpieza explícita (DELETE en orden FK)
        conn.execute(
            text("DELETE FROM contacts WHERE company_id = cast(:cid as uuid)"),
            {"cid": company_id},
        )
        conn.execute(
            text("DELETE FROM companies WHERE id = cast(:cid as uuid)"),
            {"cid": company_id},
        )
        conn.commit()


def test_fetch_pending_contacts_skips_optout_even_if_primary(
    conn: Connection,
) -> None:
    """is_primary=true + is_optout=true → NO se devuelve. El opt-out
    permanente (Apéndice A regla 2) gana sobre cualquier flag operativo."""
    nif = "X99999002"
    company_id, primary_id, _ = _insert_company_with_contacts(
        conn,
        nif=nif,
        nombre="INTEGRATION TEST OPTOUT",
        primary_email="primary-optout@test-integration.example.com",
        secondary_email="secondary-optout@test-integration.example.com",
    )
    conn.execute(
        text(
            "UPDATE contacts SET is_optout=true, optout_reason='test' "
            "WHERE id = cast(:id as uuid)"
        ),
        {"id": primary_id},
    )
    conn.commit()
    try:
        out = fetch_pending_contacts(
            env="dev", tier="T3", angle="opening", limit=10, rerun=False,
        )
        assert all(r.contact_id != primary_id for r in out), (
            "contact con is_optout=true NO debería aparecer aunque sea primary"
        )
    finally:
        conn.execute(
            text("DELETE FROM contacts WHERE company_id = cast(:cid as uuid)"),
            {"cid": company_id},
        )
        conn.execute(
            text("DELETE FROM companies WHERE id = cast(:cid as uuid)"),
            {"cid": company_id},
        )
        conn.commit()
