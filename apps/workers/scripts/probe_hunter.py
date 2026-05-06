"""apps/workers/scripts/probe_hunter.py

Validación experimental de Hunter.io como email finder primario para
DEMIN antes de comprometer Sprint 4 (decisión D17, plan §8.5 / §16).
Sondea 25 empresas SABI distribuidas por tier:

    - 5 T1 con web (rev_y0 1.000-5.000 k€)
    - 5 T2 con web (rev_y0 5.000-20.000 k€)
    - 5 T3 con web (rev_y0   500-1.000 k€)
    - 10 T4 sin web (rev_y0   500-20.000 k€)

Para T1-T3 invoca Hunter Domain Search por dominio extraído de la web
SABI. Para T4 invoca el mismo endpoint pasando `company=<nombre>`,
que resuelve fuzzy a un dominio canónico (lo más cercano a un
"company search" público de Hunter).

NO toca pipeline ni inserta en contacts. Lectura sólo de
`companies` en demin-prod por defecto (override `--read-env=dev`).

Salida en `apps/workers/scripts/probe_hunter_output/`:
    - results.json — resultado crudo por empresa + agregados
    - audit.md     — auditoría humana de 5 empresas (descripción
                     SABI + decisores Hunter + cargo)

Coste: 25 search credits del plan Free Hunter (50/mes disponibles).

Uso:
    cd apps/workers && uv run python scripts/probe_hunter.py
    uv run python scripts/probe_hunter.py --read-env dev    # fallback
    uv run python scripts/probe_hunter.py --dry-run         # sin Hunter
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import tldextract
from sqlalchemy import text

os.environ.setdefault("ENV", "dev")  # Hunter key vive en .env.dev

# Windows: fuerza stdout/stderr a UTF-8 para que los nombres SABI con
# tildes/eñes se rendericen sin UnicodeEncodeError contra cp1252.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

WORKERS_ROOT = Path(__file__).resolve().parent.parent
if str(WORKERS_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKERS_ROOT))

from shared.config import settings  # noqa: E402
from shared.db import get_session  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "probe_hunter_output"
RESULTS_JSON = OUTPUT_DIR / "results.json"
AUDIT_MD = OUTPUT_DIR / "audit.md"

# Selección reproducible: sembramos hashtext con esta sal cuando ordenamos
# candidatos por tier. Cambiar la sal SOLO si se quiere reseleccionar.
SELECTION_SEED = "demin-probe-hunter-2026-05-06"

# ─── filtros de cargo ───────────────────────────────────────────────────────
# Patrones que tras normalizar (minúsculas + sin acentos) marcan a un
# contacto como "decisor" para outreach DEMIN. Cubren constructora /
# reformista típica española + variantes inglesas que Hunter pueda
# devolver para empresas con presencia internacional.
CARGO_PATTERNS_RAW = [
    r"\bceo\b",
    r"\bcfo\b",
    r"\bcoo\b",
    r"\bcto\b",
    r"\bcio\b",
    r"director\s+general",
    r"director\s+ejecutivo",
    r"director\s+t[eé]cnico",
    r"director\s+de\s+operaciones",
    r"director\s+comercial",
    r"director\s+de\s+compras",
    r"director\s+financiero",
    r"\bgerente\b",
    r"jefe\s+de\s+obra",
    r"jefe\s+de\s+compras",
    r"jefe\s+de\s+operaciones",
    r"jefe\s+t[eé]cnico",
    r"responsable\s+de\s+compras",
    r"responsable\s+de\s+obras?",
    r"responsable\s+t[eé]cnico",
    r"\bmanager\b",
    r"general\s+manager",
    r"managing\s+director",
    r"\bpresidente\b",
    r"\bfundador\b",
    r"\bfounder\b",
    r"co-?founder",
    r"\bpropietario\b",
    r"\bowner\b",
    r"\bsocio\b",
    r"\badministrador\b",
    r"\bdirector\b",  # último recurso: cualquier "director X"
]
COMPILED_CARGO_PATTERNS = [re.compile(p) for p in CARGO_PATTERNS_RAW]

HUNTER_TIMEOUT_S = 30.0
HUNTER_PAUSE_S = 1.2  # plan free ~10 req/s pero con margen extra
HUNTER_LIMIT = 10     # plan Free limita a 10 emails por response (400 si pides más)


def _normalize(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def is_decisor(position: str | None) -> bool:
    if not position:
        return False
    norm = _normalize(position)
    return any(p.search(norm) for p in COMPILED_CARGO_PATTERNS)


def extract_domain(raw: str | None) -> str | None:
    """Extrae el dominio registrado (`example.com`) de un campo `web` SABI.

    Tolera valores tipo `https://www.example.com/path`, `www.example.com`,
    `example.com`, o ruido `Example Co — www.example.com`. Devuelve `None`
    si no encuentra dominio resoluble.
    """
    if not raw:
        return None
    raw = raw.strip()
    if not raw:
        return None
    # Si hay espacios, asumir que el dominio es el último token con punto.
    candidates = [raw, *raw.split()]
    for cand in candidates:
        c = cand.strip().strip("()[],;.")
        if not c:
            continue
        if "://" not in c:
            c = "http://" + c
        try:
            parsed = urlparse(c)
        except ValueError:
            continue
        host = parsed.netloc or parsed.path
        if not host or "." not in host:
            continue
        ext = tldextract.extract(host)
        if ext.domain and ext.suffix:
            return f"{ext.domain}.{ext.suffix}".lower()
    return None


# ─── selección de empresas ─────────────────────────────────────────────────
@dataclass
class Company:
    nif: str
    nombre: str
    localidad: str | None
    descripcion: str | None
    web: str | None
    rev_y0_keur: float | None
    tier: str

    @property
    def domain(self) -> str | None:
        return extract_domain(self.web)


def _diversify(rows: list[Company], k: int) -> list[Company]:
    """Toma `k` empresas intentando diversificar localidades.

    Greedy: por cada slot, elige primero localidades aún no vistas; si se
    agotan, repite las menos representadas. Determinista (depende del
    orden de entrada — nosotros lo fijamos vía hashtext + sal).
    """
    picked: list[Company] = []
    seen: dict[str, int] = {}
    for row in rows:
        loc = (row.localidad or "—").upper()
        if len(picked) < k and seen.get(loc, 0) == 0:
            picked.append(row)
            seen[loc] = 1
        if len(picked) >= k:
            break
    if len(picked) < k:
        # Rellenar con los siguientes evitando ya elegidos
        chosen_nifs = {c.nif for c in picked}
        for row in rows:
            if row.nif in chosen_nifs:
                continue
            picked.append(row)
            if len(picked) >= k:
                break
    return picked[:k]


def select_companies(env: str) -> list[Company]:
    """Selecciona 25 empresas (5/5/5/10) leyendo `companies` de `env`.

    Orden estable: `hashtext(nif || SEED)`. Diversificación greedy por
    localidad. Si alguna canasta no llega a 5/10, se rellena con los
    siguientes del orden estable.
    """
    selections: list[Company] = []

    queries = [
        ("T1", "tier='T1' and web is not null and rev_y0_keur between 1000 and 5000", 5),
        ("T2", "tier='T2' and web is not null and rev_y0_keur between 5000 and 20000", 5),
        ("T3", "tier='T3' and web is not null and rev_y0_keur between 500 and 1000", 5),
        ("T4", "tier='T4' and web is null     and rev_y0_keur between 500 and 20000", 10),
    ]

    with get_session(env) as s:
        for label, where, k in queries:
            sql = text(f"""
                select nif, nombre, localidad, descripcion, web,
                       rev_y0_keur, tier
                from companies
                where {where}
                order by hashtext(nif || :seed)
                limit 200
            """)
            rows = s.execute(sql, {"seed": SELECTION_SEED}).all()
            candidates = [
                Company(
                    nif=r.nif,
                    nombre=r.nombre,
                    localidad=r.localidad,
                    descripcion=r.descripcion,
                    web=r.web,
                    rev_y0_keur=float(r.rev_y0_keur) if r.rev_y0_keur is not None else None,
                    tier=r.tier,
                )
                for r in rows
            ]
            if not candidates:
                raise RuntimeError(
                    f"selección vacía para {label} en env={env} con filtro: {where}"
                )
            picked = _diversify(candidates, k)
            if len(picked) < k:
                raise RuntimeError(
                    f"sólo {len(picked)} candidatos disponibles para {label} en env={env}"
                )
            selections.extend(picked)

    return selections


# ─── llamadas a Hunter ──────────────────────────────────────────────────────
@dataclass
class Decisor:
    nombre: str | None
    cargo: str | None
    email: str
    confidence: int | None
    seniority: str | None
    department: str | None


@dataclass
class ProbeResult:
    nif: str
    nombre: str
    tier: str
    localidad: str | None
    descripcion: str | None
    domain_input: str | None       # dominio derivado de SABI.web (None si T4)
    domain_resolved: str | None    # dominio que Hunter dice tener
    organization: str | None       # nombre que Hunter atribuye al dominio
    n_emails_total: int            # total de emails devueltos por Hunter
    n_decisores: int               # tras filtro de cargo
    decisores: list[Decisor] = field(default_factory=list)
    other_emails: list[Decisor] = field(default_factory=list)  # los descartados
    avg_confidence_decisores: float | None = None
    latency_ms: int | None = None
    http_status: int | None = None
    error: str | None = None
    used_credit: bool = False


def _to_decisor(item: dict[str, Any]) -> Decisor:
    first = item.get("first_name") or ""
    last = item.get("last_name") or ""
    name = (first + " " + last).strip() or None
    return Decisor(
        nombre=name,
        cargo=item.get("position"),
        email=item.get("value", ""),
        confidence=item.get("confidence"),
        seniority=item.get("seniority"),
        department=item.get("department"),
    )


def hunter_domain_search(
    client: httpx.Client,
    *,
    domain: str | None = None,
    company: str | None = None,
) -> tuple[int, dict[str, Any], int]:
    """Llama Hunter Domain Search. Devuelve (status_code, json, latency_ms).

    Pasa `domain` o `company` (uno de los dos). `domain` tiene precedencia
    si ambos vienen.
    """
    assert domain or company, "necesario domain o company"
    api_key = settings.HUNTER_API_KEY
    if not api_key:
        raise RuntimeError(
            "HUNTER_API_KEY no está en .env.dev. Reasentar antes de ejecutar."
        )
    base = settings.HUNTER_BASE_URL.rstrip("/")
    params: dict[str, Any] = {
        "api_key": api_key,
        "limit": HUNTER_LIMIT,
    }
    if domain:
        params["domain"] = domain
    elif company:
        params["company"] = company

    started = time.monotonic()
    try:
        r = client.get(f"{base}/domain-search", params=params, timeout=HUNTER_TIMEOUT_S)
    except httpx.HTTPError as e:
        elapsed = int((time.monotonic() - started) * 1000)
        return -1, {"error": f"httpx: {e!r}"}, elapsed
    elapsed = int((time.monotonic() - started) * 1000)
    try:
        body = r.json()
    except Exception:
        body = {"error": "no-json", "raw": r.text[:300]}
    return r.status_code, body, elapsed


def probe_one(client: httpx.Client, c: Company) -> ProbeResult:
    domain = c.domain
    res = ProbeResult(
        nif=c.nif,
        nombre=c.nombre,
        tier=c.tier,
        localidad=c.localidad,
        descripcion=c.descripcion,
        domain_input=domain,
        domain_resolved=None,
        organization=None,
        n_emails_total=0,
        n_decisores=0,
    )

    if domain:
        status, body, elapsed = hunter_domain_search(client, domain=domain)
    else:
        # T4 sin web: dejamos que Hunter resuelva por nombre.
        status, body, elapsed = hunter_domain_search(client, company=c.nombre)

    res.latency_ms = elapsed
    res.http_status = status

    if status == 401:
        res.error = "401 unauthorized — api key inválida"
        return res
    if status == 429:
        res.error = "429 rate limit"
        return res
    if status == 400:
        # Hunter devuelve 400 si no consigue resolver `company` a un dominio
        details = body.get("errors") or body.get("error") or body
        res.error = f"400 — {json.dumps(details, ensure_ascii=False)[:200]}"
        res.used_credit = False
        return res
    if status != 200:
        res.error = f"http {status} — {json.dumps(body, ensure_ascii=False)[:200]}"
        return res

    res.used_credit = True

    data = body.get("data") or {}
    res.domain_resolved = data.get("domain")
    res.organization = data.get("organization")
    emails = data.get("emails") or []
    res.n_emails_total = len(emails)

    decisores: list[Decisor] = []
    others: list[Decisor] = []
    for item in emails:
        d = _to_decisor(item)
        if is_decisor(d.cargo):
            decisores.append(d)
        else:
            others.append(d)
    res.decisores = decisores
    res.other_emails = others
    res.n_decisores = len(decisores)
    if decisores:
        confs = [d.confidence for d in decisores if d.confidence is not None]
        if confs:
            res.avg_confidence_decisores = round(sum(confs) / len(confs), 1)
    return res


# ─── agregados ──────────────────────────────────────────────────────────────
def aggregate(results: list[ProbeResult]) -> dict[str, Any]:
    by_tier: dict[str, dict[str, Any]] = {}
    for tier in ("T1", "T2", "T3", "T4"):
        rs = [r for r in results if r.tier == tier]
        n = len(rs)
        ok = [r for r in rs if r.error is None]
        with_decisor = [r for r in ok if r.n_decisores > 0]
        latencias = [r.latency_ms for r in rs if r.latency_ms]
        all_emails = [r.n_emails_total for r in ok]
        confs_t = [
            d.confidence
            for r in ok
            for d in r.decisores
            if d.confidence is not None
        ]
        by_tier[tier] = {
            "n_empresas": n,
            "n_sin_error": len(ok),
            "n_con_decisor": len(with_decisor),
            "hit_rate_pct": round(100 * len(with_decisor) / n, 1) if n else 0.0,
            "n_emails_total_avg": round(sum(all_emails) / len(all_emails), 1) if all_emails else 0.0,
            "n_decisores_avg": round(
                sum(r.n_decisores for r in ok) / len(ok), 2
            ) if ok else 0.0,
            "latency_ms_avg": int(sum(latencias) / len(latencias)) if latencias else None,
            "avg_confidence_decisores": (
                round(sum(confs_t) / len(confs_t), 1) if confs_t else None
            ),
        }

    # global
    n = len(results)
    with_d = [r for r in results if r.n_decisores > 0]
    latencias = [r.latency_ms for r in results if r.latency_ms]
    all_decisor_confs = [
        d.confidence
        for r in results
        for d in r.decisores
        if d.confidence is not None
    ]
    cargo_counter: dict[str, int] = {}
    for r in results:
        for d in r.decisores:
            key = (d.cargo or "—").strip()
            cargo_counter[key] = cargo_counter.get(key, 0) + 1
    cargos_top = sorted(cargo_counter.items(), key=lambda kv: kv[1], reverse=True)

    return {
        "n_empresas": n,
        "hit_rate_global_pct": round(100 * len(with_d) / n, 1) if n else 0.0,
        "latency_ms_avg": int(sum(latencias) / len(latencias)) if latencias else None,
        "avg_confidence_decisores": (
            round(sum(all_decisor_confs) / len(all_decisor_confs), 1)
            if all_decisor_confs
            else None
        ),
        "by_tier": by_tier,
        "distribucion_cargos": cargos_top,
        "credits_used_estimated": sum(1 for r in results if r.used_credit),
    }


# ─── auditoría humana ───────────────────────────────────────────────────────
def pick_audit_sample(results: list[ProbeResult], k: int = 5) -> list[ProbeResult]:
    """Mezcla buenos y malos resultados:
        - 2 con más decisores (mejor caso)
        - 2 con 0 emails o error (peor caso)
        - 1 con resultado intermedio (1-2 emails)
    """
    by_n = sorted(results, key=lambda r: r.n_decisores, reverse=True)
    best = by_n[:2]
    worst = [r for r in results if r.n_emails_total == 0 or r.error][:2]
    chosen = {r.nif for r in best + worst}
    middle = [
        r for r in results
        if r.nif not in chosen and 1 <= r.n_emails_total <= 4
    ]
    middle = middle[:1]
    sample = best + worst + middle
    # rellena si faltan
    if len(sample) < k:
        for r in results:
            if r.nif not in {x.nif for x in sample}:
                sample.append(r)
                if len(sample) >= k:
                    break
    return sample[:k]


def render_audit_md(audit: list[ProbeResult]) -> str:
    lines: list[str] = []
    lines.append("# Auditoría humana — probe_hunter\n")
    lines.append(
        "Selección de empresas con resultados dispares para evaluar a "
        "ojo si Hunter devuelve decisores útiles para escribir prospección.\n"
    )
    for i, r in enumerate(audit, 1):
        lines.append(f"## {i}. {r.nombre}  ({r.tier})")
        lines.append("")
        lines.append(f"- **NIF:** `{r.nif}`")
        lines.append(f"- **Localidad:** {r.localidad or '—'}")
        lines.append(f"- **Web (SABI):** {r.domain_input or 'sin web'}")
        lines.append(f"- **Dominio resuelto por Hunter:** {r.domain_resolved or '—'}")
        lines.append(f"- **Organización Hunter:** {r.organization or '—'}")
        lines.append(f"- **Emails totales devueltos:** {r.n_emails_total}")
        lines.append(f"- **Decisores tras filtro:** {r.n_decisores}")
        lines.append(f"- **Latencia:** {r.latency_ms} ms")
        if r.error:
            lines.append(f"- **Error:** `{r.error}`")
        lines.append("")
        lines.append("**Descripción SABI:**")
        lines.append("")
        desc = (r.descripcion or "—").strip()
        # quote
        for line in desc.splitlines():
            lines.append(f"> {line}")
        lines.append("")
        if r.decisores:
            lines.append("**Decisores Hunter:**")
            lines.append("")
            for d in r.decisores:
                lines.append(
                    f"- `{d.email}` — {d.nombre or '—'} — "
                    f"{d.cargo or '—'} — confidence={d.confidence}"
                )
            lines.append("")
        if r.other_emails:
            lines.append("**Otros emails (descartados por filtro de cargo):**")
            lines.append("")
            for d in r.other_emails:
                lines.append(
                    f"- `{d.email}` — {d.nombre or '—'} — "
                    f"{d.cargo or '—'} — confidence={d.confidence}"
                )
            lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


# ─── runner ─────────────────────────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description="Validación experimental Hunter D17")
    parser.add_argument(
        "--read-env", default="prod", choices=["dev", "prod"],
        help="entorno desde el que leer companies (default prod, lectura sólo)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="no llama a Hunter; sólo selecciona y muestra (debug)",
    )
    args = parser.parse_args()

    print(f"=== probe_hunter — read_env={args.read_env}  dry_run={args.dry_run} ===\n")

    if not settings.HUNTER_API_KEY and not args.dry_run:
        print("ROJO: HUNTER_API_KEY no está en .env.dev")
        return 2

    print(f"[1] Selección de 25 empresas desde demin-{args.read_env}")
    companies = select_companies(args.read_env)
    for c in companies:
        loc = (c.localidad or "—")[:25]
        rev = f"{c.rev_y0_keur:>7.0f}" if c.rev_y0_keur else "    n/a"
        dom = c.domain or "(sin dominio)"
        print(f"   {c.tier} {c.nif:<11} rev={rev}  loc={loc:<25}  {c.nombre[:40]:<40}  {dom}")
    print()

    if args.dry_run:
        print("dry-run -> fin sin llamadas a Hunter")
        return 0

    print(f"[2] Hunter Domain Search × {len(companies)} (free plan, 1 credit c/u)\n")
    results: list[ProbeResult] = []
    with httpx.Client() as client:
        for i, c in enumerate(companies, 1):
            res = probe_one(client, c)
            results.append(res)
            tag = "OK" if res.error is None else "ERR"
            print(
                f"   [{i:>2}/{len(companies)}] {tag} {res.tier} {res.nif:<11} "
                f"emails={res.n_emails_total:>2} decisores={res.n_decisores:>2} "
                f"lat={res.latency_ms or 0:>4}ms  {res.nombre[:40]}"
            )
            if res.error:
                print(f"        error: {res.error[:140]}")
            # parada temprana si la primera llamada da 401/429
            if i == 1 and res.http_status in (401, 429):
                print(f"PARADA — primera llamada {res.http_status}; aborta")
                break
            time.sleep(HUNTER_PAUSE_S)
    print()

    print("[3] Agregados")
    agg = aggregate(results)
    print(json.dumps(agg, indent=2, ensure_ascii=False))
    print()

    print("[4] Persistencia")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "metadata": {
            "read_env": args.read_env,
            "selection_seed": SELECTION_SEED,
            "n_companies": len(companies),
            "ts_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "aggregate": agg,
        "results": [asdict(r) for r in results],
    }
    RESULTS_JSON.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"   results -> {RESULTS_JSON}")

    audit_sample = pick_audit_sample(results, k=5)
    AUDIT_MD.write_text(render_audit_md(audit_sample), encoding="utf-8")
    print(f"   audit   -> {AUDIT_MD}")

    print()
    print("=== FIN ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
