"""apps/workers/scripts/reanalyze_hunter_d20.py

Frente E — re-análisis del output crudo de Frente C (Hunter, commit
3c5b7a9) bajo el criterio dual D20 SIN reejecutar Hunter (cero
créditos consumidos).

Calcula hit rate decisor estricto (criterio antiguo, ya conocido al
8% global) vs hit rate D20 (criterio nuevo: decisor + nominal +
corporativo_pequeno con política por tier) y emite veredicto
operacional.

Lee:     apps/workers/scripts/probe_hunter_output/results.json
Escribe: apps/workers/scripts/probe_hunter_output/d20_reanalysis.md
         (gitignored — contiene PII real de Hunter)

Reglas D20 (confirmadas con humano en sesión 2026-05-06):

- Whitelist NEGATIVA por prefijo (siempre descartado, todos los tiers):
    marketing, rrhh, prensa, noreply, facturas, contabilidad,
    webmaster, soporte, comunicacion, atencion

- Whitelist POSITIVA por prefijo (corporativo_pequeno; aceptado SOLO
  en T1/T3/T4):
    info, contacto, hola, gerencia, obras, proyectos, comercial,
    direccion, despacho, oficina, hello, contact, administracion,
    gestion

- Cargos decisor estricto: gerente, director general, CEO/CFO/COO/CTO,
  jefe de obra, responsable de compras, director técnico, jefe de
  proyectos, jefe de operaciones, manager con contexto operativo
  (technical/operations/works/infrastructure/civil works), founder,
  propietario, presidente.
  Bare "Director" o "Manager" sin contexto → NO decisor (cae a nominal).

- Cargos descartados por rol (overrides cualquier match decisor o
  nominal): marketing, communications, comms, RRHH/HR, prensa, press,
  prevention specialist / PRL, internal audit, customer support,
  recepción.

- Cargos nominales: cualquier cargo identificable que NO sea decisor
  estricto y NO sea descartado por rol (Engineer, Coordinator, Project
  Manager generic, Architect, Technician, Specialist no-prevention,
  Department Head, bare "Director", bare "Manager", etc.).

- Caso A3 (nombre conocido + prefijo personal + sin cargo):
    T1/T3/T4: nominal (gerente lee toda la cuenta en empresa pequeña)
    T2:       descartado (filtros administrativos exigen cargo)

- Caso C1 (T4 sin web — Hunter fuzzy mapea a empresa distinta):
    Si la marca del nombre SABI no aparece en la organización resuelta
    por Hunter → descartado completo (falso positivo, outreach iría a
    la empresa equivocada).

- Política por tier:
    T1, T3, T4: aceptan decisor + nominal + corporativo_pequeno
    T2:         aceptan decisor + nominal (no corporativo_pequeno)
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

OUTPUT_DIR = Path(__file__).resolve().parent / "probe_hunter_output"
INPUT_JSON = OUTPUT_DIR / "results.json"
REPORT_MD = OUTPUT_DIR / "d20_reanalysis.md"

# ─── normalización ─────────────────────────────────────────────────────────
def _normalize(s: str | None) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


# ─── whitelists D20 ────────────────────────────────────────────────────────
POSITIVE_PREFIXES: set[str] = {
    "info", "contacto", "hola", "gerencia", "obras", "proyectos",
    "comercial", "direccion", "despacho", "oficina", "hello", "contact",
    "administracion", "gestion",
}

NEGATIVE_PREFIXES: set[str] = {
    "marketing", "rrhh", "prensa", "noreply", "no-reply",
    "facturas", "contabilidad", "webmaster", "soporte",
    "comunicacion", "comunicaciones", "atencion",
}

# ─── patrones de cargo ──────────────────────────────────────────────────────
NEGATIVE_ROLE_PATTERNS_RAW = [
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
NEGATIVE_ROLE = [re.compile(p) for p in NEGATIVE_ROLE_PATTERNS_RAW]

STRICT_DECISOR_PATTERNS_RAW = [
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
STRICT_DECISOR = [re.compile(p) for p in STRICT_DECISOR_PATTERNS_RAW]

# ─── clasificación ──────────────────────────────────────────────────────────
EmailType = Literal["decisor", "nominal", "corporativo_pequeno", "descartado"]


@dataclass
class Classification:
    email_type: EmailType
    reason: str


def classify_email(
    email: str,
    position: str | None,
    person_name: str | None,
    tier: str,
) -> Classification:
    """Aplica reglas D20 (con A3 híbrido por tier) a un email crudo de Hunter."""
    prefix = email.split("@", 1)[0].lower()
    norm_pos = _normalize(position)
    has_name = bool(person_name and person_name.strip())

    # 1) prefijo en whitelist negativa → descartado
    if prefix in NEGATIVE_PREFIXES:
        return Classification("descartado", f"prefijo `{prefix}@` en whitelist negativa")

    # 2) cargo en whitelist negativa de roles → descartado (override)
    if norm_pos:
        for pat in NEGATIVE_ROLE:
            if pat.search(norm_pos):
                return Classification(
                    "descartado",
                    f"rol descartado por whitelist negativa: '{position}'",
                )

    # 3) cargo decisor estricto
    if norm_pos:
        for pat in STRICT_DECISOR:
            if pat.search(norm_pos):
                return Classification("decisor", f"cargo decisor: '{position}'")

    # 4) prefijo en whitelist positiva → corporativo_pequeno
    if prefix in POSITIVE_PREFIXES:
        return Classification(
            "corporativo_pequeno",
            f"prefijo `{prefix}@` en whitelist positiva",
        )

    # 5) cargo identificable no decisor → nominal
    if norm_pos:
        return Classification("nominal", f"cargo identificable no decisor: '{position}'")

    # 6) caso A3 — nombre conocido sin cargo, prefijo no whitelist
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

    # 7) sin cargo, sin nombre, prefijo no whitelist → descartado
    return Classification("descartado", f"sin cargo ni nombre, prefijo `{prefix}@` no whitelist")


def is_aceptable_for_tier(email_type: EmailType, tier: str) -> bool:
    """Política por tier (D20):
        T1, T3, T4: aceptan decisor + nominal + corporativo_pequeno
        T2:         aceptan decisor + nominal (no corporativo_pequeno)
    """
    if email_type == "descartado":
        return False
    if email_type == "corporativo_pequeno":
        return tier != "T2"
    return email_type in ("decisor", "nominal")


# ─── falso positivo Hunter en T4 (caso C1) ────────────────────────────────
GENERIC_TOKENS = {
    "sl", "slu", "sa", "sau", "sl.", "s.l.", "s.a.", "s.a", "s.l",
    "the", "el", "la", "los", "las", "de", "del", "y",
    "construccion", "construcciones", "constructora", "obras", "proyectos",
    "reformas", "reforma", "company", "co", "group", "grupo",
    "management", "international", "iberia", "spain",
}


def is_false_positive_t4(
    domain_input: str | None,
    domain_resolved: str | None,
    organization: str | None,
    company_name: str,
) -> bool:
    """Detecta el caso C1: T4 sin web donde Hunter hizo fuzzy match a una
    empresa distinta. Heurística: la primera palabra significativa
    (la "marca") del nombre SABI debe aparecer en la organización que
    Hunter atribuye al dominio resuelto. Si NO aparece, es falso positivo.
    """
    if not domain_resolved or domain_input:
        return False
    if not organization:
        return False

    norm_comp = _normalize(company_name)
    norm_org = _normalize(organization)

    comp_tokens = [
        t for t in re.findall(r"\w+", norm_comp)
        if t not in GENERIC_TOKENS and len(t) >= 3
    ]
    if not comp_tokens:
        return False  # no podemos juzgar sin marca

    brand = comp_tokens[0]
    return brand not in norm_org


# ─── reanálisis principal ──────────────────────────────────────────────────
@dataclass
class CompanyReanalysis:
    nif: str
    nombre: str
    tier: str
    domain_input: str | None
    domain_resolved: str | None
    organization: str | None
    n_emails_total: int
    is_false_positive: bool
    n_decisor: int
    n_nominal: int
    n_corporativo_pequeno: int
    n_descartado: int
    n_aceptable_d20: int            # según política tier
    n_decisor_estricto_frenteC: int # criterio antiguo (Frente C)
    detalle: list[dict]             # [{email, cargo, nombre, type, reason, accepted}]


def reanalyze(data: dict) -> list[CompanyReanalysis]:
    out: list[CompanyReanalysis] = []
    for r in data["results"]:
        all_emails = list(r.get("decisores", [])) + list(r.get("other_emails", []))
        domain_input = r.get("domain_input")
        domain_resolved = r.get("domain_resolved")
        organization = r.get("organization")
        is_fp = is_false_positive_t4(
            domain_input, domain_resolved, organization, r["nombre"]
        )

        counts = {"decisor": 0, "nominal": 0, "corporativo_pequeno": 0, "descartado": 0}
        n_aceptable = 0
        detalle: list[dict] = []

        for em in all_emails:
            email = em["email"]
            if is_fp:
                # forzamos descarte total — el email no es de la empresa target
                cls = Classification("descartado", "C1: falso positivo (Hunter fuzzy a otra empresa)")
            else:
                cls = classify_email(email, em.get("cargo"), em.get("nombre"), r["tier"])
            counts[cls.email_type] += 1
            accepted = (not is_fp) and is_aceptable_for_tier(cls.email_type, r["tier"])
            if accepted:
                n_aceptable += 1
            detalle.append(
                {
                    "email": email,
                    "cargo": em.get("cargo"),
                    "nombre": em.get("nombre"),
                    "confidence": em.get("confidence"),
                    "email_type": cls.email_type,
                    "reason": cls.reason,
                    "accepted": accepted,
                }
            )

        out.append(
            CompanyReanalysis(
                nif=r["nif"],
                nombre=r["nombre"],
                tier=r["tier"],
                domain_input=domain_input,
                domain_resolved=domain_resolved,
                organization=organization,
                n_emails_total=len(all_emails),
                is_false_positive=is_fp,
                n_decisor=counts["decisor"],
                n_nominal=counts["nominal"],
                n_corporativo_pequeno=counts["corporativo_pequeno"],
                n_descartado=counts["descartado"],
                n_aceptable_d20=n_aceptable,
                n_decisor_estricto_frenteC=len(r.get("decisores", [])),
                detalle=detalle,
            )
        )
    return out


# ─── agregados y veredicto ─────────────────────────────────────────────────
def aggregate_by_tier(rows: list[CompanyReanalysis]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for tier in ("T1", "T2", "T3", "T4"):
        tier_rows = [r for r in rows if r.tier == tier]
        n = len(tier_rows)
        with_decisor_strict = sum(1 for r in tier_rows if r.n_decisor_estricto_frenteC > 0)
        with_d20 = sum(1 for r in tier_rows if r.n_aceptable_d20 > 0)
        # también contamos decisor + nominal sin contar corporativo_pequeno (mid)
        with_decisor_or_nominal = sum(
            1 for r in tier_rows
            if (not r.is_false_positive) and (r.n_decisor + r.n_nominal) > 0
        )
        out[tier] = {
            "n": n,
            "with_decisor_strict": with_decisor_strict,
            "hit_rate_decisor_strict_pct": round(100 * with_decisor_strict / n, 1) if n else 0.0,
            "with_decisor_or_nominal": with_decisor_or_nominal,
            "hit_rate_decisor_nominal_pct": round(100 * with_decisor_or_nominal / n, 1) if n else 0.0,
            "with_d20": with_d20,
            "hit_rate_d20_pct": round(100 * with_d20 / n, 1) if n else 0.0,
        }
    return out


def aggregate_global(rows: list[CompanyReanalysis]) -> dict:
    n = len(rows)
    with_decisor_strict = sum(1 for r in rows if r.n_decisor_estricto_frenteC > 0)
    with_d20 = sum(1 for r in rows if r.n_aceptable_d20 > 0)
    with_decisor_nominal = sum(
        1 for r in rows
        if (not r.is_false_positive) and (r.n_decisor + r.n_nominal) > 0
    )
    return {
        "n": n,
        "hit_rate_decisor_strict_pct": round(100 * with_decisor_strict / n, 1) if n else 0.0,
        "hit_rate_decisor_nominal_pct": round(100 * with_decisor_nominal / n, 1) if n else 0.0,
        "hit_rate_d20_pct": round(100 * with_d20 / n, 1) if n else 0.0,
        "n_emails_aceptables_total": sum(r.n_aceptable_d20 for r in rows),
        "n_emails_brutos_total": sum(r.n_emails_total for r in rows),
        "n_falsos_positivos": sum(1 for r in rows if r.is_false_positive),
    }


def veredicto(global_d20_pct: float) -> tuple[str, str]:
    if global_d20_pct >= 50:
        return (
            "VERDE",
            "Hunter+D20 cubre >50% del sample. Hunter es adapter primario, "
            "Sprint 4 puede arrancar productivo con la política D20 aplicada.",
        )
    if global_d20_pct >= 30:
        return (
            "AMARILLO",
            "Hunter+D20 cubre 30-50%. Hunter es primario para los tiers "
            "cubiertos, pero hay que buscar adapter secundario (research IA + "
            "permutación email) para los tiers no cubiertos.",
        )
    return (
        "ROJO",
        "Hunter+D20 cubre <30%. Pivote a Opción C del plan §19 (research IA "
        "leyendo web pública del prospecto + permutación de patrones email + "
        "verificación con MillionVerifier). Hunter solo como complemento.",
    )


# ─── render markdown ───────────────────────────────────────────────────────
def render_md(
    rows: list[CompanyReanalysis],
    by_tier: dict[str, dict],
    glob: dict,
    veredicto_label: str,
    veredicto_text: str,
) -> str:
    L: list[str] = []
    L.append("# Frente E — Re-análisis Hunter con criterio D20")
    L.append("")
    L.append(
        "Re-procesa el output crudo de Frente C (Hunter, commit 3c5b7a9) "
        "aplicando el criterio dual D20 confirmado en sesión 2026-05-06. "
        "Cero llamadas adicionales a Hunter."
    )
    L.append("")
    L.append("## Hit rate decisor estricto vs Hit rate D20 — por tier")
    L.append("")
    L.append("| Tier | Empresas | Decisor estricto (Frente C) | Decisor + Nominal | **D20 completo** |")
    L.append("|---|---|---|---|---|")
    for t in ("T1", "T2", "T3", "T4"):
        d = by_tier[t]
        L.append(
            f"| {t} | {d['n']} | "
            f"{d['with_decisor_strict']}/{d['n']} = **{d['hit_rate_decisor_strict_pct']}%** | "
            f"{d['with_decisor_or_nominal']}/{d['n']} = {d['hit_rate_decisor_nominal_pct']}% | "
            f"{d['with_d20']}/{d['n']} = **{d['hit_rate_d20_pct']}%** |"
        )
    L.append(
        f"| **Global** | {glob['n']} | "
        f"**{glob['hit_rate_decisor_strict_pct']}%** | "
        f"{glob['hit_rate_decisor_nominal_pct']}% | "
        f"**{glob['hit_rate_d20_pct']}%** |"
    )
    L.append("")
    L.append(
        f"**Total emails brutos Hunter:** {glob['n_emails_brutos_total']}  ·  "
        f"**Aceptables D20:** {glob['n_emails_aceptables_total']}  ·  "
        f"**Falsos positivos C1 (T4):** {glob['n_falsos_positivos']}"
    )
    L.append("")

    L.append("## Detalle por empresa")
    L.append("")
    L.append("| Tier | NIF | Empresa | dec | nom | corp | desc | aceptables D20 | notas |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        notas = []
        if r.is_false_positive:
            notas.append(f"**FP C1** ({r.organization or '?'})")
        if r.n_emails_total == 0:
            notas.append("Hunter sin datos")
        nombre_corto = r.nombre[:40]
        L.append(
            f"| {r.tier} | `{r.nif}` | {nombre_corto} | "
            f"{r.n_decisor} | {r.n_nominal} | {r.n_corporativo_pequeno} | "
            f"{r.n_descartado} | **{r.n_aceptable_d20}** | "
            f"{' / '.join(notas) if notas else ''} |"
        )
    L.append("")

    L.append("## Detalle email-por-email con clasificación D20")
    L.append("")
    for r in rows:
        if r.n_emails_total == 0:
            continue
        L.append(f"### [{r.tier}] {r.nombre}")
        if r.is_false_positive:
            L.append(
                f"> ⚠️ Falso positivo C1 — Hunter resolvió `{r.domain_resolved}` "
                f"(organización `{r.organization}`) que NO es la empresa SABI. "
                f"Todos los emails se descartan en bloque."
            )
        L.append("")
        L.append("| email | cargo Hunter | nombre | conf | tipo D20 | aceptado | razón |")
        L.append("|---|---|---|---|---|---|---|")
        for d in r.detalle:
            cargo = (d["cargo"] or "—")[:50]
            nom = (d["nombre"] or "—")[:25]
            checkmark = "✓" if d["accepted"] else "✗"
            L.append(
                f"| `{d['email']}` | {cargo} | {nom} | {d['confidence']} | "
                f"`{d['email_type']}` | {checkmark} | {d['reason']} |"
            )
        L.append("")

    L.append("## Veredicto")
    L.append("")
    L.append(f"**{veredicto_label}**")
    L.append("")
    L.append(veredicto_text)
    L.append("")
    L.append("## Recomendación operacional")
    L.append("")
    L.append(
        "Política D20 aplicada al output de Hunter SOBRE el mismo sample de "
        "25 empresas SABI. Mismas empresas, mismo dataset, criterio nuevo. "
        "Sin créditos consumidos en este análisis."
    )
    return "\n".join(L) + "\n"


def main() -> int:
    if not INPUT_JSON.exists():
        print(f"ROJO: no existe {INPUT_JSON}. Frente C no escribió output o se borró.")
        return 2

    with INPUT_JSON.open(encoding="utf-8") as f:
        data = json.load(f)

    rows = reanalyze(data)
    by_tier = aggregate_by_tier(rows)
    glob = aggregate_global(rows)
    label, text = veredicto(glob["hit_rate_d20_pct"])

    md = render_md(rows, by_tier, glob, label, text)
    REPORT_MD.write_text(md, encoding="utf-8")

    # Stdout resumen
    SEP = "=" * 76
    print(SEP)
    print("Frente E — Re-análisis Hunter con criterio D20")
    print(SEP)
    print()
    print(f"{'Tier':<6} {'n':<4} {'Decisor estricto':<18} {'Dec+Nom':<10} {'D20 completo':<12}")
    print("-" * 60)
    for t in ("T1", "T2", "T3", "T4"):
        d = by_tier[t]
        print(
            f"{t:<6} {d['n']:<4} "
            f"{d['with_decisor_strict']}/{d['n']} = {d['hit_rate_decisor_strict_pct']:>5}%   "
            f"{d['with_decisor_or_nominal']}/{d['n']} = {d['hit_rate_decisor_nominal_pct']:>5}%   "
            f"{d['with_d20']}/{d['n']} = {d['hit_rate_d20_pct']:>5}%"
        )
    print("-" * 60)
    print(
        f"{'Global':<6} {glob['n']:<4} "
        f"{glob['hit_rate_decisor_strict_pct']:>20}%  "
        f"{glob['hit_rate_decisor_nominal_pct']:>9}%   "
        f"{glob['hit_rate_d20_pct']:>11}%"
    )
    print()
    print(f"Falsos positivos C1 (T4 fuzzy a empresa distinta): {glob['n_falsos_positivos']}")
    print(f"Emails aceptables D20 / brutos: {glob['n_emails_aceptables_total']} / {glob['n_emails_brutos_total']}")
    print()
    print(SEP)
    print(f"VEREDICTO: {label}")
    print(SEP)
    print(text)
    print()
    print(f"Reporte completo escrito en {REPORT_MD}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
