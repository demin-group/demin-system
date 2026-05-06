"""research_prospect.py — Sprint 4 paso 4b (D21).

Función dual sobre `companies` con `ia_fit='fit'` y `web` disponible:

1. **Dossier de personalización** (D10 original) — alimenta el prompt de
   redacción §10.2 (paso 5).
2. **`personas_extraidas`** (D21) — `find_contacts.py` (paso 4) la consume
   para reclasificar T2 nominal-sin-cargo a nominal-con-cargo (§8.5 paso 3).

Pipeline por empresa:
  1. Resolver URL base con `tldextract` + scheme (https → http fallback).
  2. Scrapear home + 9 subpaths de §8.4 (`/contacto`, `/servicios`,
     `/proyectos`, `/sobre-nosotros`, `/equipo`, `/team`, `/about`,
     `/quienes-somos`). Si los primeros 4 dan 404, abortar restantes.
  3. Extraer texto de cada HTML con `selectolax` (elimina script/style/nav/
     footer/header). Concatenar con `--- <url> ---` como separador.
  4. Truncar a 32k chars (≈ 8k tokens, límite §8.4).
  5. Llamar Claude Sonnet 4.6 vía `call_llm(task='research_prospect')`.
  6. Validar JSON tolerantemente (campos opcionales rellenan default).
  7. UPDATE companies SET research_data, research_done_at = now().

Idempotencia: skipea companies con `research_done_at IS NOT NULL` salvo
`--rerun` (re-procesa todo) o `--retry-failed` (solo las que tienen
`_failed` en research_data — recurso quirúrgico para no quemar el universo
entero recuperando 8-15 fallos esperados de scraping ruidoso).

Cap defensivo `--max-cost-usd 5.0` (estima $0.005/empresa, ~$0.56 para
T3+T2 = 112 empresas, margen 9×).

Playwright fallback queda fuera de v1: si una web es SPA con HTML <500
chars, el worker marca `_warning='thin_html_possibly_spa'` pero no aborta.
Re-evaluar añadir playwright si >20% de empresas caen en ese estado.

CLI:
    cd apps/workers
    uv run python -m pipeline.research_prospect --env dev --tier T3 --limit 5
    uv run python -m pipeline.research_prospect --env prod --tier T2 --max-cost-usd 1.5
    uv run python -m pipeline.research_prospect --env dev --tier T2 --rerun
    uv run python -m pipeline.research_prospect --env prod --tier T2 --retry-failed
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from urllib.parse import urljoin

import httpx
import tldextract
from selectolax.parser import HTMLParser
from sqlalchemy import text

EnvName = Literal["dev", "prod"]
Tier = Literal["T1", "T2", "T3", "T4"]

WORKERS_DIR = Path(__file__).resolve().parent.parent
PROMPT_PATH = WORKERS_DIR / "shared" / "prompts" / "research_prospect.md"

# Subpaths a probar tras la home (§8.4). Primeros 4 son los más estables;
# si los 4 dan 404, asumimos que la web no usa esos paths estándar y
# abortamos los restantes para no malgastar requests.
_SUBPATHS: tuple[str, ...] = (
    "/contacto",
    "/servicios",
    "/proyectos",
    "/sobre-nosotros",
    "/equipo",
    "/team",
    "/about",
    "/quienes-somos",
)
_MAX_CONSECUTIVE_FAILS = 4

_HTTP_TIMEOUT_S = 8.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
}

_MAX_TEXT_CHARS = 32_000
"""Truncado heurístico a ~8k tokens (4 chars/token) — límite §8.4."""

_THIN_HTML_THRESHOLD = 500
"""Bytes de texto extraído por debajo del cual marcamos `_warning` SPA."""

USD_COST_CAP = 5.0
"""Cap por defecto del run completo. Plan §8.4 estima ~$0.005/empresa
(Sonnet 4.6 con prompt ~8k tokens input + ~500 output). 112 empresas
T3+T2 ≈ $0.56 → cap 5.0 da 9× margen."""

# Pricing local fallback (Sonnet 4.6 cifras aproximadas Anthropic 2026).
# Igual que `classify_descr.py`, NO se rellena `shared/llm.PRICING_USD_PER_MTOKENS`
# para no contaminar el log oficial mientras esa tabla esté vacía.
_SONNET_FALLBACK_USD_PER_MTOK = {"input": 3.0, "output": 15.0}

logger = logging.getLogger("demin.research_prospect")
if not logger.handlers:
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

_VALID_TAMANO = frozenset({"muy_pequeno", "pequeno", "mediano", "grande", "incierto"})
_VALID_TIPO_OBRA = frozenset({
    "residencial", "comercial", "industrial",
    "obra_nueva", "reforma", "rehabilitacion",
})
_VALID_LENGUAJE = frozenset({"tecnico", "cercano", "corporativo", "familiar"})


# ─── Dataclasses ───────────────────────────────────────────────────────────


@dataclass(slots=True)
class Pending:
    id: str
    nif: str
    nombre: str
    web: str


@dataclass(slots=True)
class ScrapeOutcome:
    """Resultado del scraping de una empresa.

    `pages` = {url: html_text}. Vacío si home falló.
    `failure` = razón estructurada si home falló (None si home OK).
    `thin_html` = True si home OK pero <500 chars de texto extraído (SPA?).
    """

    pages: dict[str, str]
    failure: str | None
    thin_html: bool


@dataclass(slots=True)
class Result:
    nif: str
    company_id: str
    research_data: dict[str, Any]
    tokens_in: int
    tokens_out: int
    failed: bool  # True si research_data tiene clave `_failed`


# ─── Funciones puras (testables sin red ni LLM) ────────────────────────────


def resolve_base_url(web: str | None) -> str | None:
    """Devuelve la URL canónica `https://<dominio_registrable>` o None.

    `tldextract` extrae el dominio registrable; ignoramos subdominios para
    estabilizar el target (acme.es es siempre `https://acme.es`, sin `www.`,
    sin path). Si la web no es parseable, devuelve None — la empresa queda
    sin research.
    """
    if not web or not web.strip():
        return None
    ext = tldextract.extract(web.strip())
    if not ext.domain or not ext.suffix:
        return None
    return f"https://{ext.domain}.{ext.suffix}".lower()


def extract_text_from_html(html: str) -> str:
    """Convierte HTML a texto plano legible.

    Elimina `<script>`, `<style>`, `<noscript>`, `<nav>`, `<footer>`,
    `<header>` (los menús útiles ya los cogeremos vía /equipo /sobre-nosotros).
    Devuelve texto con saltos de línea preservados pero whitespace normalizado.
    """
    if not html or not html.strip():
        return ""
    try:
        tree = HTMLParser(html)
    except Exception:
        return ""
    for sel in ("script", "style", "noscript", "nav", "footer", "header"):
        for node in tree.css(sel):
            node.decompose()
    body = tree.body
    if body is None:
        return ""
    raw = body.text(separator="\n", strip=False)
    # Colapsar runs de espacios horizontales y limpiar líneas vacías múltiples.
    lines: list[str] = []
    for line in raw.splitlines():
        clean = " ".join(line.split())
        if clean:
            lines.append(clean)
    return "\n".join(lines)


def truncate_to_budget(text: str, max_chars: int = _MAX_TEXT_CHARS) -> str:
    """Trunca preservando palabras enteras hasta el límite, añade marcador."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "\n\n[... truncado por longitud ...]"


def compose_pages_text(pages: dict[str, str]) -> str:
    """Concatena el texto de las páginas con `--- <url> ---` como cabecera
    de cada bloque. La cabecera es un anchor que el LLM usa para rellenar
    `personas_extraidas[].fuente_url`."""
    parts: list[str] = []
    for url, html in pages.items():
        text_extracted = extract_text_from_html(html)
        if not text_extracted:
            continue
        parts.append(f"--- {url} ---\n{text_extracted}")
    return "\n\n".join(parts)


def _strip_codefences(s: str) -> str:
    s = s.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
        if s.endswith("```"):
            s = s[:-3]
    return s.strip()


def _coerce_str_list(value: Any, max_items: int | None = None) -> list[str]:
    """Limpia value a lista de strings no vacíos."""
    if not isinstance(value, list):
        return []
    out = [v.strip() for v in value if isinstance(v, str) and v.strip()]
    if max_items is not None:
        out = out[:max_items]
    return out


def clean_personas_extraidas(value: Any) -> list[dict[str, str]]:
    """Filtra entradas no conformes. Cada item válido tiene `nombre` (no
    vacío) + `cargo_si_aparece` (str, puede estar vacío) + `fuente_url`
    (str, puede estar vacío). Mismas garantías que asume
    `enrich_with_personas_extraidas` en find_contacts.py."""
    if not isinstance(value, list):
        return []
    out: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, dict):
            continue
        nombre = entry.get("nombre")
        if not isinstance(nombre, str) or not nombre.strip():
            continue
        cargo = entry.get("cargo_si_aparece", "")
        cargo = cargo if isinstance(cargo, str) else ""
        fuente = entry.get("fuente_url", "")
        fuente = fuente if isinstance(fuente, str) else ""
        out.append({
            "nombre": nombre.strip(),
            "cargo_si_aparece": cargo.strip(),
            "fuente_url": fuente.strip(),
        })
    return out


def parse_research_json(raw: str) -> dict[str, Any]:
    """Parse + validación tolerante. Si `raw` no parsea o no es dict,
    levanta ValueError. Si parsea pero le faltan campos, los rellena con
    defaults vacíos. Filtros tier/lenguaje aceptan solo valores conocidos
    (incierto/vacío en otro caso)."""
    cleaned = _strip_codefences(raw)
    data = json.loads(cleaned)
    if not isinstance(data, dict):
        raise ValueError(f"JSON no es objeto: {type(data).__name__}")

    tamano = data.get("tamano_aparente")
    if not isinstance(tamano, str) or tamano not in _VALID_TAMANO:
        tamano = "incierto"

    tipo_obra_raw = data.get("tipo_obra_que_hacen")
    tipo_obra: list[str]
    if isinstance(tipo_obra_raw, list):
        tipo_obra = [t for t in tipo_obra_raw if isinstance(t, str) and t in _VALID_TIPO_OBRA]
    else:
        tipo_obra = []

    lenguaje = data.get("lenguaje_que_usan")
    if not isinstance(lenguaje, str) or lenguaje not in _VALID_LENGUAJE:
        lenguaje = ""

    tipo_actividad = data.get("tipo_actividad_concreta")
    tipo_actividad = tipo_actividad.strip() if isinstance(tipo_actividad, str) else ""

    noticias = data.get("noticias_o_novedades")
    noticias = noticias.strip() if isinstance(noticias, str) else ""

    return {
        "tipo_actividad_concreta": tipo_actividad,
        "tamano_aparente": tamano,
        "tipo_obra_que_hacen": tipo_obra,
        "proyectos_recientes": _coerce_str_list(data.get("proyectos_recientes"), max_items=3),
        "noticias_o_novedades": noticias,
        "lenguaje_que_usan": lenguaje,
        "valores_que_destacan": _coerce_str_list(data.get("valores_que_destacan"), max_items=4),
        "hooks_de_personalizacion": _coerce_str_list(data.get("hooks_de_personalizacion")),
        "personas_extraidas": clean_personas_extraidas(data.get("personas_extraidas")),
    }


def _load_prompt() -> tuple[str, str]:
    """Lee `research_prospect.md` y separa en (system, user_template). Misma
    convención que `classify_descr.py`."""
    raw = PROMPT_PATH.read_text(encoding="utf-8")
    parts = raw.split("## System", 1)
    if len(parts) != 2:
        raise RuntimeError(f"Prompt {PROMPT_PATH.name} no contiene '## System'")
    after_system = parts[1]
    sys_user = after_system.split("## User template", 1)
    if len(sys_user) != 2:
        raise RuntimeError(f"Prompt {PROMPT_PATH.name} no contiene '## User template'")
    return sys_user[0].strip(), sys_user[1].strip()


# ─── Scraping (red, sin LLM, sin BD) ───────────────────────────────────────


def scrape_company_web(
    base_url: str,
    client: httpx.Client,
    *,
    subpaths: tuple[str, ...] = _SUBPATHS,
    max_consecutive_fails: int = _MAX_CONSECUTIVE_FAILS,
) -> ScrapeOutcome:
    """Scrapea home + subpaths. Si home falla por red/4xx-5xx → ScrapeOutcome
    con failure rellenado. Si home OK, sigue con subpaths hasta toparse con
    `max_consecutive_fails` 404 seguidos.

    Si la URL https:// falla con SSL/conexión, intenta http://.
    """
    pages: dict[str, str] = {}
    home_url = base_url
    home_resp, home_err = _fetch(home_url, client)

    if home_resp is None:
        # Probar fallback http:// si la base era https://
        if home_url.startswith("https://"):
            alt = "http://" + home_url[len("https://"):]
            home_url = alt
            home_resp, home_err = _fetch(home_url, client)

    if home_resp is None:
        return ScrapeOutcome(pages={}, failure=f"home_unreachable: {home_err}", thin_html=False)
    if home_resp.status_code >= 400:
        return ScrapeOutcome(
            pages={},
            failure=f"home_http_{home_resp.status_code}",
            thin_html=False,
        )

    pages[home_url] = home_resp.text
    home_text_len = len(extract_text_from_html(home_resp.text))
    thin = home_text_len < _THIN_HTML_THRESHOLD

    consecutive_fails = 0
    for path in subpaths:
        if consecutive_fails >= max_consecutive_fails:
            logger.debug("aborting subpaths after %d consecutive fails", consecutive_fails)
            break
        url = urljoin(home_url + "/", path.lstrip("/"))
        resp, _ = _fetch(url, client)
        if resp is None or resp.status_code >= 400:
            consecutive_fails += 1
            continue
        consecutive_fails = 0
        pages[url] = resp.text

    return ScrapeOutcome(pages=pages, failure=None, thin_html=thin)


def _fetch(url: str, client: httpx.Client) -> tuple[httpx.Response | None, str | None]:
    """Devuelve (response, None) si llegó respuesta HTTP (incluso 4xx/5xx),
    o (None, error_str) si falló la conexión/timeout/SSL."""
    try:
        r = client.get(url, headers=_HEADERS, follow_redirects=True)
        return r, None
    except httpx.TimeoutException:
        return None, "timeout"
    except httpx.ConnectError as e:
        return None, f"connect_error: {str(e)[:80]}"
    except httpx.HTTPError as e:
        return None, f"http_error: {type(e).__name__}: {str(e)[:80]}"


# ─── Procesamiento por empresa (red + LLM, sin BD) ─────────────────────────


def process_one(
    item: Pending,
    client: httpx.Client,
    system: str,
    user_template: str,
) -> Result:
    """Scrapea + llama LLM. Captura cualquier excepción y devuelve un Result
    con `_failed` rellenado en research_data. Nunca lanza."""
    base = resolve_base_url(item.web)
    if base is None:
        return Result(
            nif=item.nif,
            company_id=item.id,
            research_data={"_failed": "invalid_web", "raw_web": item.web or ""},
            tokens_in=0,
            tokens_out=0,
            failed=True,
        )

    outcome = scrape_company_web(base, client)
    if outcome.failure:
        return Result(
            nif=item.nif,
            company_id=item.id,
            research_data={"_failed": "scraping_failed", "reason": outcome.failure, "base_url": base},
            tokens_in=0,
            tokens_out=0,
            failed=True,
        )

    pages_text = compose_pages_text(outcome.pages)
    if not pages_text.strip():
        return Result(
            nif=item.nif,
            company_id=item.id,
            research_data={
                "_failed": "empty_text",
                "reason": "html parseado pero sin texto extraíble",
                "base_url": base,
            },
            tokens_in=0,
            tokens_out=0,
            failed=True,
        )

    user = user_template.replace("{nombre}", item.nombre).replace(
        "{texto_web}", truncate_to_budget(pages_text)
    )

    from shared.llm import call_llm  # noqa: PLC0415

    try:
        text_out, meta = call_llm(
            task="research_prospect",
            system=system,
            user=user,
            max_tokens=2000,
            response_format="text",  # parseamos tolerante a code fences
        )
    except Exception as e:
        return Result(
            nif=item.nif,
            company_id=item.id,
            research_data={
                "_failed": "llm_error",
                "reason": f"{type(e).__name__}: {str(e)[:150]}",
                "base_url": base,
            },
            tokens_in=0,
            tokens_out=0,
            failed=True,
        )

    try:
        validated = parse_research_json(text_out)
    except (json.JSONDecodeError, ValueError) as e:
        return Result(
            nif=item.nif,
            company_id=item.id,
            research_data={
                "_failed": "json_parse",
                "reason": f"{type(e).__name__}: {str(e)[:150]}",
                "raw_excerpt": text_out[:500],
                "base_url": base,
            },
            tokens_in=meta["tokens_in"],
            tokens_out=meta["tokens_out"],
            failed=True,
        )

    # Anotamos thin_html como pista para análisis posterior si el research
    # quedó pobre. NO marca como _failed — el LLM puede haber sacado señal útil.
    if outcome.thin_html:
        validated["_warning"] = "thin_html_possibly_spa"
    validated["_meta"] = {
        "base_url": base,
        "n_pages_scraped": len(outcome.pages),
    }

    return Result(
        nif=item.nif,
        company_id=item.id,
        research_data=validated,
        tokens_in=meta["tokens_in"],
        tokens_out=meta["tokens_out"],
        failed=False,
    )


# ─── Acceso a BD ───────────────────────────────────────────────────────────


def fetch_pending(
    env: EnvName,
    tier: Tier,
    limit: int | None,
    rerun: bool,
    retry_failed: bool,
) -> list[Pending]:
    """Trae companies con `ia_fit='fit'`, tier solicitado, web no vacío.

    Modos:
        - default: research_done_at IS NULL (idempotencia).
        - --rerun: ignora research_done_at (re-procesa todo el universo).
        - --retry-failed: solo las que tienen `_failed` en research_data.
    """
    from shared.db import get_session  # noqa: PLC0415

    sql = """
        SELECT c.id, c.nif, c.nombre, c.web
        FROM companies c
        WHERE c.ia_fit = 'fit'
          AND c.tier = :tier
          AND c.web IS NOT NULL
          AND length(trim(c.web)) > 0
    """
    if retry_failed:
        sql += " AND c.research_data ? '_failed'"
    elif not rerun:
        sql += " AND c.research_done_at IS NULL"
    sql += " ORDER BY c.nif"
    if limit is not None:
        sql += f" LIMIT {int(limit)}"

    with get_session(env) as s:
        rows = s.execute(text(sql), {"tier": tier}).all()
    return [Pending(id=str(r[0]), nif=r[1], nombre=r[2], web=r[3]) for r in rows]


_UPDATE_SQL = text(
    """
    UPDATE companies
    SET research_data = CAST(:rd AS jsonb),
        research_done_at = now()
    WHERE id = CAST(:id AS uuid)
    """
)


def write_result(env: EnvName, result: Result) -> None:
    from shared.db import get_session  # noqa: PLC0415

    with get_session(env) as s:
        s.execute(
            _UPDATE_SQL,
            {"id": result.company_id, "rd": json.dumps(result.research_data, ensure_ascii=False)},
        )


# ─── Orquestación CLI ──────────────────────────────────────────────────────


def _estimate_cost_usd(tokens_in: int, tokens_out: int) -> float:
    return (
        tokens_in * _SONNET_FALLBACK_USD_PER_MTOK["input"]
        + tokens_out * _SONNET_FALLBACK_USD_PER_MTOK["output"]
    ) / 1_000_000.0


def _pct(n: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="research_prospect — dossier dual + personas_extraidas (Sprint 4 paso 4b)"
    )
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--tier", choices=("T1", "T2", "T3", "T4"), required=True)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--workers", type=int, default=2,
                   help="Threads paralelos (default 2 — Sprint 3 calibró que 8 saturó Anthropic).")
    p.add_argument("--max-cost-usd", type=float, default=USD_COST_CAP)
    grp = p.add_mutually_exclusive_group()
    grp.add_argument("--rerun", action="store_true",
                     help="Ignora research_done_at — re-procesa todo el universo del tier.")
    grp.add_argument("--retry-failed", action="store_true",
                     help="Solo re-procesa las que tienen _failed en research_data.")
    args = p.parse_args(argv)
    env: EnvName = args.env
    tier: Tier = args.tier

    print("=" * 76)
    print(
        f"research_prospect  env={env}  tier={tier}  limit={args.limit}  "
        f"workers={args.workers}  max_cost_usd={args.max_cost_usd}  "
        f"rerun={args.rerun}  retry_failed={args.retry_failed}"
    )
    print("=" * 76)

    system, user_template = _load_prompt()
    print(f"[prompt] cargado de {PROMPT_PATH.name}: "
          f"system={len(system)} chars, user_template={len(user_template)} chars")

    pending = fetch_pending(env, tier, args.limit, args.rerun, args.retry_failed)
    if not pending:
        print("No hay empresas pendientes. Nada que hacer.")
        return 0
    print(f"[fetch] {len(pending)} empresas a procesar")

    counts = {"ok": 0, "failed": 0}
    failure_breakdown: dict[str, int] = {}
    personas_total = 0
    thin_html = 0
    total_tok_in = 0
    total_tok_out = 0
    cost_alarm = False

    t0 = time.monotonic()
    lock = Lock()

    def _record(r: Result) -> None:
        nonlocal personas_total, thin_html, total_tok_in, total_tok_out, cost_alarm
        with lock:
            total_tok_in += r.tokens_in
            total_tok_out += r.tokens_out
            if r.failed:
                counts["failed"] += 1
                reason = r.research_data.get("_failed", "unknown")
                failure_breakdown[reason] = failure_breakdown.get(reason, 0) + 1
            else:
                counts["ok"] += 1
                personas_total += len(r.research_data.get("personas_extraidas", []))
                if r.research_data.get("_warning") == "thin_html_possibly_spa":
                    thin_html += 1
            try:
                write_result(env, r)
            except Exception as e:
                logger.exception("write_result failed nif=%s: %s", r.nif, e)

            cost = _estimate_cost_usd(total_tok_in, total_tok_out)
            done = counts["ok"] + counts["failed"]
            if done % 5 == 0 or done == len(pending):
                print(
                    f"  [{done:>3}/{len(pending)}]  ok={counts['ok']:>3}  "
                    f"failed={counts['failed']:>3}  "
                    f"personas={personas_total:>3}  thin_html={thin_html:>2}  "
                    f"tok={total_tok_in}+{total_tok_out}  est_usd={cost:.3f}"
                )
            if cost > args.max_cost_usd and not cost_alarm:
                cost_alarm = True
                print(f"PARADA: coste {cost:.2f} USD supera cap {args.max_cost_usd} USD")

    print(f"[run] {args.workers} threads, prompt cargado")
    print()

    # Cliente httpx compartido entre workers — es thread-safe en httpx>=0.27.
    with httpx.Client(timeout=_HTTP_TIMEOUT_S, follow_redirects=True) as client:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            futures = {
                ex.submit(process_one, item, client, system, user_template): item
                for item in pending
            }
            for fut in as_completed(futures):
                if cost_alarm:
                    for f in futures:
                        f.cancel()
                    break
                try:
                    r = fut.result()
                    _record(r)
                except Exception as e:
                    item = futures[fut]
                    print(f"  [worker error] nif={item.nif}: {type(e).__name__}: {e}")

    elapsed = time.monotonic() - t0
    final_cost = _estimate_cost_usd(total_tok_in, total_tok_out)
    n_done = counts["ok"] + counts["failed"]

    print()
    print("=" * 76)
    print(f"FIN research_prospect  env={env}  tier={tier}  elapsed={elapsed:.1f}s")
    print(f"  procesadas:    {n_done} / {len(pending)}")
    print(f"  ok:            {counts['ok']}  ({_pct(counts['ok'], n_done)})")
    print(f"  failed:        {counts['failed']}  ({_pct(counts['failed'], n_done)})")
    if failure_breakdown:
        print(f"  failure breakdown: {failure_breakdown}")
    print(f"  personas_extraidas total: {personas_total}")
    print(f"  thin_html_possibly_spa:   {thin_html}")
    print(f"  tokens: in={total_tok_in}  out={total_tok_out}")
    print(f"  coste estimado USD: {final_cost:.4f} (cap {args.max_cost_usd})")
    print("=" * 76)

    if cost_alarm:
        return 2
    if counts["failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
