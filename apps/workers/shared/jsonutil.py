"""Utilidades de parsing de JSON emitido por LLMs. Módulo PURO (solo stdlib):
no importa config ni clientes, para que los parsers de los workers sigan
siendo testables sin entorno.

`extract_json_block` es robusto a:
- code fences (```json ... ```),
- **prosa antes y/o después del objeto JSON** — Lección 64: Opus 4.8 (y
  modelos "reasoning-forward" en general) anteponen razonamiento antes del
  JSON pese a pedir "solo JSON", lo que rompía un `json.loads` directo.
"""
from __future__ import annotations


def extract_json_block(raw: str) -> str:
    """Devuelve el primer objeto JSON balanceado `{...}` contenido en `raw`,
    descartando prosa/markdown antes o después.

    - Quita code fences ```...``` si envuelven todo el bloque.
    - Localiza la primera `{` y avanza contando llaves, respetando strings y
      escapes, hasta cerrar el objeto. Devuelve ese substring.
    - Si no hay `{`, devuelve la cadena sin fences (deja que `json.loads`
      falle con un error claro, o que el caller valide el tipo si era una
      lista válida).
    - Si hay `{` pero nunca cierra (truncado), devuelve desde la primera `{`
      hasta el final (json.loads dará JSONDecodeError, comportamiento previo).
    """
    s = raw.strip()
    if s.startswith("```"):
        nl = s.find("\n")
        if nl != -1:
            s = s[nl + 1:]
        if s.endswith("```"):
            s = s[:-3]
        s = s.strip()

    start = s.find("{")
    if start == -1:
        return s

    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[start:i + 1]
    return s[start:]
