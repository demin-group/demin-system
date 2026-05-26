"""permute_emails.py -- generador de candidatos email para Opcion C T4.

Dado un dominio inferido (por infer_domain), genera lista de patrones a
probar via SMTP. Whitelist L23 D20 ajustada para T4 (microempresas):
solo prefijos donde el gerente lee directamente.

Ver doc: docs/option_c_t4_pipeline.md (3) permute_emails.
"""
from __future__ import annotations


# Prefijos para T4 (microempresas, gerente lee todo). Cap a 5 patrones
# por dominio para no quemar SMTP probe + reducir riesgo de bloqueo.
T4_PREFIXES = (
    "info",
    "contacto",
    "administracion",
    "gerencia",
    "oficina",
)

# Email aleatorio para catch-all detection. No coincide con ningun
# patron real conocido (chars random + dominio).
CATCH_ALL_PROBE_LOCAL = "demin-catch-all-probe-x9k7q2p"


def permute_emails(domain: str) -> list[str]:
    """Devuelve lista de candidatos email para probar via SMTP.

    No incluye el catch-all probe. Para catch-all use catch_all_probe().
    """
    if not domain:
        return []
    return [f"{prefix}@{domain}" for prefix in T4_PREFIXES]


def catch_all_probe(domain: str) -> str:
    """Email aleatorio que NADIE tiene. Si SMTP responde 250 a este,
    el dominio es catch-all y los probes reales son falsos positivos."""
    return f"{CATCH_ALL_PROBE_LOCAL}@{domain}"
