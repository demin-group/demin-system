"""Muestra la cadencia ACTIVA real (sequences.steps) en la BD del ENV.
Solo lectura. Uso (en apps/workers):  ENV=prod uv run python -m scripts.show_cadence
"""
from __future__ import annotations

import os

from sqlalchemy import text

from shared.db import get_session

env = os.environ.get("ENV", "dev")
with get_session(env) as s:  # type: ignore[arg-type]
    rows = s.execute(
        text("select nombre, is_active, steps from sequences order by nombre")
    ).mappings().all()
    if not rows:
        print("(no hay filas en sequences)")
    for r in rows:
        print(f"\nsecuencia: {r['nombre']}   activa={r['is_active']}")
        steps = r["steps"] or []
        for i, st in enumerate(steps):
            print(f"  step {i}: D+{st.get('day')}   {st.get('angle')}")
    print()
