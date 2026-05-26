"""infer_domain.py -- inferencia heuristica de dominio para empresas sin web.

Opcion C T4 (sesion 2026-05-26). Para una company sin `web` declarada en
Sabi, intenta adivinar el dominio probando variantes <slug>.<tld> con
DNS MX lookup. Si una variante devuelve MX records, esa es el candidato.

NO usa Google search, NO usa scraping de directorios -- solo heuristica
+ MX. Coste: 0 USD, ~50ms por lookup.

Ver doc completo: docs/option_c_t4_pipeline.md
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable

import dns.exception
import dns.resolver


# Sufijos legales que quitar antes de slugificar.
LEGAL_SUFFIXES = (
    "sociedad limitada",
    "sociedad anonima",
    "sociedad anónima",
    "sociedad limitada unipersonal",
    "sociedad cooperativa",
    "comunidad de bienes",
    "s.l.u.",
    "s.l.u",
    "slu",
    "s.l.",
    "s.l",
    "sl",
    "s.a.",
    "s.a",
    "sa",
    "c.b.",
    "cb",
    "scl",
    "ltd",
    "ltda",
    "y cia",
    "y cía",
    "& cia",
)

# Stopwords sin valor identificador (no quitamos siempre, solo si la
# empresa tiene >=3 palabras y quitarlas deja >=1 palabra util).
STOPWORDS = (
    "de", "del", "la", "el", "los", "las", "y", "e", "o",
    "para", "por", "en", "con", "a", "al",
)

TLDS_TO_TRY = ("es", "com", "eu")


@dataclass(slots=True, frozen=True)
class DomainCandidate:
    domain: str  # dominio sin scheme, ej "demolicionesperez.es"
    mx_records: tuple[str, ...]


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)
    )


def slugify_company_name(nombre: str) -> list[str]:
    """Genera variantes de slug a partir del nombre legal de la empresa.

    Devuelve lista ordenada por prioridad:
    1. Variante con palabras juntas (`demolicionesperez`).
    2. Variante con guiones (`demoliciones-perez`).

    Si la limpieza deja una sola palabra, solo devuelve esa.
    """
    if not nombre:
        return []
    s = _strip_accents(nombre).lower()
    # Quitar sufijos legales. Aplicar en orden de mas largo a mas corto.
    for suffix in sorted(LEGAL_SUFFIXES, key=len, reverse=True):
        # Match sufijo al final (con boundary " " o final-de-string).
        pattern = r"(?:^|\s)" + re.escape(suffix) + r"\s*$"
        s = re.sub(pattern, "", s).strip()
    # Quitar caracteres no alfanumericos (excepto espacio).
    s = re.sub(r"[^a-z0-9\s]", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return []
    words = s.split()
    # Si quitando stopwords queda algo razonable, usar version sin ellos
    # para la variante con guiones.
    words_no_stop = [w for w in words if w not in STOPWORDS]
    if not words_no_stop:
        words_no_stop = words

    out: list[str] = []
    # Variante 1: todo junto.
    joined = "".join(words_no_stop)
    if joined:
        out.append(joined)
    # Variante 2: guiones (solo si hay >=2 palabras tras stopword removal).
    if len(words_no_stop) >= 2:
        out.append("-".join(words_no_stop))
    # Variante 3: solo primera palabra significativa (a veces nombres
    # cortos cuelgan de `<primerapalabra>.es`).
    if len(words_no_stop) >= 2 and len(words_no_stop[0]) >= 4:
        out.append(words_no_stop[0])
    # Deduplicar manteniendo orden.
    seen: set[str] = set()
    deduped: list[str] = []
    for w in out:
        if w and w not in seen:
            seen.add(w)
            deduped.append(w)
    return deduped


def _mx_records_for(domain: str, timeout: float = 5.0) -> tuple[str, ...]:
    """Lookup MX records. Devuelve tupla de hostnames de MX (sin priority)
    ordenados por prioridad ascendente. Tupla vacia si NXDOMAIN, sin MX,
    o timeout.
    """
    try:
        resolver = dns.resolver.Resolver()
        resolver.lifetime = timeout
        resolver.timeout = timeout
        answer = resolver.resolve(domain, "MX")
        sorted_rdata = sorted(answer, key=lambda r: int(r.preference))
        return tuple(str(r.exchange).rstrip(".") for r in sorted_rdata)
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.Timeout, dns.resolver.NoNameservers):
        return ()
    except Exception:
        return ()


def infer_domain(
    nombre: str,
    *,
    tlds: Iterable[str] = TLDS_TO_TRY,
    mx_timeout: float = 5.0,
) -> DomainCandidate | None:
    """Intenta inferir dominio para una empresa sin web declarada.

    Algoritmo: combinatoria de slugs * TLDs, primer match con MX gana.
    Orden de preferencia: (slug_variant_1, .es), (slug_variant_2, .es),
    (slug_variant_1, .com), etc.

    Returns:
        DomainCandidate si encuentra match, None si ninguna combinacion
        tiene MX records.
    """
    slugs = slugify_company_name(nombre)
    if not slugs:
        return None
    # Iterar primero por TLD prioritario (.es), luego por slug. Razon:
    # en PYME ES, dominio .es es ~3x mas comun que .com.
    for tld in tlds:
        for slug in slugs:
            candidate = f"{slug}.{tld}"
            mx = _mx_records_for(candidate, timeout=mx_timeout)
            if mx:
                return DomainCandidate(domain=candidate, mx_records=mx)
    return None
