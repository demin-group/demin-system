"""scrape_emails.py — recuperación de emails visibles en la web del prospecto.

Historia: el stub original (D17) quedó descartado del flujo activo en favor de
Hunter (D19 → D21). Reactivado 2026-06-03 por decisión PM para la recuperación
de T2 fit sin contactos: Hunter + política D20 dejaron 33 T2 grandes (5-19M€)
sin ningún email, y PM autorizó scraping de emails públicos de sus webs como
palanca de recuperación dirigida.

**Override D20 consciente (PM 2026-06-03):** para T2 la política D20 rechaza
`corporativo_pequeno` (info@, comercial@, obras@...). Esta recuperación los
acepta — un buzón corporativo real encontrado en la web propia es mejor que
excluir a una constructora de 15M€ del pipeline. Los contactos quedan con
`email_source='web_scrape'` y `email_type` honesto para auditoría. Los
prefijos de la whitelist NEGATIVA D20 (rrhh, prensa, noreply...) siguen
descartándose siempre.

Flujo por empresa (tier + fit + sin contacts, mismo criterio que
`find_contacts.fetch_pending`):
    1. Resuelve dominio registrable de `companies.web` (tldextract).
       Skip si está en `GENERIC_DOMAIN_BLACKLIST` o `DIRECTORY_DOMAINS`.
    2. Descarga home + páginas internas típicas (/contacto, /aviso-legal,
       /equipo...) + links del home que matcheen palabras de contacto.
       Máx `--max-pages` páginas, pausa cortés entre requests.
    3. Extrae emails de `mailto:` y de regex sobre el HTML, filtrando a
       emails del dominio propio de la empresa (un email de tercero en la
       web no es un contacto de la empresa).
    4. Prioriza: persona > comercial > obras > proyectos > genéricos
       operativos > info > contacto > administracion > resto (orden PM).
    5. Inserta hasta `--max-emails` por empresa (`ON CONFLICT DO NOTHING`),
       primero por prioridad → `is_primary=true`, `email_source='web_scrape'`.
       Actualiza `ia_fit_reason` a 'recuperada_web_scrape' (audit trail).

NO inventa emails (L49: cero permutación). Solo persiste lo que aparece
literalmente en la web pública de la empresa.

CLI:
    cd apps/workers
    uv run python -m pipeline.scrape_emails --env prod --tier T2 --dry-run --limit 5
    uv run python -m pipeline.scrape_emails --env prod --tier T2 \
        --exclude-nif B28293884 --exclude-nif B87984258 --mark-verify B91345264
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Literal
from urllib.parse import urljoin, urlparse

import httpx
import tldextract
from selectolax.parser import HTMLParser
from sqlalchemy import text

from pipeline.find_contacts import resolve_domain_from_company
from pipeline.infer_domain import GENERIC_DOMAIN_BLACKLIST
from shared.email_policy import NEGATIVE_PREFIXES, POSITIVE_PREFIXES

EnvName = Literal["dev", "prod"]

logger = logging.getLogger("demin.scrape_emails")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

# Directorios / plataformas que aparecen en `companies.web` pero no son el
# dominio de la empresa. Scrapearlos daría emails de la plataforma.
DIRECTORY_DOMAINS = frozenset({
    "houzz.es", "houzz.com", "habitissimo.es", "paginasamarillas.es",
    "linkedin.com", "facebook.com", "instagram.com", "idealista.com",
    "google.com", "wixsite.com",
})

# Rutas internas típicas donde las webs corporativas publican emails.
CANDIDATE_PATHS = (
    "/contacto", "/contact", "/contactar", "/contacto/", "/contact/",
    "/aviso-legal", "/aviso-legal/", "/legal",
    "/equipo", "/sobre-nosotros", "/quienes-somos", "/empresa", "/nosotros",
)

# Palabras en href/texto de un link del home que lo marcan como candidato.
_LINK_HINT = re.compile(
    r"contact|aviso|legal|equipo|nosotros|somos|empresa|about|team", re.I
)

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# Falsos positivos típicos del regex sobre HTML (assets @2x, libs JS, etc.).
_JUNK_TLD = re.compile(r"\.(png|jpe?g|gif|webp|svg|css|js|woff2?|ico)$", re.I)
_JUNK_LOCAL = frozenset({
    "noreply", "no-reply", "sentry", "example", "your", "tu", "email",
    "name", "user", "nombre", "correo",
})

# Prefijos genéricos que no son ni positivos D20 ni negativos pero tampoco
# son personas (defensa para no clasificar `ventas@` como persona).
_EXTRA_GENERIC = frozenset({
    "admin", "ventas", "sales", "compras", "estudios", "licitaciones",
    "oficinatecnica", "calidad", "central", "clientes", "recepcion",
    "mail", "web", "online", "madrid", "secretaria", "presupuestos",
})

# Prefijos que se descartan siempre además de la whitelist negativa D20
# (buzones legales/privacidad: escribir prospección ahí es contraproducente).
_LEGAL_PREFIXES = frozenset({"dpo", "lopd", "rgpd", "privacidad", "privacy", "legal"})

# Orden PM 2026-06-03: persona > comercial > obras > proyectos > genéricos
# operativos > info > contacto > administracion > resto genérico.
_RANK_EXACT = {
    "comercial": 1,
    "obras": 2,
    "proyectos": 3,
    "gerencia": 4, "direccion": 4, "despacho": 4, "oficina": 4,
    "gestion": 4, "compras": 4, "estudios": 4, "licitaciones": 4,
    "oficinatecnica": 4, "presupuestos": 4,
    "info": 5,
    "contacto": 6, "contact": 6, "hola": 6, "hello": 6,
    "administracion": 7, "admin": 7,
}
_RANK_PERSONA = 0
_RANK_OTHER_GENERIC = 8

_ALL_GENERIC = POSITIVE_PREFIXES | _EXTRA_GENERIC


@dataclass(slots=True)
class ScrapedEmail:
    email: str
    rank: int
    via_mailto: bool

    @property
    def is_persona(self) -> bool:
        return self.rank == _RANK_PERSONA


@dataclass(slots=True)
class CompanyResult:
    nif: str
    nombre: str
    domain: str | None
    status: str  # ok | no_emails | fetch_failed | js_required | skipped_*
    emails: list[ScrapedEmail] = field(default_factory=list)
    pages_fetched: int = 0
    detail: str = ""


def rank_email(email: str) -> int | None:
    """Prioridad PM del email por su parte local. `None` = descartar."""
    local, _, domain = email.lower().partition("@")
    if local in NEGATIVE_PREFIXES or local in _LEGAL_PREFIXES or local in _JUNK_LOCAL:
        return None
    if local in _RANK_EXACT:
        return _RANK_EXACT[local]
    if local in _ALL_GENERIC:
        return _RANK_OTHER_GENERIC
    # `empresa@empresa.es` (local == primer label del dominio) es el buzón
    # corporativo con nombre de marca, no una persona (visto en run
    # 2026-06-03: iycsa@iycsa.es, trauxia@trauxia.es, divegon@divegon.com…).
    if local == domain.split(".", 1)[0]:
        return _RANK_OTHER_GENERIC
    # No genérico conocido → asumimos buzón de persona (nombre, n.apellido…).
    return _RANK_PERSONA


def extract_emails(html: str, company_domain: str) -> list[ScrapedEmail]:
    """Emails del dominio propio en un HTML: mailto primero, regex después."""
    found: dict[str, ScrapedEmail] = {}

    def consider(raw: str, via_mailto: bool) -> None:
        email = raw.strip().strip(".,;:<>()[]\"'").lower()
        if not email or "@" not in email or _JUNK_TLD.search(email):
            return
        if not EMAIL_RE.fullmatch(email):
            return
        ext = tldextract.extract(email.split("@", 1)[1])
        if not ext.domain or not ext.suffix:
            return
        if f"{ext.domain}.{ext.suffix}".lower() != company_domain:
            return  # email de tercero — no es contacto de la empresa
        rank = rank_email(email)
        if rank is None:
            return
        prev = found.get(email)
        if prev is None or (via_mailto and not prev.via_mailto):
            found[email] = ScrapedEmail(email=email, rank=rank, via_mailto=via_mailto)

    tree = HTMLParser(html)
    for node in tree.css("a[href]"):
        href = node.attributes.get("href") or ""
        if href.lower().startswith("mailto:"):
            target = href[7:].split("?", 1)[0]
            for part in target.split(","):
                consider(part.replace("%40", "@"), via_mailto=True)

    for match in EMAIL_RE.findall(html):
        consider(match, via_mailto=False)

    return sorted(found.values(), key=lambda e: (e.rank, not e.via_mailto, e.email))


def candidate_urls(base_url: str, home_html: str, max_pages: int) -> list[str]:
    """Home + rutas fijas + links del home que parezcan de contacto."""
    urls: list[str] = []
    seen: set[str] = set()
    base_netloc = urlparse(base_url).netloc.lower().removeprefix("www.")

    def add(u: str) -> None:
        parsed = urlparse(u)
        if parsed.netloc.lower().removeprefix("www.") != base_netloc:
            return  # no salir del dominio
        norm = parsed._replace(fragment="", query="").geturl().rstrip("/")
        if norm and norm not in seen:
            seen.add(norm)
            urls.append(norm)

    add(base_url)
    for path in CANDIDATE_PATHS:
        add(urljoin(base_url, path))
    tree = HTMLParser(home_html)
    for node in tree.css("a[href]"):
        href = node.attributes.get("href") or ""
        label = node.text() or ""
        if href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        if _LINK_HINT.search(href) or _LINK_HINT.search(label):
            add(urljoin(base_url, href))
    return urls[:max_pages]


def fetch_page(client: httpx.Client, url: str) -> str | None:
    try:
        resp = client.get(url)
        if resp.status_code == 200 and "text/html" in resp.headers.get(
            "content-type", "text/html"
        ):
            return resp.text
    except httpx.HTTPError as e:
        logger.debug("fetch fallo %s: %s", url, e)
    return None


def scrape_company(
    client: httpx.Client,
    nif: str,
    nombre: str,
    web: str | None,
    max_pages: int,
    pause_s: float,
) -> CompanyResult:
    domain = resolve_domain_from_company(web)
    if not domain:
        return CompanyResult(nif, nombre, None, "skipped_no_domain")
    if domain in GENERIC_DOMAIN_BLACKLIST or domain in DIRECTORY_DOMAINS:
        return CompanyResult(
            nif, nombre, domain, "skipped_generic_domain",
            detail=f"{domain} es directorio/genérico — búsqueda manual",
        )

    home_html: str | None = None
    base_url = ""
    for scheme_host in (f"https://{domain}", f"https://www.{domain}", f"http://{domain}"):
        home_html = fetch_page(client, scheme_host)
        if home_html is not None:
            base_url = scheme_host
            break
        time.sleep(pause_s)
    if home_html is None:
        return CompanyResult(nif, nombre, domain, "fetch_failed",
                             detail="home no responde (https/www/http)")

    emails: dict[str, ScrapedEmail] = {}
    pages = 0
    for url in candidate_urls(base_url, home_html, max_pages):
        html = home_html if pages == 0 else fetch_page(client, url)
        pages += 1
        if html:
            for se in extract_emails(html, domain):
                prev = emails.get(se.email)
                if prev is None or (se.via_mailto and not prev.via_mailto):
                    emails[se.email] = se
        if pages > 1:
            time.sleep(pause_s)

    result_emails = sorted(
        emails.values(), key=lambda e: (e.rank, not e.via_mailto, e.email)
    )
    if result_emails:
        return CompanyResult(nif, nombre, domain, "ok", result_emails, pages)

    # Heurística SPA: home sin emails Y casi sin texto visible → requiere JS.
    visible_text = HTMLParser(home_html).body
    text_len = len(visible_text.text(strip=True)) if visible_text else 0
    if text_len < 200:
        return CompanyResult(nif, nombre, domain, "js_required", [], pages,
                             detail=f"texto visible {text_len} chars — posible SPA")
    return CompanyResult(nif, nombre, domain, "no_emails", [], pages)


# ─── BD ────────────────────────────────────────────────────────────────────


def fetch_pending(env: EnvName, tier: str, limit: int | None) -> list[dict]:
    from shared.db import get_session  # noqa: PLC0415

    sql = """
        SELECT c.id, c.nif, c.nombre, c.web
        FROM companies c
        WHERE c.ia_fit = 'fit' AND c.tier = :tier
          AND NOT EXISTS (SELECT 1 FROM contacts ct WHERE ct.company_id = c.id)
        ORDER BY c.rev_y0_keur DESC NULLS LAST
    """
    if limit is not None:
        sql += f" LIMIT {int(limit)}"
    with get_session(env) as s:
        rows = s.execute(text(sql), {"tier": tier}).mappings().all()
    return [dict(r) for r in rows]


_INSERT_SQL = text(
    """
    INSERT INTO contacts
        (company_id, email, email_verified, email_source,
         email_type, email_priority, is_primary)
    VALUES
        (:company_id, :email, false, 'web_scrape',
         :email_type, :email_priority, :is_primary)
    ON CONFLICT (company_id, email) DO NOTHING
    """
)


def persist(
    env: EnvName,
    company_id: str,
    selected: list[ScrapedEmail],
    fit_reason: str,
) -> int:
    """Inserta los emails elegidos + actualiza ia_fit_reason. Devuelve
    inserts reales (ON CONFLICT descarta duplicados silenciosamente)."""
    from shared.db import get_session  # noqa: PLC0415

    inserted = 0
    with get_session(env) as s:
        for i, se in enumerate(selected):
            email_type = "nominal" if se.is_persona else "corporativo_pequeno"
            email_priority = 4 if se.is_persona else 5
            res = s.execute(
                _INSERT_SQL,
                {
                    "company_id": company_id,
                    "email": se.email,
                    "email_type": email_type,
                    "email_priority": email_priority,
                    "is_primary": i == 0,
                },
            )
            inserted += res.rowcount or 0
        if inserted:
            s.execute(
                text("UPDATE companies SET ia_fit_reason = :r WHERE id = :id"),
                {"r": fit_reason, "id": company_id},
            )
    return inserted


# ─── CLI ───────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="scrape_emails — extrae emails públicos de las webs de companies fit sin contacts"
    )
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--tier", choices=("T1", "T2", "T3", "T4"), required=True)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--max-pages", type=int, default=8)
    p.add_argument("--max-emails", type=int, default=2,
                   help="Máx emails a persistir por empresa (PM 2026-06-03: 2).")
    p.add_argument("--pause", type=float, default=0.4,
                   help="Pausa cortés entre requests al mismo dominio (s).")
    p.add_argument("--dry-run", action="store_true",
                   help="Scrapea y reporta sin escribir en BD.")
    p.add_argument("--exclude-nif", action="append", default=[],
                   help="NIF a saltar (repetible). Ej: dominio global multinacional.")
    p.add_argument("--mark-verify", action="append", default=[],
                   help="NIF cuyo ia_fit_reason marcar 'verificar_dominio' (discrepancia razón social ↔ web).")
    args = p.parse_args(argv)
    env: EnvName = args.env

    print("=" * 76)
    print(
        f"scrape_emails  env={env}  tier={args.tier}  limit={args.limit}  "
        f"max_pages={args.max_pages}  max_emails={args.max_emails}  "
        f"dry_run={args.dry_run}  exclude={args.exclude_nif}"
    )
    print("=" * 76)

    pending = fetch_pending(env, args.tier, args.limit)
    if not pending:
        print("No hay empresas pendientes (fit + tier sin contacts). Nada que hacer.")
        return 0
    print(f"[fetch] {len(pending)} empresas a procesar")

    results: list[CompanyResult] = []
    inserted_total = 0
    companies_ok = 0

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.6",
    }
    with httpx.Client(
        follow_redirects=True, timeout=10.0, headers=headers
    ) as client:
        for i, row in enumerate(pending, 1):
            if row["nif"] in args.exclude_nif:
                results.append(CompanyResult(
                    row["nif"], row["nombre"], None, "excluded_cli",
                    detail="excluida por --exclude-nif (revisión manual)",
                ))
                print(f"  [{i:>2}/{len(pending)}] {row['nombre'][:40]:<40} EXCLUIDA (CLI)")
                continue

            r = scrape_company(
                client, row["nif"], row["nombre"], row["web"],
                args.max_pages, args.pause,
            )
            results.append(r)

            n_persist = 0
            if r.status == "ok" and not args.dry_run:
                fit_reason = (
                    "recuperada_web_scrape_verificar_dominio"
                    if row["nif"] in args.mark_verify
                    else "recuperada_web_scrape"
                )
                n_persist = persist(
                    env, str(row["id"]), r.emails[: args.max_emails], fit_reason
                )
                inserted_total += n_persist
            if r.status == "ok":
                companies_ok += 1

            shown = ", ".join(e.email for e in r.emails[: args.max_emails]) or r.detail
            print(
                f"  [{i:>2}/{len(pending)}] {row['nombre'][:40]:<40} "
                f"{r.status:<22} ins={n_persist}  {shown[:60]}"
            )

    print()
    print("=" * 76)
    by_status: dict[str, int] = {}
    for r in results:
        by_status[r.status] = by_status.get(r.status, 0) + 1
    print(f"FIN scrape_emails  empresas={len(results)}  con_email={companies_ok}  "
          f"contacts_insertados={inserted_total}  dry_run={args.dry_run}")
    for status, n in sorted(by_status.items(), key=lambda kv: -kv[1]):
        print(f"  {status:<24} {n}")
    print("=" * 76)
    return 0


if __name__ == "__main__":
    sys.exit(main())
