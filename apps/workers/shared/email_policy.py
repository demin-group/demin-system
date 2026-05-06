"""Política D20 — clasificación de emails para el pipeline de outreach.

Reglas confirmadas en sesión 2026-05-06 tras Frente E (commit 36d5077).
Fuente arquitectónica: tasks/todo.md §8.5.

Whitelists:
- Positiva (14 prefijos): aceptados como `corporativo_pequeno` SOLO en T1/T3/T4.
- Negativa (17 prefijos): siempre `descartado`, independiente de tier.

Política por tier:
- T1, T3, T4: aceptan decisor + nominal + corporativo_pequeno.
- T2:         aceptan decisor + nominal (no corporativo_pequeno).

Caso A3 (nombre + sin cargo + prefijo no whitelist):
- T1/T3/T4: nominal (gerente lee toda la cuenta en empresa pequeña).
- T2:       descartado (filtros administrativos exigen cargo).

La lógica está validada empíricamente sobre 25 empresas SABI en Frente E
(scripts/reanalyze_hunter_d20.py). Este módulo es la fuente operativa que
consume find_contacts.py (Sprint 4 paso 4); el script queda como artefacto
de auditoría de la decisión D21/D22.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Literal

EmailType = Literal["decisor", "nominal", "corporativo_pequeno", "descartado"]


@dataclass(frozen=True)
class Classification:
    email_type: EmailType
    reason: str


# ─── Whitelists por prefijo ────────────────────────────────────────────────
POSITIVE_PREFIXES: frozenset[str] = frozenset({
    "info", "contacto", "contact", "hola", "hello",
    "gerencia", "gestion", "direccion", "despacho", "oficina",
    "administracion", "obras", "proyectos", "comercial",
})

NEGATIVE_PREFIXES: frozenset[str] = frozenset({
    "marketing", "rrhh", "prensa",
    "comunicacion", "comunicaciones", "atencion",
    "noreply", "no-reply",
    "facturas", "contabilidad", "webmaster",
    "soporte", "support", "ayuda",
    "jobs", "empleo", "trabaja",
})

VALID_TIERS: frozenset[str] = frozenset({"T1", "T2", "T3", "T4"})

# ─── Patrones de cargo (todos sobre texto pre-normalizado) ─────────────────
# Override de cualquier match decisor: si el cargo contiene un rol descartado,
# va a la basura aunque también contenga tokens de decisor (e.g. "Marketing
# Director").
_NEGATIVE_ROLE_PATTERNS = [
    r"\bmarketing\b",
    r"\bcommunications?\b",
    r"\bcomms\b",
    r"comunicaci[oó]n",
    r"\brrhh\b",
    r"\bhr\b",
    r"recursos\s+humanos",
    r"human\s+resources",
    r"\bprensa\b",
    r"\bpress\b",
    r"prevention\s+specialist",
    r"\bprl\b",
    r"prevenci[oó]n\s+de\s+riesgos",
    r"internal\s+audit",
    r"\bauditor[ae]?\b",
    r"customer\s+(?:support|service)",
    r"atenci[oó]n\s+al\s+cliente",
    r"recepci[oó]n",
    r"\breceptionist\b",
]
_NEGATIVE_ROLE = [re.compile(p) for p in _NEGATIVE_ROLE_PATTERNS]

# Decisor estricto. `Director`/`Manager` solos no entran — exigen contexto
# operativo (technical/operations/works/etc.) o jerarquía explícita
# (general/managing/...).
_STRICT_DECISOR_PATTERNS = [
    r"\bceo\b",
    r"\bcfo\b",
    r"\bcoo\b",
    r"\bcto\b",
    r"\bcio\b",
    r"director\s+general",
    r"director\s+ejecutivo",
    r"director\s+t[eé]cnico",
    r"director\s+de\s+operaciones",
    r"director\s+de\s+obras?",
    r"director\s+comercial",
    r"director\s+de\s+compras",
    r"director\s+(?:de|of)\s+procurement",
    r"director\s+(?:de|of)\s+(?:proyectos|projects)",
    r"\bgerente\b",
    r"general\s+manager",
    r"managing\s+director",
    r"jefe\s+de\s+obras?",
    r"jefe\s+de\s+operaciones",
    r"jefe\s+de\s+proyectos",
    r"jefe\s+de\s+compras",
    r"jefe\s+t[eé]cnico",
    r"responsable\s+de\s+obras?",
    r"responsable\s+de\s+compras",
    r"responsable\s+t[eé]cnico",
    r"responsable\s+de\s+operaciones",
    r"\bpresidente\b",
    r"\bfundador\b",
    r"\bfounder\b",
    r"co-?founder",
    r"\bowner\b",
    r"\bpropietario\b",
    r"\bsocio\b",
    # `administrador de sistemas` queda fuera vía lookahead negativo.
    r"\badministrador\b(?!\s+de\s+sistemas)",
    r"operations\s+manager",
    r"technical\s+manager",
    r"technical\s+office\s+manager",
    r"infrastructure\s+.*\s+manager",
    r"civil\s+works\s+.*\s+manager",
    r"head\s+of\s+(?:operations|construction|works?|procurement|technical|projects?)",
    r"works?\s+manager",
    r"project\s+director",
    r"plant\s+manager",
]
_STRICT_DECISOR = [re.compile(p) for p in _STRICT_DECISOR_PATTERNS]


def _normalize(s: str | None) -> str:
    """Lowercase + sin acentos + strip. NFD descompone los acentos en
    char base + combining mark; filtramos los combiners (categoría Mn)."""
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def _email_prefix(email: str) -> str:
    """Parte local antes del primer `@`, lowercased. Si no hay `@`, devuelve
    la cadena entera (defensivo: el adapter puede mandar algo sin formato)."""
    return email.split("@", 1)[0].lower()


def classify_email(
    email: str,
    position: str | None,
    person_name: str | None,
    tier: str,
) -> Classification:
    """Aplica las reglas D20 a un email crudo del adapter primario.

    Orden de evaluación (importa — el primero que matchea gana):
        1. prefijo en whitelist negativa → descartado
        2. cargo en whitelist negativa de roles → descartado (override)
        3. cargo decisor estricto → decisor
        4. prefijo en whitelist positiva → corporativo_pequeno
        5. cargo identificable no decisor → nominal
        6. caso A3 (nombre + sin cargo + prefijo no whitelist):
           T1/T3/T4 → nominal, T2 → descartado
        7. sin cargo, sin nombre, prefijo no whitelist → descartado

    `tier` se usa solo en la regla 6 (A3). El filtro tier-corporativo se
    aplica después en `is_acceptable_for_tier`.
    """
    prefix = _email_prefix(email)
    norm_pos = _normalize(position)
    has_name = bool(person_name and person_name.strip())

    # 1) prefijo negativo
    if prefix in NEGATIVE_PREFIXES:
        return Classification("descartado", f"prefijo `{prefix}@` en whitelist negativa")

    # 2) rol negativo (override sobre decisor)
    if norm_pos:
        for pat in _NEGATIVE_ROLE:
            if pat.search(norm_pos):
                return Classification(
                    "descartado",
                    f"rol descartado por whitelist negativa: '{position}'",
                )

    # 3) decisor estricto
    if norm_pos:
        for pat in _STRICT_DECISOR:
            if pat.search(norm_pos):
                return Classification("decisor", f"cargo decisor: '{position}'")

    # 4) prefijo positivo
    if prefix in POSITIVE_PREFIXES:
        return Classification(
            "corporativo_pequeno",
            f"prefijo `{prefix}@` en whitelist positiva",
        )

    # 5) cargo identificable no decisor
    if norm_pos:
        return Classification("nominal", f"cargo identificable no decisor: '{position}'")

    # 6) A3 — nombre conocido sin cargo
    if has_name:
        if tier == "T2":
            return Classification(
                "descartado",
                f"A3: nombre sin cargo + tier T2 → descartado ('{person_name}')",
            )
        return Classification(
            "nominal",
            f"A3: nombre sin cargo + tier {tier} → nominal_sin_cargo ('{person_name}')",
        )

    # 7) nada
    return Classification(
        "descartado", f"sin cargo ni nombre, prefijo `{prefix}@` no whitelist"
    )


def is_acceptable_for_tier(email_type: EmailType, tier: str) -> bool:
    """Política por tier (D20):
        T1, T3, T4: aceptan decisor + nominal + corporativo_pequeno.
        T2:         aceptan decisor + nominal (no corporativo_pequeno).
        descartado: nunca aceptado.
    """
    if tier not in VALID_TIERS:
        raise ValueError(
            f"tier inválido: {tier!r}; esperado uno de {sorted(VALID_TIERS)}"
        )
    if email_type == "descartado":
        return False
    if email_type == "corporativo_pequeno":
        return tier != "T2"
    return email_type in ("decisor", "nominal")
