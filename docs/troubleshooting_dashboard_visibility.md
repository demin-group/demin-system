# Troubleshooting: el dashboard no muestra drafts pendientes

> Doc operativa para **Gonzalo**. PM (Alberto) ya ha hecho lo que podía hacer
> remoto. Este doc da los pasos concretos para diagnosticar por qué los drafts
> no se ven cuando entras a `/approval-queue`.

Sesión de captura: 2026-05-25. Origen: en la auditoría del 25 de mayo el PM
encontró 2 drafts en la base de datos de producción pero al entrar Gonzalo al
dashboard no los veía. Lecciones 34 y 35 cubren la causa raíz que vimos en
mayo (env var de Supabase mal + Site URL apuntando a localhost). Este doc
asume que esas dos causas YA están arregladas y va al siguiente nivel de
diagnóstico.

---

## URL canónica del dashboard

**Usa esta URL exacta** (no un bookmark viejo, no una preview deploy):

> **https://demin-system.vercel.app**

Es la URL principal hoy. El dominio custom `app.demingroupmadrid.com` existe
en la configuración del proyecto Vercel pero el flujo de magic link Supabase
está apuntando a `demin-system.vercel.app` (Lección 35 — "Site URL" en
Supabase Auth). Si entras por `app.demingroupmadrid.com`, el dashboard
funciona pero el magic link te puede llevar a `demin-system.vercel.app` —
quédate en `demin-system.vercel.app` para evitar confusión durante el login.

> **Bookmarks obsoletos:** si tienes guardado algo del estilo
> `demin-system-git-main-…vercel.app`, `demin-system-xxx-yyy.vercel.app`, o
> cualquier URL con sufijo que NO sea exactamente `demin-system.vercel.app`,
> bórralo y usa solo la URL canónica de arriba. Las preview deploys de
> Vercel no comparten env vars con producción y pueden mostrar BD distinta o
> dar errores raros.

---

## Pasos para Gonzalo (ejecutar en orden)

### Paso 1 — ventana de incógnito limpia

1. Abre Chrome (o Edge/Firefox/Safari, sirve cualquiera).
2. **Nueva ventana de incógnito** — `Ctrl+Shift+N` en Chrome/Edge,
   `Ctrl+Shift+P` en Firefox, `Cmd+Shift+N` en Safari.
   - **Por qué incógnito:** las cookies de sesiones previas y las extensiones
     del browser principal pueden estar interfiriendo. La ventana de
     incógnito arranca limpia.
3. Pega exactamente: `https://demin-system.vercel.app`
4. Verás la pantalla de **Login** pidiendo email.

### Paso 2 — login con magic link

1. Escribe `gonzalo.perez@demingroupmadrid.com` y dale al botón.
2. Espera el correo (suele llegar en <30 segundos).
3. Abre el correo en una pestaña aparte. **NO cierres la ventana de
   incógnito** donde pediste el login.
4. **Antes de clicar el link, mira a dónde apunta:**
   - Pasa el ratón por encima del botón / link sin hacer click.
   - Abajo a la izquierda del navegador / en el preview de Gmail debe
     aparecer una URL que **empieza por** `https://demin-system.vercel.app/auth/callback?code=...`.
   - Si empieza por `http://localhost:3000`, **PARA** — eso significa que
     Supabase Site URL volvió a apuntar mal a localhost. Reporta a PM.
5. Haz click en el link. Te llevará al dashboard ya logueado.

### Paso 3 — verificar que ves los drafts

1. Una vez dentro del dashboard, ve a `/approval-queue` (o
   "Cola de aprobación" en el menú lateral).
2. **Si ves los drafts pendientes:** ✓ problema resuelto, sigue trabajando
   normal.
3. **Si dice "No hay drafts pendientes":**
   - Antes de hacer nada más: **reporta a PM** indicando que llegaste hasta
     aquí en incógnito y aún no se ven.
   - Sigue al **Paso 4 — DevTools** para capturar evidencia.

---

## Paso 4 — DevTools (solo si los drafts NO aparecen)

Esto captura la información técnica que PM necesita para diagnosticar.

### 4.1 — Abrir DevTools

1. En la pestaña del dashboard (donde dice "No hay drafts pendientes"), pulsa
   **F12**.
   - En Mac: `Cmd+Option+I`.
   - Se abre un panel lateral o inferior con varias pestañas: Elements,
     Console, Network, etc.

### 4.2 — Capturar errores de Console

1. Click en la pestaña **Console** (arriba del panel DevTools).
2. Si hay líneas en rojo o naranja, **haz captura de pantalla** completa del
   panel.
3. Guárdala como `console-errors.png` y envíasela a PM.

### 4.3 — Capturar el request a Supabase

1. Click en la pestaña **Network** del panel DevTools.
2. **IMPORTANTE:** marca el checkbox **Preserve log** (arriba del panel)
   para que no se borre al recargar.
3. Pulsa **F5** para recargar la página.
4. Espera 3-5 segundos a que termine de cargar.
5. En la lista de requests que aparece, busca uno que contenga `messages`
   o `rest/v1/messages` en el nombre — es la llamada a Supabase para leer
   los drafts.
6. **Click sobre ese request** y verás un panel a la derecha con varias
   pestañas (Headers, Payload, Response).
7. Haz captura de pantalla del panel mostrando:
   - La pestaña **Headers** (arriba): qué URL se está llamando.
   - La pestaña **Response** (al lado): qué devuelve Supabase.
8. Guárdalas como `network-headers.png` y `network-response.png`.

### 4.4 — Enviar a PM

Envía las 3 capturas (`console-errors.png`, `network-headers.png`,
`network-response.png`) a PM por el canal habitual. Con eso PM puede
diagnosticar:

- Si el request está autenticando bien (Headers).
- Si la BD está devolviendo `[]` por filtro mal puesto (Response).
- Si hay un error JavaScript downstream silenciando datos (Console).

---

## Causas conocidas que YA están descartadas

Estas causas se diagnosticaron en mayo y están en Lecciones 34/35. Si vuelves
a estar en este flujo, asume que NO son la causa actual (porque están
arregladas y monitorizadas):

- **Supabase Site URL apuntando a localhost** (Lección 35). Sigue estando
  bien si el magic link te lleva a `demin-system.vercel.app` como debe
  (Paso 2.4).
- **`SUPABASE_SERVICE_ROLE_KEY` mal copy-pasted** (Lección 34). Auditoría
  posterior con `audit_vercel_env_checklist.py` validó el resto de env
  vars Vercel. Si aún así dudas, PM puede re-correr `scripts/audit_vercel_env_checklist.py`
  con el `.env.prod` actual para re-validar.

## Causas posibles si llegas aquí con captura DevTools

Estas son las hipótesis que PM revisará con tus capturas:

1. **Rate limit Supabase Auth** — si pediste varios magic links en poco
   tiempo, Supabase puede bloquear nuevos durante ~30 min. Espera y vuelve a
   intentar.
2. **Cookie de sesión expirada** — el dashboard puede mostrarte logueado pero
   con sesión caducada que devuelve 401 silencioso. Logout + login resuelve.
3. **Bug en el filtro del query del frontend** — alguna actualización
   reciente puede haber cambiado el filtro de `status='drafted'`. PM revisa
   el código.
4. **Drafts cancelados/aprobados sin que lo notases** — si entre el momento
   en que PM hizo la auditoría y tu intento de verlos alguien procesó la
   cola, ya no hay drafts pendientes. Revisa `/metrics` para ver volumen
   total reciente.
5. **Worker `auto_replenish` no está repobalndo cola** — si la cola se vacía
   y no hay empresas frescas en el pool, no hay drafts nuevos. PM revisa en
   `audit_pool_contacts.py`.

---

## Notas finales

- **NUNCA cambies env vars en Vercel ni en Supabase tú** — eso lo hace PM.
  Tu rol es reportar lo que ves y enviar las capturas de DevTools.
- **NUNCA borres cookies del navegador en sesión real** sin avisar — perder
  la sesión activa puede saturar el rate limit de magic links si
  re-intentas varias veces seguidas.
- **Si todo el flow funciona pero ves un draft con contenido raro** (ej.
  email del remitente apareciendo en el cuerpo del mensaje), eso ya lo
  arregló la sesión del 25 de mayo (Lecciones 39-42). Si vuelves a ver
  algo así, reporta a PM directamente con captura del draft — es regresión
  nueva, no este flujo.
