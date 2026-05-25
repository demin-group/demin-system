# Re-autorización Gmail OAuth: ampliar scope a `gmail.modify`

> Doc operativa para **PM (Alberto)** + **Gonzalo**. Resuelve el bloqueador
> humano **B7** (Lección 36): el worker `poll_imap.py` requiere scope
> `gmail.modify`, pero el `refresh_token` actual de Gonzalo solo cubre
> `gmail.send`. Sin esta re-autorización, Fase 3 (lectura de respuestas) no
> funciona productiva — el worker corre y exit 3 cada vez.

Sesión de captura: 2026-05-25. Cambio de scope en código ya aplicado en
`apps/workers/scripts/gmail_oauth_setup.py:68` y `:13` (commit posterior). Lo
único pendiente es la acción humana de re-autorizar.

---

## ⚠️ Aviso importante: lo que va a anunciar el consent screen

Cuando Gonzalo acepte el consent en el browser, Google va a mostrar un texto
del tipo:

> **DEMIN Workers (desktop) quiere acceder a tu Cuenta de Google**
>
> - Leer, redactar, enviar y **eliminar permanentemente** todos tus emails
>   de Gmail
> - Ver, editar, crear o cambiar la configuración de tu correo y filtros
> - Ver tu dirección de email

**Esto es normal y esperado. NO está mal.**

Tres puntos para que Gonzalo lo entienda antes de aceptar:

1. **El scope se llama `gmail.modify`** porque incluye la capacidad de marcar
   emails como leídos. La etiqueta "modify" agrupa varias operaciones bajo el
   mismo permiso técnico — incluyendo el "eliminar permanentemente" que
   Google obliga a anunciar como permiso máximo del scope.
2. **El código NO borra emails**. Solo hace dos cosas con el buzón de
   Gonzalo:
   - Enviar correos productivos (ya lo hacía).
   - Leer respuestas que llegan y marcarlas como leídas tras procesarlas (lo
     nuevo de Fase 3 — `poll_imap.py`).
3. **Google obliga a anunciar el permiso MÁXIMO del scope**, no el uso real.
   Es como cuando una app pide "acceso al micrófono" pero solo lo usa para
   detectar silencio. La política de Google es transparente sobre el
   permiso técnico concedido; el uso real está auditado en el repo público
   `demin-group/demin-system`.

Si Gonzalo prefiere ver el código antes de aceptar, los dos workers que tocan
su buzón son:

- `apps/workers/outreach/send_gmail.py` — envío de correos.
- `apps/workers/replies/poll_imap.py` — lectura + marcar como leídas.

Ninguno hace `users.messages.trash` ni `users.messages.delete` (los endpoints
de Gmail API que borran).

---

## Pasos para re-autorizar (6 pasos, ~15 min)

### Paso 1 — Gonzalo revoca el consent actual

Sin revocar primero, Google puede no devolver `refresh_token` nuevo porque
considera que ya hay autorización vigente (aunque el scope sea menor). El
script `gmail_oauth_setup.py` fuerza `prompt=consent` pero por seguridad
empezamos limpios.

1. Gonzalo abre `https://myaccount.google.com/permissions` logueado con
   `gonzalo.perez@demingroupmadrid.com`.
2. Busca **"DEMIN Workers (desktop)"** en la lista de apps con acceso.
3. Click en la app → botón **"Quitar acceso"** / **"Remove access"** →
   confirmar.
4. Esto invalida el `refresh_token` actual. **El sistema de envío productivo
   queda offline hasta que terminemos el Paso 5.** PM debe avisar a Gonzalo
   antes de iniciar este paso si hay drafts en cola que esperan envío
   inmediato.

### Paso 2 — Verificar que el código tiene el scope nuevo

PM (no Gonzalo) verifica en el repo local que el cambio de scope ya está:

```bash
grep -n "gmail.modify" apps/workers/scripts/gmail_oauth_setup.py
# Debe mostrar:
# 13:   - Scopes: anadir `https://www.googleapis.com/auth/gmail.modify`.
# 72: SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
```

Si NO aparece, PM aborta — el cambio de scope falló o no se commiteó.

### Paso 3 — PM lanza el script de OAuth setup

PM con el repo clonado localmente y `credentials.json` en `apps/workers/`:

```bash
cd apps/workers
uv run python scripts/gmail_oauth_setup.py \
    --credentials credentials.json \
    --email gonzalo.perez@demingroupmadrid.com
```

Esto:

- Abre el browser default de PM.
- Pide login con cuenta Google.
- **IMPORTANTE:** debe loguearse con `gonzalo.perez@demingroupmadrid.com`,
  NO con la cuenta personal de PM. El `refresh_token` resultante será para
  la cuenta que se loguee.
- Si PM no tiene la contraseña de Gonzalo: la opción cómoda es coordinar
  una llamada/screen-share y que Gonzalo introduzca la contraseña en el
  browser de PM. La opción más limpia (recomendada) es que Gonzalo
  ejecute el script en SU máquina con SU `credentials.json` clonado del
  repo — pero entonces necesita uv + Python instalados, lo cual añade
  setup.

### Paso 4 — Consent screen (Gonzalo acepta el aviso del bloque anterior)

Tras login:

- Google muestra el consent screen con el texto del aviso de arriba.
- Gonzalo (o quien tenga el browser delante) acepta.
- Google redirige al callback localhost del script.
- Script imprime `REFRESH TOKEN (...)` a stdout + guarda en
  `.gmail_refresh_token_gonzalo.perez@demingroupmadrid.com.txt` (gitignored).

Si el consent screen no aparece (Google devuelve directo al callback), es
porque el revoke del Paso 1 no se hizo bien. PM revoca otra vez en
`myaccount.google.com/permissions` y re-lanza el script.

### Paso 5 — PM persiste el refresh_token nuevo en BD

```bash
cd apps/workers
uv run python scripts/seed_oauth_token.py --env prod \
    --email gonzalo.perez@demingroupmadrid.com \
    --token-file .gmail_refresh_token_gonzalo.perez@demingroupmadrid.com.txt
```

Esto encripta el token vía Supabase Vault y lo guarda en
`mailboxes.oauth_refresh_token_encrypted` reemplazando el anterior
(`gmail.send`-only). El `send_gmail.py` lo seguirá usando para enviar (el
scope `gmail.modify` cubre `gmail.send` como subconjunto) y `poll_imap.py`
empezará a funcionar.

**Importante:** una vez confirmado el seed con éxito, borrar el fichero
`.gmail_refresh_token_*.txt` del disco. Es un secreto y aunque está
gitignored, no debe quedar en local más tiempo del necesario (Lección 31 —
exposure de secrets por inercia).

### Paso 6 — Verificar que `poll_imap` funciona

```bash
ssh demin@178.105.143.239
sudo systemctl start demin-poll-imap.service
sudo journalctl -u demin-poll-imap.service -n 50 --no-pager
```

Verificación esperada (logs del worker):

- Si sale `exit 0` con `replies_inserted=N` (N puede ser 0 si nadie ha
  respondido aún): ✓ B7 cerrado.
- Si sale `exit 3` con `BLOQUEADOR B7 -- scope OAuth insuficiente`: la
  re-autorización no surtió efecto. PM verifica que el seed del Paso 5 fue
  al `--env prod` correcto y que el refresh_token capturado tras el consent
  es el nuevo (no se reusó el viejo en caché).
- Si sale otro error: revisa journal completo y reporta a PM. Lección 36
  cubre el patrón meta.

Tras verificación OK, el `demin-poll-imap.timer` ya está configurado en VPS
(commit `a394a8e`) y disparará cada hora automáticamente. No requiere
intervención adicional.

---

## Riesgos / consideraciones

- **Ventana ciega durante Paso 1 → Paso 5.** Mientras el revoke esté
  aplicado y el seed nuevo no se haya completado, **el envío productivo
  también está parado** (no solo poll_imap — porque `send_gmail.py` usa el
  mismo `refresh_token` que poll_imap ahora). Tiempo total típico: 5-15 min
  si PM y Gonzalo están sincronizados. Hacerlo fuera de business hours
  Madrid (por ej. fin de semana o noche) minimiza impacto en envíos
  scheduled.
- **Si Gonzalo se equivoca de cuenta en el login** (usa su personal Gmail
  en vez de `gonzalo.perez@demingroupmadrid.com`), el token resultante NO
  sirve y todos los envíos productivos saldrían desde su cuenta personal —
  fuga grave de imagen. El Paso 5 falla porque el email del token no
  coincide con el `mailboxes.email` esperado, pero conviene capturarlo en
  Paso 4 antes: revisar que el consent screen dice
  `gonzalo.perez@demingroupmadrid.com` arriba a la derecha (avatar Google).
- **El consent screen está en inglés o español según la config de Google
  de Gonzalo.** Las traducciones del aviso pueden variar mínimamente. La
  semántica es la misma: "Leer/redactar/enviar/eliminar emails" =
  scope completo `gmail.modify`.
- **El fichero `credentials.json`** (OAuth client config) NO cambia. Solo
  cambia el `refresh_token`. Si PM ya lo tiene en `apps/workers/` desde el
  setup original de mayo, no necesita re-descargarlo.

---

## Después de B7 cerrado

Pendientes naturales una vez `poll_imap` funcione:

- Comprobar que `replies.classify_replies` clasifica bien la primera
  respuesta real que entre. `apps/workers/replies/classify_replies.py` ya
  está en cron VPS (`demin-classify-replies.timer`).
- Verificar que `handle_actions.py` dispara las acciones correctas
  (re_engage 60d para `no_ahora`, opt-out permanente para `optout`, etc.).
- Que la pantalla `/inbox` del dashboard liste las replies con sus badges.
  PM revisa con la primera respuesta real que entre.
