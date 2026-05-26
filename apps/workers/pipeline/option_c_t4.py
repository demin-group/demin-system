"""option_c_t4.py -- orquestador Opcion C para empresas T4 sin web.

Combina los 4 sub-modulos:
1. infer_domain (heuristica slug+TLD con MX check).
2. research_t4_nowebsite (LLM Sonnet).
3. permute_emails (whitelist 5 prefijos).
4. smtp_probe (catch-all detection + RCPT TO).

Persiste resultados en BD:
- Si NO se infiere dominio: companies.tier='descartado' +
  research_data._descartado_reason='no_domain_inferred'.
- Si dominio inferido: companies.research_data + research_done_at=now().
- Si catch-all detectado: research_data._smtp_status='catch_all_skipped'.
- Si email verificado: INSERT contact con email_source='option_c_t4'.

CLI:
    cd apps/workers
    PYTHONPATH=. python -m pipeline.option_c_t4 --env prod --limit 5
    PYTHONPATH=. python -m pipeline.option_c_t4 --env prod --max-cost-usd 3.0
    PYTHONPATH=. python -m pipeline.option_c_t4 --env prod --dry-run

Exit codes:
- 0: OK
- 2: error config / BD
- 3: cap presupuestario alcanzado (paro defensivo)
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import text

from pipeline.infer_domain import infer_domain
from pipeline.permute_emails import catch_all_probe, permute_emails
from pipeline.research_t4_nowebsite import research_company_nowebsite
from pipeline.smtp_probe import EmailStatus, is_catch_all, probe_email
from shared.db import get_session

EnvName = Literal["dev", "prod"]

logger = logging.getLogger("demin.option_c_t4")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

# Rate limit entre dominios DISTINTOS (mismo dominio no se prueba
# multiple veces simultaneo).
SLEEP_BETWEEN_DOMAINS_S = 3.0


@dataclass(slots=True)
class CompanyRow:
    id: str
    nif: str
    nombre: str
    localidad: str
    descripcion: str
    web: str | None
    rev_y0_keur: float | None
    rev_y1_keur: float | None
    rev_growth_pct: float | None
    tier: str


def fetch_pending(env: EnvName, limit: int | None) -> list[CompanyRow]:
    sql = """
        SELECT id::text, nif, nombre, localidad, descripcion, web,
               rev_y0_keur, rev_y1_keur, rev_growth_pct, tier
        FROM companies
        WHERE ia_fit='fit'
          AND tier='T4'
          AND research_done_at IS NULL
          AND (web IS NULL OR web='' OR web='0')
        ORDER BY nif
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    with get_session(env) as s:
        rows = s.execute(text(sql)).mappings().all()
    return [
        CompanyRow(
            id=r["id"], nif=r["nif"], nombre=r["nombre"],
            localidad=r["localidad"] or "",
            descripcion=r["descripcion"] or "",
            web=r["web"], rev_y0_keur=r["rev_y0_keur"],
            rev_y1_keur=r["rev_y1_keur"], rev_growth_pct=r["rev_growth_pct"],
            tier=r["tier"],
        )
        for r in rows
    ]


def persist_descartado(env: EnvName, company_id: str, reason: str) -> None:
    """No domain inferred -> tier=descartado."""
    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE companies
                SET tier='descartado',
                    research_data = jsonb_build_object(
                        '_descartado_reason', :reason,
                        '_descartado_at', now()::text,
                        '_research_method', 'option_c_nowebsite'
                    ),
                    research_done_at = now()
                WHERE id = cast(:cid as uuid)
                """
            ),
            {"cid": company_id, "reason": reason},
        )
        s.commit()


def persist_research(
    env: EnvName, company_id: str, research_data: dict[str, Any],
    domain: str, smtp_status: str,
) -> None:
    """Update companies.research_data + smtp_status como metadato."""
    import json as _json
    enriched = {
        **research_data,
        "_inferred_domain": domain,
        "_smtp_status": smtp_status,
    }
    with get_session(env) as s:
        s.execute(
            text(
                """
                UPDATE companies
                SET research_data = cast(:rd as jsonb),
                    research_done_at = now()
                WHERE id = cast(:cid as uuid)
                """
            ),
            {"cid": company_id, "rd": _json.dumps(enriched)},
        )
        s.commit()


def insert_contact(env: EnvName, company_id: str, email: str) -> str | None:
    """INSERT contact con email_source='option_c_t4'. Idempotente por
    (company_id, email)."""
    with get_session(env) as s:
        row = s.execute(
            text(
                """
                INSERT INTO contacts (
                    company_id, email, email_verified, email_source,
                    email_type, email_priority, nombre, cargo, is_primary
                ) VALUES (
                    cast(:cid as uuid), :email, true, 'option_c_t4',
                    'corporativo_pequeno', 4, NULL, NULL, true
                )
                ON CONFLICT (company_id, email) DO NOTHING
                RETURNING id::text
                """
            ),
            {"cid": company_id, "email": email},
        ).fetchone()
        s.commit()
    return str(row[0]) if row else None


@dataclass(slots=True)
class RunCounters:
    processed: int = 0
    no_domain: int = 0
    with_domain: int = 0
    catch_all: int = 0
    contacts_inserted: int = 0
    smtp_no_match: int = 0
    research_failed: int = 0
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_usd: float = 0.0


def process_one(
    env: EnvName, c: CompanyRow, dry_run: bool, counters: RunCounters,
) -> None:
    counters.processed += 1

    # PASO 1: infer dominio.
    candidate = infer_domain(c.nombre)
    if candidate is None:
        counters.no_domain += 1
        logger.info("  no_domain nif=%s nombre=%r", c.nif, c.nombre[:40])
        if not dry_run:
            persist_descartado(env, c.id, "no_domain_inferred")
        return

    counters.with_domain += 1
    logger.info("  domain_inferred nif=%s domain=%s mx=%d",
                c.nif, candidate.domain, len(candidate.mx_records))

    # PASO 2: research IA.
    try:
        rr = research_company_nowebsite({
            "nombre": c.nombre, "nif": c.nif, "localidad": c.localidad,
            "descripcion": c.descripcion, "rev_y0_keur": c.rev_y0_keur,
            "rev_y1_keur": c.rev_y1_keur, "rev_growth_pct": c.rev_growth_pct,
            "tier": c.tier,
        })
        counters.total_tokens_in += rr.tokens_in
        counters.total_tokens_out += rr.tokens_out
        if rr.cost_usd is not None:
            counters.total_cost_usd += rr.cost_usd
        research_data = rr.research_data
        if research_data.get("_failed"):
            counters.research_failed += 1
    except Exception as e:
        logger.warning("  research_failed nif=%s: %s", c.nif, e)
        counters.research_failed += 1
        research_data = {
            "_failed": True, "_failed_reason": f"exception: {type(e).__name__}",
            "_research_method": "option_c_nowebsite",
        }

    # PASO 3: catch-all detection.
    catch_email = catch_all_probe(candidate.domain)
    catch_detected = False
    try:
        catch_detected = is_catch_all(catch_email, candidate.mx_records)
    except Exception as e:
        logger.warning("  catch_all_probe_error nif=%s: %s", c.nif, e)

    if catch_detected:
        counters.catch_all += 1
        logger.info("  catch_all nif=%s domain=%s -> skip", c.nif, candidate.domain)
        if not dry_run:
            persist_research(env, c.id, research_data, candidate.domain, "catch_all_skipped")
        return

    # PASO 4: SMTP probe sobre candidatos.
    candidates = permute_emails(candidate.domain)
    valid_email: str | None = None
    for cand in candidates:
        result = probe_email(cand, candidate.mx_records)
        if result.status == EmailStatus.VALID:
            valid_email = cand
            logger.info("  smtp_valid nif=%s email=%s", c.nif, cand)
            break
        logger.debug("  smtp_%s %s code=%s", result.status.value, cand, result.smtp_code)

    if not dry_run:
        smtp_status = "verified" if valid_email else "no_match"
        persist_research(env, c.id, research_data, candidate.domain, smtp_status)
        if valid_email:
            contact_id = insert_contact(env, c.id, valid_email)
            if contact_id:
                counters.contacts_inserted += 1
        else:
            counters.smtp_no_match += 1
    elif valid_email:
        counters.contacts_inserted += 1
    else:
        counters.smtp_no_match += 1


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--max-cost-usd", type=float, default=5.0,
                   help="Cap defensivo. Paro si total_cost_usd supera.")
    p.add_argument("--dry-run", action="store_true",
                   help="No persiste BD. Util para smoke.")
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(f"option_c_t4  env={env}  limit={args.limit}  "
          f"max_cost_usd={args.max_cost_usd}  dry_run={args.dry_run}")
    print("=" * 76)

    pending = fetch_pending(env, args.limit)
    if not pending:
        print("No hay companies T4 fit sin research. Nada que hacer.")
        return 0
    print(f"[fetch] {len(pending)} empresas a procesar")

    counters = RunCounters()
    t0 = time.monotonic()

    for i, c in enumerate(pending, 1):
        print(f"\n[{i:>3}/{len(pending)}] {c.nif} {c.nombre[:50]}")
        try:
            process_one(env, c, args.dry_run, counters)
        except KeyboardInterrupt:
            print("\nInterrumpido por usuario. Resultado parcial:")
            break
        except Exception as e:
            logger.exception("process_one error nif=%s: %s", c.nif, e)

        # Rate limit entre empresas (no entre dominios -- aqui es por empresa
        # porque cada empresa tiene 1 dominio inferido).
        if i < len(pending):
            time.sleep(SLEEP_BETWEEN_DOMAINS_S)

        # Cap defensivo cost.
        if counters.total_cost_usd >= args.max_cost_usd:
            logger.warning("max_cost_usd alcanzado (%.4f >= %.2f), parando",
                           counters.total_cost_usd, args.max_cost_usd)
            return 3

        # Progreso cada 25.
        if i % 25 == 0:
            print(f"\n  progreso: processed={counters.processed} "
                  f"with_domain={counters.with_domain} "
                  f"catch_all={counters.catch_all} "
                  f"inserted={counters.contacts_inserted} "
                  f"cost_usd={counters.total_cost_usd:.4f}")

    elapsed = time.monotonic() - t0
    print()
    print("=" * 76)
    print(f"FIN option_c_t4  env={env}  elapsed={elapsed:.1f}s")
    print(f"  procesadas:           {counters.processed} / {len(pending)}")
    print(f"  con dominio inferido: {counters.with_domain}")
    print(f"  sin dominio:          {counters.no_domain}")
    print(f"  catch_all detectado:  {counters.catch_all}")
    print(f"  contacts insertados:  {counters.contacts_inserted}")
    print(f"  smtp sin match:       {counters.smtp_no_match}")
    print(f"  research failed:      {counters.research_failed}")
    print(f"  tokens: in={counters.total_tokens_in}  out={counters.total_tokens_out}")
    print(f"  coste LLM USD: {counters.total_cost_usd:.4f} (cap {args.max_cost_usd})")
    print("=" * 76)

    return 0


if __name__ == "__main__":
    sys.exit(main())
