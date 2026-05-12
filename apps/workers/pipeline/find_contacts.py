"""find_contacts.py — Sprint 4 paso 4 (D21, D22).

Itera companies con `ia_fit='fit'` del tier solicitado, llama HunterAdapter
sobre el dominio (o nombre como fallback gratis para T1/T4 sin web),
clasifica cada email devuelto con `email_policy.classify_email`, aplica el
filtro tier (`is_acceptable_for_tier`), opcionalmente enriquece nominal-sin-cargo
con `research_data.personas_extraidas` (D21), prioriza 1..4 y elige hasta 3
candidatos por empresa (D18). Inserta en `contacts` con `email_source='hunter'`,
`email_verified=false` (lo rellena `verify_emails.py`).

Idempotente: skipea companies con `contacts` existentes salvo `--reprocess`.
La cláusula `ON CONFLICT (company_id, email) DO NOTHING` cubre re-ejecuciones.

Cap defensivo de llamadas Hunter (default 20, plan Free 25/mes).

NO ejecuta `research_prospect.py` (eso es paso 4b). Cuando `personas_extraidas`
no exista para una empresa T2 (caso esperado en Sprint 4 hasta paso 4b), el
nominal-sin-cargo cae por A3 → empresa marcada con `ia_fit_reason=
'no_contactos_encontrados'`. Eso es el comportamiento de plan §8.5 paso 5.

CLI:
    cd apps/workers
    uv run python -m pipeline.find_contacts --env dev --tier T3 --limit 5
    uv run python -m pipeline.find_contacts --env prod --tier T3 --max-hunter-calls 20
    uv run python -m pipeline.find_contacts --env dev --tier T3 --reprocess
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass, replace
from typing import Any, Literal

import tldextract
from sqlalchemy import CursorResult, text

from shared.email_finder import Contact
from shared.email_policy import (
    EmailType,
    _normalize,
    classify_email,
    is_acceptable_for_tier,
)

EnvName = Literal["dev", "prod"]
Tier = Literal["T1", "T2", "T3", "T4"]

MAX_CONTACTS_PER_COMPANY = 3
"""D18: máximo 2-3 candidatos por empresa. 3 nos da margen sin spamear."""

DEFAULT_MAX_HUNTER_CALLS = 20
"""Cap defensivo. Plan Free 25/mes; dejamos 5 de margen para imprevistos."""

DECISOR_HIGH_CONFIDENCE = 80
"""Umbral confidence para distinguir priority 1 (decisor confiable) de 2."""

logger = logging.getLogger("demin.find_contacts")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


@dataclass(slots=True)
class CompanyRow:
    """Subset de `companies` que necesita el worker."""

    id: str
    nif: str
    nombre: str
    web: str | None
    tier: str
    research_data: dict[str, Any] | None


@dataclass(slots=True)
class CandidateContact:
    """Email post-clasificación + priorización, listo para insert."""

    email: str
    email_type: EmailType
    email_priority: int
    nombre: str | None
    cargo: str | None
    confidence: int | None
    classification_reason: str


# ─── Funciones puras (testables sin BD ni red) ─────────────────────────────


def resolve_domain_from_company(web: str | None) -> str | None:
    """Extrae el dominio registrable (`acme.es`) de cualquier valor en
    `companies.web` (URL completa, dominio pelado, con o sin path).

    Devuelve `None` si no se puede extraer un dominio válido (entrada vacía,
    cadena no parseable, sin sufijo conocido).
    """
    if not web or not web.strip():
        return None
    extracted = tldextract.extract(web.strip())
    if not extracted.domain or not extracted.suffix:
        return None
    return f"{extracted.domain}.{extracted.suffix}".lower()


def assign_priority(
    email_type: EmailType,
    confidence: int | None,
    position: str | None = None,
) -> int:
    """Mapping de prioridad (D18 + D20, refinado paso 6.6 con sub-bucket nominal):

        1 = decisor con confidence >= 80
        2 = decisor (confidence < 80, o sin confidence reportada)
        3 = nominal CON cargo identificado (position no vacío)
        4 = nominal SIN cargo identificado
        5 = corporativo_pequeno

    Dentro del bucket nominal, el cargo claro (Director, Manager, Engineer,
    Architect, etc. — roles que `classify_email` no eleva a decisor estricto
    pero existen como función) prevalece sobre el desempate por `confidence`
    en `select_top_candidates`. Lección 29: una persona identificada con
    función conocida es mejor primary que una persona sin función conocida
    aunque la confianza del email finder sea más alta. El campo `confidence`
    mide calidad del email (sintaxis, fuente Hunter), NO calidad del rol.

    `position` se considera "vacío" si es `None` o un string que tras `strip()`
    queda vacío. La distinción se hace tras `enrich_with_personas_extraidas`,
    que rellena `position` desde `research_data.personas_extraidas` cuando
    Hunter devolvió nombre sin cargo.

    `descartado` no debería llegar aquí — `is_acceptable_for_tier` lo filtra
    antes. Si llega, levantamos para que un fallo en el flujo sea ruidoso.
    """
    if email_type == "decisor":
        if confidence is not None and confidence >= DECISOR_HIGH_CONFIDENCE:
            return 1
        return 2
    if email_type == "nominal":
        if position is not None and position.strip():
            return 3
        return 4
    if email_type == "corporativo_pequeno":
        return 5
    raise ValueError(
        f"assign_priority no soporta email_type={email_type!r} "
        f"(descartado debería estar filtrado antes)"
    )


def select_top_candidates(
    candidates: list[CandidateContact],
    max_n: int = MAX_CONTACTS_PER_COMPANY,
) -> list[CandidateContact]:
    """Ordena por priority asc, confidence desc (None al final). Devuelve
    los primeros N. Cap D18: ≤3 candidatos por empresa."""

    def sort_key(c: CandidateContact) -> tuple[int, int]:
        # Confidence desc → invertimos para que el sort natural (asc) lo
        # ordene de mayor a menor. None va al final con 101 (>100).
        conf_inv = 101 if c.confidence is None else (100 - c.confidence)
        return (c.email_priority, conf_inv)

    return sorted(candidates, key=sort_key)[:max_n]


def enrich_with_personas_extraidas(
    contact: Contact,
    research_data: dict[str, Any] | None,
) -> Contact:
    """Si el contact tiene nombre pero NO cargo, intenta sacar el cargo de
    `research_data.personas_extraidas` (D21, §8.4).

    No-op (devuelve el contact intacto) si:
    - el contact ya tiene cargo
    - el contact no tiene nombre
    - `research_data` es None / vacío / mal formado
    - no hay match por nombre normalizado
    - el match existe pero `cargo_si_aparece` está vacío

    Estructura esperada de research_data (la rellena paso 4b):
        {"personas_extraidas": [
            {"nombre": "Juan Pérez", "cargo_si_aparece": "Director", "fuente_url": "..."}
        ]}
    """
    if contact.position:
        return contact
    if not contact.person_name:
        return contact
    if not research_data:
        return contact
    personas = research_data.get("personas_extraidas")
    if not isinstance(personas, list) or not personas:
        return contact

    target = _normalize(contact.person_name)
    if not target:
        return contact

    for p in personas:
        if not isinstance(p, dict):
            continue
        cand_name = _normalize(p.get("nombre"))
        if cand_name and cand_name == target:
            cargo = p.get("cargo_si_aparece")
            if isinstance(cargo, str) and cargo.strip():
                return replace(contact, position=cargo.strip())
    return contact


def classify_and_filter(
    raw_contacts: list[Contact],
    company: CompanyRow,
) -> list[CandidateContact]:
    """De los contacts crudos del adapter al subset aceptable + priorizado.

    Pipeline interno (sin BD, sin red — todo en memoria):
        1. Enriquece cada contact con personas_extraidas (no-op si no aplica).
        2. Clasifica con `email_policy.classify_email(tier)`.
        3. Filtra con `is_acceptable_for_tier`.
        4. Asigna priority.

    No trunca — eso lo hace `select_top_candidates` después.
    """
    out: list[CandidateContact] = []
    for raw in raw_contacts:
        if not raw.email or "@" not in raw.email:
            logger.debug("descarto contact sin email válido: %r", raw)
            continue
        enriched = enrich_with_personas_extraidas(raw, company.research_data)
        cls = classify_email(
            email=enriched.email,
            position=enriched.position,
            person_name=enriched.person_name,
            tier=company.tier,
        )
        if not is_acceptable_for_tier(cls.email_type, company.tier):
            logger.debug(
                "filtrado por tier nif=%s email=%s type=%s reason=%s",
                company.nif, enriched.email, cls.email_type, cls.reason,
            )
            continue
        priority = assign_priority(
            cls.email_type, enriched.confidence, enriched.position
        )
        out.append(
            CandidateContact(
                email=enriched.email.strip().lower(),
                email_type=cls.email_type,
                email_priority=priority,
                nombre=enriched.person_name,
                cargo=enriched.position,
                confidence=enriched.confidence,
                classification_reason=cls.reason,
            )
        )
    return out


# ─── Orquestación por empresa (red, sin BD) ────────────────────────────────


def process_company(
    company: CompanyRow,
    hunter: Any,  # `EmailFinder` runtime; tipo Any para no atar el tipo en tests
) -> tuple[list[CandidateContact], int]:
    """Procesa una empresa: resuelve dominio → llama Hunter → clasifica → top N.

    Devuelve `(candidatos elegidos, llamadas Hunter consumidas)`.

    Reglas:
        - Con dominio: `find_contacts_by_domain` (1 llamada).
        - Sin dominio + tier ∈ {T1,T4}: fallback `find_contacts_by_company`
          (1 llamada, fuzzy — Frente C dio 0% pero coste 0).
        - Sin dominio + tier ∈ {T2,T3}: skip silencioso (0 llamadas). T2/T3
          sin web son raros y quemar Hunter ahí no es rentable.
    """
    domain = resolve_domain_from_company(company.web)
    raw: list[Contact] = []
    calls = 0

    if domain:
        raw = hunter.find_contacts_by_domain(domain, company.nombre)
        calls = 1
    elif company.tier in ("T1", "T4"):
        raw = hunter.find_contacts_by_company(company.nombre, "")
        calls = 1
    else:
        return [], 0

    classified = classify_and_filter(raw, company)
    selected = select_top_candidates(classified, MAX_CONTACTS_PER_COMPANY)
    return selected, calls


# ─── Acceso a BD ───────────────────────────────────────────────────────────


def fetch_pending(
    env: EnvName, tier: Tier, limit: int | None, reprocess: bool
) -> list[CompanyRow]:
    """Trae companies con `ia_fit='fit'` del tier solicitado, orden estable
    por NIF. Si `reprocess=False` (default), excluye las que ya tengan al
    menos un contact (idempotencia)."""
    from shared.db import get_session  # noqa: PLC0415

    sql = """
        SELECT c.id, c.nif, c.nombre, c.web, c.tier, c.research_data
        FROM companies c
        WHERE c.ia_fit = 'fit'
          AND c.tier = :tier
    """
    if not reprocess:
        sql += " AND NOT EXISTS (SELECT 1 FROM contacts WHERE company_id = c.id)"
    sql += " ORDER BY c.nif"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    with get_session(env) as s:
        rows = s.execute(text(sql), {"tier": tier}).all()

    return [
        CompanyRow(
            id=str(r[0]),
            nif=r[1],
            nombre=r[2],
            web=r[3],
            tier=r[4],
            research_data=r[5],
        )
        for r in rows
    ]


_INSERT_CONTACT_SQL = text(
    """
    INSERT INTO contacts
        (company_id, email, email_verified, email_source,
         email_type, email_priority, nombre, cargo, is_primary)
    VALUES
        (:company_id, :email, false, 'hunter',
         :email_type, :email_priority, :nombre, :cargo, :is_primary)
    ON CONFLICT (company_id, email) DO NOTHING
    """
)


def insert_contacts(
    env: EnvName, company: CompanyRow, candidates: list[CandidateContact]
) -> int:
    """Inserta cada candidato (uno por uno para poder contar inserts reales
    via rowcount; máx 3 por empresa, perf no es problema). Devuelve nº de
    filas efectivamente insertadas (las que chocaron con el unique se descartan
    silenciosamente)."""
    from shared.db import get_session  # noqa: PLC0415

    if not candidates:
        return 0

    inserted = 0
    with get_session(env) as s:
        for i, c in enumerate(candidates):
            # En runtime `Session.execute` con DML devuelve `CursorResult` (que
            # expone `rowcount`); el type hint genérico es `Result[Any]`. Cast
            # explícito para satisfacer mypy --strict sin oscurecer la lectura.
            res: CursorResult[Any] = s.execute(  # type: ignore[assignment]
                _INSERT_CONTACT_SQL,
                {
                    "company_id": company.id,
                    "email": c.email,
                    "email_type": c.email_type,
                    "email_priority": c.email_priority,
                    "nombre": c.nombre,
                    "cargo": c.cargo,
                    "is_primary": i == 0,
                },
            )
            inserted += res.rowcount or 0
    return inserted


_UPDATE_NO_CONTACTS_SQL = text(
    "UPDATE companies SET ia_fit_reason = :reason WHERE id = :id"
)


def mark_no_contacts(
    env: EnvName, company: CompanyRow, reason: str = "no_contactos_encontrados"
) -> None:
    """Marca la empresa con `ia_fit_reason='no_contactos_encontrados'` para
    que paso 6/7 la salte. NO toca `ia_fit` (sigue siendo 'fit' por
    descripción; el problema es la cobertura del email finder)."""
    from shared.db import get_session  # noqa: PLC0415

    with get_session(env) as s:
        s.execute(_UPDATE_NO_CONTACTS_SQL, {"id": company.id, "reason": reason})


# ─── CLI ───────────────────────────────────────────────────────────────────


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="find_contacts — busca emails via Hunter sobre companies fit del tier solicitado"
    )
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument(
        "--tier",
        choices=("T1", "T2", "T3", "T4"),
        required=True,
        help="Tier a procesar. D22 ordena T3 → T2 → resto en Sprint 4.",
    )
    p.add_argument("--limit", type=int, default=None,
                   help="Procesar solo las primeras N empresas (orden por NIF). Útil para smoke.")
    p.add_argument("--max-hunter-calls", type=int, default=DEFAULT_MAX_HUNTER_CALLS,
                   help=f"Cap de llamadas Hunter (default {DEFAULT_MAX_HUNTER_CALLS}, plan Free 25/mes).")
    p.add_argument("--reprocess", action="store_true",
                   help="Ignora el filtro 'sin contacts'. Re-procesa empresas ya pobladas.")
    args = p.parse_args(argv)
    env: EnvName = args.env
    tier: Tier = args.tier

    print("=" * 76)
    print(
        f"find_contacts  env={env}  tier={tier}  limit={args.limit}  "
        f"max_hunter_calls={args.max_hunter_calls}  reprocess={args.reprocess}"
    )
    print("=" * 76)

    pending = fetch_pending(env, tier, args.limit, args.reprocess)
    if not pending:
        print("No hay empresas pendientes (ia_fit='fit' + tier sin contacts). Nada que hacer.")
        return 0
    print(f"[fetch] {len(pending)} empresas a procesar")

    counts = {"decisor": 0, "nominal": 0, "corporativo_pequeno": 0}
    hunter_calls = 0
    inserted = 0
    no_contacts = 0
    skipped_no_domain = 0
    errors = 0
    aborted_cap = False

    t0 = time.monotonic()

    # Lazy import — la creación del adapter lee HUNTER_API_KEY de settings,
    # que ya está validado en config.py. Si la key falta, falla aquí ruidoso.
    from shared.hunter_adapter import HunterAdapter  # noqa: PLC0415

    with HunterAdapter() as hunter:
        for i, company in enumerate(pending, 1):
            if hunter_calls >= args.max_hunter_calls:
                aborted_cap = True
                print(
                    f"  [cap] hunter_calls={hunter_calls} >= "
                    f"max_hunter_calls={args.max_hunter_calls}, parando"
                )
                break

            try:
                selected, calls = process_company(company, hunter)
            except Exception as e:
                errors += 1
                logger.exception(
                    "error procesando nif=%s nombre=%s: %s",
                    company.nif, company.nombre, e,
                )
                continue

            hunter_calls += calls

            if selected:
                n = insert_contacts(env, company, selected)
                inserted += n
                for c in selected:
                    counts[c.email_type] += 1
            else:
                if calls == 0:
                    skipped_no_domain += 1
                else:
                    no_contacts += 1
                    mark_no_contacts(env, company)

            if i % 5 == 0 or i == len(pending):
                print(
                    f"  [{i:>3}/{len(pending)}]  "
                    f"hunter_calls={hunter_calls:>2}  "
                    f"insertados={inserted:>3}  "
                    f"sin_contactos={no_contacts:>2}  "
                    f"skip_no_dom={skipped_no_domain:>2}  errs={errors}"
                )

    elapsed = time.monotonic() - t0

    print()
    print("=" * 76)
    print(f"FIN find_contacts  env={env}  tier={tier}  elapsed={elapsed:.1f}s")
    print(f"  empresas procesadas: {min(len(pending), i)} / {len(pending)}")
    print(f"  hunter_calls: {hunter_calls} (cap {args.max_hunter_calls})")
    print(f"  contacts insertados: {inserted}")
    print(f"    decisor:             {counts['decisor']}")
    print(f"    nominal:             {counts['nominal']}")
    print(f"    corporativo_pequeno: {counts['corporativo_pequeno']}")
    print(f"  empresas sin contactos aceptables: {no_contacts} ({_pct(no_contacts, len(pending))})")
    print(f"  empresas skip por sin_dominio:     {skipped_no_domain}")
    print(f"  errores: {errors}")
    print("=" * 76)

    if aborted_cap:
        return 2
    if errors > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
