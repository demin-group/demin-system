"""Adapter de OpenMercantil — fuente del NOMBRE del decisor (administrador/cargo).

OpenMercantil (https://openmercantil.es) parsea el BORME (Boletín Oficial del
Registro Mercantil, dato público por publicidad registral) y expone, por API
REST gratuita (CC BY 4.0, sin auth), el órgano de administración de cada
sociedad: administradores, consejeros y apoderados con NOMBRE y CARGO.

Por qué existe (decisión 2026-06-23): el cuello de botella del pipeline NO es
research ni modelo, es DATA — Hunter cubre ~8% decisor del sector (L22/L66) y
las webs PYME no publican equipo. BORME sí trae el nombre del responsable para
~42% del sector (medido sobre 40 empresas de demolición). Ese nombre alimenta
`HunterAdapter.find_email_by_name` (Email Finder por persona+dominio), cerrando
el bucle nombre_responsable → email_personal que hasta ahora estaba muerto.

LÍMITES conocidos (medidos contra la API real, 2026-06-23):
- OpenMercantil NO trae el dominio web (`company.website` sale vacío o apunta
  al BORME). El dominio debe venir de `companies.web` (SABI) o de infer_domain.
- El índice de búsqueda tiene el CIF/NIF de forma irregular (muchos items sin
  `cif`). El cruce por NIF funciona pero conviene fallback por razón social.
- Mayoría de cargos son `Apoderado` (persona real → `nominal`); menos
  `Administrador único/solidario` (→ `decisor`). El cargo se pasa tal cual a
  `email_policy.classify_email` como `position`, que ya lo clasifica.

RGPD: el nombre del administrador es dato público (publicidad registral) y su
tratamiento para contacto B2B al cargo se ampara en interés legítimo
(art. 19.1 LOPDGDD). Obligatorio: tratar solo el dato de cargo, declarar el
origen (BORME) en el primer contacto y respetar oposición/opt-out.

Llamadas vía httpx (dependencia ya presente). NO añade paquetes nuevos.
"""
from __future__ import annotations

import logging
import unicodedata
from dataclasses import dataclass

import httpx

logger = logging.getLogger("demin.openmercantil")

BASE_URL = "https://openmercantil.es/api/v1"
_TIMEOUT = httpx.Timeout(30.0)
_HEADERS = {"Accept": "application/json", "User-Agent": "demin-system/1.0 (+contacto B2B)"}

# ─── Ranking de cargo (mayor = más decisor). Se evalúa por substring sobre el
#     `role` normalizado. El primero que matchea gana. ──────────────────────
_ROLE_RANK: list[tuple[str, int]] = [
    ("administrador unico", 100),
    ("administrador solidario", 95),
    ("administrador mancomunado", 90),
    ("administrador", 88),
    ("consejero delegado", 85),
    ("presidente", 82),
    ("director general", 80),
    ("gerente", 78),
    ("socio", 72),
    ("apoderado", 60),
    ("consejero", 50),
    ("liquidador", 30),
    ("secretario", 25),
]
# Cargos/entidades a excluir como decisor de contacto.
_EXCLUDE_ROLE = ("auditor",)
# Sufijos de persona JURÍDICA (otra sociedad ocupando un cargo): se descartan,
# queremos personas físicas.
_JURIDICAL_SUFFIXES = (
    " sl", " s.l.", " s.l", " sa", " s.a.", " s.a", " slu", " slp", " sll",
    " sociedad limitada", " sociedad anonima", " coop", " s.coop", " aie",
)
# Partículas que se adhieren al apellido siguiente al parsear el nombre.
_PARTICLES = {"de", "del", "la", "las", "los", "san", "y", "da", "do", "dos",
              "van", "von", "mac", "mc", "di", "le"}


@dataclass(frozen=True)
class Officer:
    """Decisor extraído de BORME vía OpenMercantil.

    `name_registry` viene en orden registral (APELLIDOS NOMBRE, mayúsculas).
    `full_name_natural` es el orden natural (Nombre Apellidos) para pasar a
    Hunter Email Finder. `role` es el cargo literal del BORME, que se pasa a
    `email_policy.classify_email` como `position`.
    """

    name_registry: str
    role: str
    first_name: str
    last_name: str
    full_name_natural: str
    rank: int


# ─── Funciones puras (testeables sin red) ──────────────────────────────────
def _normalize(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def is_juridical_person(name: str) -> bool:
    """True si el `name` es una sociedad (otra empresa ocupando el cargo),
    no una persona física."""
    n = " " + _normalize(name)
    return any(n.endswith(suf) for suf in _JURIDICAL_SUFFIXES)


def rank_role(role: str | None) -> int:
    """Puntúa el cargo. -1 si es un cargo excluido (auditor). 10 si es un
    cargo desconocido pero presente (sigue siendo persona de contacto)."""
    r = _normalize(role)
    if not r:
        return 10
    if any(x in r for x in _EXCLUDE_ROLE):
        return -1
    for key, score in _ROLE_RANK:
        if key in r:
            return score
    return 10


def parse_spanish_name(registry_name: str) -> tuple[str, str, str]:
    """Convierte 'APELLIDO1 APELLIDO2 NOMBRE(S)' (orden registral del BORME)
    en (first_name, last_name, full_name_natural).

    Heurística: las dos primeras *unidades* de apellido (cada una puede llevar
    partículas: 'DE LA FUENTE') son apellidos; el resto es el nombre de pila.
    Si solo hay 2 tokens, el último es el nombre. Devuelve Title Case.

    Ejemplos:
      'FERNANDEZ MENCIA RICARDO'        -> ('Ricardo', 'Fernandez', 'Ricardo Fernandez Mencia')
      'CRESPO JIMENEZ JUAN JOSE'        -> ('Juan Jose', 'Crespo', 'Juan Jose Crespo Jimenez')
      'DE LA FUENTE GARCIA ANA'         -> ('Ana', 'De La Fuente', 'Ana De La Fuente Garcia')
      'GARCIA JUAN'                     -> ('Juan', 'Garcia', 'Juan Garcia')
    """
    toks = [t for t in registry_name.split() if t]
    if not toks:
        return "", "", ""
    if len(toks) == 1:
        w = toks[0].title()
        return w, "", w

    surnames: list[str] = []
    i = 0
    for _ in range(2):
        unit: list[str] = []
        while i < len(toks) and _normalize(toks[i]) in _PARTICLES:
            unit.append(toks[i])
            i += 1
        if i < len(toks):
            unit.append(toks[i])
            i += 1
        if unit:
            surnames.append(" ".join(unit))
    given_tokens = toks[i:]

    # Si no quedó nombre de pila (p. ej. 2 tokens), el último apellido es el nombre.
    if not given_tokens and surnames:
        given_tokens = [surnames.pop()]

    given = " ".join(given_tokens).title()
    surn = " ".join(surnames).title()
    first_name = given_tokens[0].title() if given_tokens else ""
    last_name = surnames[0].title() if surnames else ""
    full_natural = (given + " " + surn).strip()
    return first_name, last_name, full_natural


def pick_best_officer(current: list[dict]) -> Officer | None:
    """De la lista `current` de OpenMercantil, elige la mejor persona física
    por ranking de cargo. Devuelve None si no hay ninguna válida."""
    best: tuple[int, dict] | None = None
    for o in current or []:
        name = (o.get("name") or "").strip()
        if not name or is_juridical_person(name):
            continue
        sc = rank_role(o.get("role"))
        if sc < 0:
            continue
        if best is None or sc > best[0]:
            best = (sc, o)
    if best is None:
        return None
    score, o = best
    first, last, full = parse_spanish_name(o.get("name", ""))
    return Officer(
        name_registry=o.get("name", "").strip(),
        role=(o.get("role") or "").strip(),
        first_name=first,
        last_name=last,
        full_name_natural=full,
        rank=score,
    )


def _cif_matches(item_cif: str | None, nif: str) -> bool:
    return bool(item_cif) and _normalize(item_cif) == _normalize(nif)


# ─── Cliente HTTP ──────────────────────────────────────────────────────────
class OpenMercantilError(RuntimeError):
    pass


class OpenMercantilClient:
    """Cliente fino de la API de OpenMercantil. Reutilizable; cierra con
    `close()` o úsese como context manager."""

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=_TIMEOUT, headers=_HEADERS)
        self._owns = client is None

    def __enter__(self) -> OpenMercantilClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns:
            self._client.close()

    def _get(self, path: str, params: dict | None = None) -> dict:
        try:
            r = self._client.get(f"{BASE_URL}{path}", params=params)
        except httpx.HTTPError as e:
            raise OpenMercantilError(f"red: {e}") from e
        if r.status_code == 404:
            return {}
        if r.status_code != 200:
            raise OpenMercantilError(f"http {r.status_code} en {path}: {r.text[:200]}")
        try:
            return r.json()
        except ValueError as e:
            raise OpenMercantilError(f"json inválido en {path}") from e

    def search(self, query: str) -> list[dict]:
        return (self._get("/search", {"q": query}) or {}).get("items", []) or []

    def officers(self, slug: str) -> list[dict]:
        return (self._get(f"/company/{slug}/officers") or {}).get("current", []) or []

    def resolve_slug(self, nif: str | None, company_name: str | None) -> str | None:
        """Encuentra el slug de la empresa. Prioriza el match exacto por NIF;
        si no, cae al primer resultado de la búsqueda por razón social."""
        if nif:
            for item in self.search(nif):
                if _cif_matches(item.get("cif"), nif):
                    return item.get("slug")
        if company_name:
            items = self.search(company_name)
            if items:
                # match por alias/nombre normalizado, si no el primero
                target = _normalize(company_name)
                for item in items:
                    if _normalize(item.get("name")) == target:
                        return item.get("slug")
                return items[0].get("slug")
        return None

    def find_decisor(self, nif: str | None, company_name: str | None) -> Officer | None:
        """Punto de entrada: empresa (NIF y/o razón social) → mejor decisor
        físico del BORME, o None si no hay."""
        slug = self.resolve_slug(nif, company_name)
        if not slug:
            logger.info("openmercantil sin_slug nif=%s", nif)
            return None
        officer = pick_best_officer(self.officers(slug))
        # RGPD/PII: NO logamos el nombre de la persona física. Solo si hubo
        # match y el cargo (dato de función, no personal).
        logger.info(
            "openmercantil slug=%s decisor_found=%s rol=%s",
            slug, officer is not None, officer.role if officer else None,
        )
        return officer


def find_decisor_by_nif(nif: str | None, company_name: str | None) -> Officer | None:
    """Conveniencia de un solo uso (abre y cierra cliente)."""
    with OpenMercantilClient() as c:
        return c.find_decisor(nif, company_name)
