# shared/prompts

Prompts versionados en el repo (regla nº 8 del Apéndice A — nunca hardcoded en código).

Formato: un archivo Markdown por prompt. Convención de nombrado:
- `classify_fit.md` — filtro IA por descripción de actividad (§8.3)
- `research_prospect.md` — extracción de señales de la web del prospecto (§8.4)
- `generate_email_opening.md` — apertura D+0
- `generate_email_reframe.md` — re-encuadre D+4
- `generate_email_closing.md` — cierre D+10
- `generate_email_re_engage_60.md` — re-engage tras "no_ahora"
- `generate_email_re_engage_90.md` — re-engage tras "no_interesado" o cold
- `classify_reply.md` — clasificación de respuestas + flag opt-out (§11)

Pendientes de redactar en sus respectivas fases. Los esqueletos viven en
`tasks/todo.md` §8.3, §8.4, §10.2 y §11.
