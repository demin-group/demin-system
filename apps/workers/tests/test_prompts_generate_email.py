"""Tests estructurales de los 3 prompts generate_email_{angle}.md (Sprint 4 paso 5).

Sin LLM real — los tests verifican invariantes del archivo .md:
- existencia + secciones
- variables del user template
- email_type mencionado en system
- estructura JSON output
- placeholders bien formados (sin `{var` huérfanos)

La validación literaria del prompt (¿produce un correo que Gonzalo aprobaría?)
queda para paso 6, donde se ejecuta sobre 5 T3 reales con HITL completo.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "shared" / "prompts"

ANGLES = ("opening", "reframe", "closing")
EMAIL_TYPES = ("decisor", "nominal", "corporativo_pequeno")

# Variables comunes a los 3 ángulos.
COMMON_VARS = (
    "{nombre}",
    "{email_type}",
    "{nombre_destinatario}",
    "{cargo_destinatario}",
    "{tipo_actividad_concreta}",
    "{tipo_obra_que_hacen}",
    "{proyectos_recientes}",
    "{hooks_de_personalizacion}",
    "{kb_chunks}",
)

JSON_OUTPUT_KEYS = ("subject", "body", "razonamiento_breve")


def _path(angle: str) -> Path:
    return PROMPTS_DIR / f"generate_email_{angle}.md"


def _load(angle: str) -> tuple[str, str, str]:
    """Devuelve (raw, system, user_template) — mismo split que `_load_prompt`
    de los workers. Si el archivo no parsea correctamente, falla con error
    explícito."""
    raw = _path(angle).read_text(encoding="utf-8")
    parts = raw.split("## System", 1)
    if len(parts) != 2:
        raise AssertionError(f"prompt {angle}: falta sección '## System'")
    after_system = parts[1]
    sys_user = after_system.split("## User template", 1)
    if len(sys_user) != 2:
        raise AssertionError(f"prompt {angle}: falta sección '## User template'")
    return raw, sys_user[0].strip(), sys_user[1].strip()


# ─── 1. Existencia + estructura básica ─────────────────────────────────────


@pytest.mark.parametrize("angle", ANGLES)
def test_prompt_file_exists(angle: str) -> None:
    assert _path(angle).exists(), f"falta {_path(angle).name}"


@pytest.mark.parametrize("angle", ANGLES)
def test_prompt_parses_into_system_and_user_template(angle: str) -> None:
    raw, system, user = _load(angle)
    assert len(raw) > 200, f"{angle} sospechosamente corto: {len(raw)} chars"
    assert system, f"{angle}: system vacío"
    assert user, f"{angle}: user template vacío"


# ─── 2. Variables del user template ────────────────────────────────────────


@pytest.mark.parametrize("angle", ANGLES)
def test_user_template_has_all_common_variables(angle: str) -> None:
    _, _, user = _load(angle)
    missing = [v for v in COMMON_VARS if v not in user]
    assert not missing, f"{angle}: faltan variables {missing}"


@pytest.mark.parametrize("angle", ("reframe", "closing"))
def test_correos_previos_present_in_reframe_and_closing(angle: str) -> None:
    _, _, user = _load(angle)
    assert "{correos_previos}" in user, f"{angle}: falta {{correos_previos}}"


def test_correos_previos_absent_from_opening() -> None:
    """En el primer correo no hay correos previos — debe estar omitido del
    template para que el worker no tenga que pasar un placeholder dummy."""
    _, _, user = _load("opening")
    assert "{correos_previos}" not in user


# ─── 3. Bloque condicional por email_type ──────────────────────────────────


@pytest.mark.parametrize("angle", ANGLES)
@pytest.mark.parametrize("email_type", EMAIL_TYPES)
def test_system_mentions_each_email_type(angle: str, email_type: str) -> None:
    """Cada uno de los 3 valores de email_type debe aparecer en el system
    para que el LLM aplique correctamente la decisión C (autoregulación)."""
    _, system, _ = _load(angle)
    assert email_type in system, f"{angle}: email_type '{email_type}' ausente en system"


# ─── 4. Identidad y reglas de tono ─────────────────────────────────────────


@pytest.mark.parametrize("angle", ANGLES)
@pytest.mark.parametrize("token", ("DEMIN", "Gonzalo"))
def test_system_mentions_demin_and_gonzalo(angle: str, token: str) -> None:
    _, system, _ = _load(angle)
    assert token in system, f"{angle}: '{token}' ausente en system"


@pytest.mark.parametrize("angle", ANGLES)
def test_system_mentions_no_emojis_rule(angle: str) -> None:
    """La regla de tono "sin emojis ni signos de exclamación" debe estar
    explícita — es la diferencia entre prosa Gonzalo y prosa SaaS genérica."""
    _, system, _ = _load(angle)
    assert "emoji" in system.lower(), f"{angle}: regla 'sin emojis' ausente"


# ─── 5. Estructura JSON output ─────────────────────────────────────────────


@pytest.mark.parametrize("angle", ANGLES)
@pytest.mark.parametrize("key", JSON_OUTPUT_KEYS)
def test_system_specifies_json_output_keys(angle: str, key: str) -> None:
    _, system, _ = _load(angle)
    assert key in system, f"{angle}: key '{key}' del JSON output ausente en system"


@pytest.mark.parametrize("angle", ANGLES)
def test_system_forbids_markdown_in_output(angle: str) -> None:
    """El parser tolerante del worker (paso 6) acepta code fences, pero el
    prompt debe instruir al LLM a NO devolverlos en primer lugar."""
    _, system, _ = _load(angle)
    assert "code fences" in system or "markdown" in system.lower()


# ─── 6. Placeholders bien formados ─────────────────────────────────────────


_PLACEHOLDER_OPEN = re.compile(r"\{([a-z_][a-z_]*)")


@pytest.mark.parametrize("angle", ANGLES)
def test_no_dangling_placeholder_braces(angle: str) -> None:
    """Pillar errores típicos de copy-paste: `{nombre ` sin cierre, o
    `{var\\n` que no terminan en `}`. Cada `{<lowercase identifier>` debe
    estar seguido inmediatamente por `}`."""
    raw, _, _ = _load(angle)
    for m in _PLACEHOLDER_OPEN.finditer(raw):
        end = m.end()
        if end >= len(raw) or raw[end] != "}":
            ctx = raw[max(0, m.start() - 30): min(len(raw), m.end() + 30)]
            pytest.fail(f"{angle}: placeholder mal formado en `{m.group()}` — contexto: {ctx!r}")


# ─── 7. Sub-objetivos diferenciadores por ángulo ───────────────────────────


def test_reframe_mentions_distinct_hook() -> None:
    """El reframe debe instruir al LLM a NO repetir el hook del opening."""
    _, system, _ = _load("reframe")
    text_lower = system.lower()
    assert "hook b" in text_lower or "no repitas" in text_lower or "distinto" in text_lower


def test_closing_invites_without_forced_dichotomy() -> None:
    """Lección 42 (2026-05-25): el closing v2 invita al 'más adelante' sin
    forzar pregunta dicotómica. El prompt debe (a) mencionar la idea de
    'más adelante' / 'futuro' como puerta abierta, (b) prohibir
    explícitamente las preguntas binarias del tipo '¿lo descartamos?'
    que eran el patrón pasivo-agresivo de la v1."""
    _, system, _ = _load("closing")
    text_lower = system.lower()
    # Sigue invitando al "más adelante" como puerta abierta.
    assert "más adelante" in text_lower or "mas adelante" in text_lower
    # Prohibe explícitamente la pregunta binaria forzada (Lección 42).
    assert "prohibido" in text_lower
    assert "lo descartamos" in text_lower  # aparece como ejemplo prohibido
    # La sección PROHIBIDO debe estar visible en el system.
    assert "binarias" in text_lower or "ultim" in text_lower or "pasivo" in text_lower


def test_closing_forbids_aggressive_subject() -> None:
    """Lección 42: el closing v2 prohíbe asuntos tipo 'Último correo',
    'Última oportunidad', etc."""
    _, system, _ = _load("closing")
    text_lower = system.lower()
    assert "último correo" in text_lower or "ultimo correo" in text_lower
    assert "última oportunidad" in text_lower or "ultima oportunidad" in text_lower


def test_closing_body_word_limit_is_shorter() -> None:
    """El closing es el más corto de los tres (100 palabras vs 130). Eso
    es decisión consciente del paso 5 — confirmamos que el límite quedó
    explícito en el prompt."""
    _, system, _ = _load("closing")
    assert "100 palabras" in system


@pytest.mark.parametrize("angle", ("opening", "reframe"))
def test_opening_and_reframe_body_limit_is_130(angle: str) -> None:
    _, system, _ = _load(angle)
    assert "130 palabras" in system


# ─── 8. Versionado en cabecera (regla 8 Apéndice A) ────────────────────────


@pytest.mark.parametrize("angle", ANGLES)
def test_prompt_has_version_header(angle: str) -> None:
    """Regla 8: prompts versionados. La cabecera del .md debe llevar
    "Versión X" para que cualquier cambio de prompt sea trazable."""
    raw, _, _ = _load(angle)
    assert re.search(r"Versi[oó]n\s+\d", raw), f"{angle}: cabecera sin versión"


# ─── 9. Lección 39 — saludo neutro sin marca temporal en opening ───────────


def test_opening_forbids_temporal_greeting() -> None:
    """Lección 39 (2026-05-25): el opening debe prohibir explícitamente
    'Buenos días' y 'Buenas tardes' (saludos con marca temporal). Razón:
    el correo se abre muchas horas después de enviarse y un saludo
    desincronizado delata el envasado en serie."""
    _, system, _ = _load("opening")
    text_lower = system.lower()
    assert "buenos días" in text_lower or "buenos dias" in text_lower
    assert "buenas tardes" in text_lower
    assert "saludo" in text_lower
    # La prohibición debe estar marcada explícitamente
    assert "prohibido" in text_lower or "no uses" in text_lower or "sin marca temporal" in text_lower


def test_opening_mentions_neutral_greeting_variants() -> None:
    """El opening debe mencionar las variantes de saludo neutro
    permitidas para que el LLM las use rotativamente."""
    _, system, _ = _load("opening")
    # Al menos una de las variantes canónicas debe aparecer como ejemplo.
    canonical_variants = [
        "espero que estés bien",
        "espero que te pille bien",
        "te escribo porque",
    ]
    assert any(v in system.lower() for v in canonical_variants), (
        "opening: no menciona ninguna variante canónica de saludo neutro"
    )


# ─── 10. Lección 40 — prohibido email/teléfono/web del remitente en cuerpo ─


@pytest.mark.parametrize("angle", ANGLES)
def test_prompt_forbids_sender_contact_in_body(angle: str) -> None:
    """Lección 40 (2026-05-25): los 3 prompts deben prohibir explícitamente
    escribir email/teléfono/web del remitente en el cuerpo. La firma se
    añade automáticamente en send_gmail._FOOTER."""
    _, system, _ = _load(angle)
    text_lower = system.lower()
    assert "prohibido" in text_lower
    # Mención explícita del email del remitente / firma automática
    assert "@demingroupmadrid.com" in system or "email del remitente" in text_lower
    assert "firma" in text_lower
    # Frases de cortesía sugeridas como alternativa
    assert "quedo a vuestra disposición" in text_lower or "podéis escribirme" in text_lower


# ─── 11. Lección 39 — cabeceras de cadencia D+14/D+28 ──────────────────────


def test_reframe_mentions_d14_in_system() -> None:
    """Lección 39: el reframe v2 envía a los 14 días (no 4 como v1).
    El system debe reflejar 'Hace 14 días' o equivalente."""
    _, system, _ = _load("reframe")
    assert "14 días" in system or "14 dias" in system or "+14" in system


def test_closing_mentions_d28_in_system() -> None:
    """Lección 39: el closing v2 envía a los 28 días (no 10 como v1)."""
    _, system, _ = _load("closing")
    assert "28 días" in system or "28 dias" in system or "+28" in system
