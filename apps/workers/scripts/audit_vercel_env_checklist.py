"""audit_vercel_env_checklist.py -- helper Leccion 34 regla 5.

Lee apps/dashboard/.env.prod local + extrae para cada env var su prefix (10 chars)
y length. PM cross-references manualmente con Vercel dashboard (Settings ->
Environment Variables) para confirmar match. Sin acceso a Vercel CLI desde
esta sesion, este es el formato auditable.

Uso:
    cd apps/workers
    uv run python -m scripts.audit_vercel_env_checklist

Output: tabla con nombre / prefix / length / referencia canonica.
Cualquier mismatch en Vercel = bug similar a Leccion 34 incidente.
"""
from pathlib import Path

DASHBOARD_ENV = Path(__file__).parent.parent.parent / "dashboard" / ".env.prod"
WORKERS_ENV = Path(__file__).parent.parent / ".env.prod"

DASHBOARD_KEYS_TO_AUDIT = [
    "NEXT_PUBLIC_APP_URL",
    "NEXT_PUBLIC_SUPABASE_URL",
    "NEXT_PUBLIC_SUPABASE_ANON_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "ALLOWED_EMAILS",
    "VOYAGE_API_KEY",
    "VOYAGE_MODEL",
]


def parse_env(path: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE lines."""
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def shape_summary(val: str) -> tuple[str, int, str]:
    """Devuelve (prefix_10, length, category) para auditar match con Vercel."""
    n = len(val)
    if n == 0:
        return "<EMPTY>", 0, "empty"
    prefix = val[:10]
    if val.startswith("eyJ"):
        category = "JWT (legacy ANON_KEY or SERVICE_ROLE)"
    elif val.startswith("sb_secret_"):
        category = "Supabase secret (new format prod SERVICE_ROLE)"
    elif val.startswith("sb_publishable_"):
        category = "Supabase publishable (new format ANON_KEY)"
    elif val.startswith("pa-"):
        category = "Voyage API key"
    elif val.startswith("https://"):
        category = "URL"
    elif "@" in val and ("," in val or n > 10):
        category = "Email list (ALLOWED_EMAILS)"
    elif val.startswith("voyage-"):
        category = "Voyage model name"
    else:
        category = "Other"
    return prefix, n, category


def main() -> int:
    print("=" * 78)
    print(
        "Vercel env vars audit checklist -- cross-reference con Vercel dashboard\n"
        "Settings -> Environment Variables -> Production scope.\n"
        "Mismatch = bug Leccion 34. Si prefix o length difieren = revisar."
    )
    print("=" * 78)

    dashboard_env = parse_env(DASHBOARD_ENV)
    workers_env = parse_env(WORKERS_ENV)

    print(f"\nFuente canonica: {DASHBOARD_ENV.relative_to(DASHBOARD_ENV.parents[3])}\n")
    print(f"{'KEY':<35} {'PREFIX':<12} {'LEN':>5}  {'CATEGORY'}")
    print("-" * 78)

    for k in DASHBOARD_KEYS_TO_AUDIT:
        val = dashboard_env.get(k, "")
        prefix, n, cat = shape_summary(val)
        prefix_quoted = repr(prefix) if val else "<MISSING>"
        print(f"{k:<35} {prefix_quoted:<12} {n:>5}  {cat}")

    print()
    print("=" * 78)
    print("Workers .env.prod adicionales (NO van a Vercel, solo a VPS):")
    print("=" * 78)
    extra_workers = [
        "ANTHROPIC_API_KEY", "HUNTER_API_KEY", "DATABASE_URL",
        "GMAIL_OAUTH_CLIENT_ID", "GMAIL_OAUTH_CLIENT_SECRET",
        "GMAIL_OAUTH_REFRESH_TOKEN",
    ]
    print(f"{'KEY':<35} {'PREFIX':<12} {'LEN':>5}  {'CATEGORY'}")
    print("-" * 78)
    for k in extra_workers:
        val = workers_env.get(k, "")
        prefix, n, cat = shape_summary(val)
        prefix_quoted = repr(prefix) if val else "<MISSING>"
        print(f"{k:<35} {prefix_quoted:<12} {n:>5}  {cat}")

    print()
    print("=" * 78)
    print(
        "Procedimiento PM para auditar Vercel:\n"
        "1. Ir a https://vercel.com/<org>/<project>/settings/environment-variables\n"
        "2. Filtrar por 'Production' scope.\n"
        "3. Para cada KEY arriba, click 'Show' (o copiar via clipboard) y\n"
        "   comparar PREFIX (10 chars) + LENGTH con el output.\n"
        "4. Si difiere -> bug Leccion 34: actualizar Vercel con el valor\n"
        "   correcto del .env.prod local + redeploy.\n"
        "5. Tras auditoria completa: smoke en /pipeline + /metrics +\n"
        "   /approval-queue (cada uno consume distintas env vars).\n"
        "\n"
        "Decision Sprint 6: NO se puede hacer remoto sin Vercel CLI token.\n"
        "PM hace la auditoria manualmente con este checklist como referencia."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
