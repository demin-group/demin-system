# apps/dashboard

Panel autenticado de DEMIN (`app.demingroupmadrid.com`). Skeleton de **B3**:
auth con magic link + navegación de 6 paneles placeholder. El contenido
real de cada panel se construye en Fases 1-3.

## Stack

- Next.js 15.5 (App Router) + React 19 + TypeScript
- Tailwind CSS v4 + shadcn/ui
- Supabase Auth (magic link) vía `@supabase/ssr`

## Variables de entorno

Las claves reales viven en `.env.dev` y `.env.prod` (gitignored). La
plantilla está en `.env.example`. Variables requeridas:

| Variable | Para |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | URL del proyecto Supabase |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Publishable key (cliente) |
| `SUPABASE_SERVICE_ROLE_KEY` | Secret key (server-only, future use) |
| `NEXT_PUBLIC_APP_URL` | URL canónica del dashboard |
| `ALLOWED_EMAILS` | Lista CSV de emails autorizados a entrar |

## Comandos

```bash
# desde apps/dashboard/
cp .env.dev .env.local         # Next.js lee .env.local en dev
npm run dev                    # http://localhost:3000
npm run build                  # build de producción
npm run lint                   # ESLint
```

> **Nota sobre `.env.local`:** Next.js carga `.env.local` antes que `.env.dev`.
> Para desarrollo local, copia el contenido de `.env.dev` a `.env.local`. En
> Vercel se configuran las envs por entorno desde el panel del proyecto, no
> desde estos ficheros.

## Configuración requerida en Supabase

Antes de que el magic link funcione end-to-end hay que configurar las URLs
permitidas en cada proyecto Supabase (**Project Settings → Authentication →
URL Configuration**):

- **demin-dev:**
  - Site URL: `http://localhost:3000`
  - Additional Redirect URLs: `http://localhost:3000/auth/callback`
- **demin-prod:**
  - Site URL: `https://app.demingroupmadrid.com`
  - Additional Redirect URLs: `https://app.demingroupmadrid.com/auth/callback`

Sin esto, el correo del magic link enlazará a una URL no permitida y la
sesión no se establecerá.

## Auth flow

1. Usuario va a `/login`, introduce email
2. Cliente llama `signInWithOtp` → Supabase envía email con link a `/auth/callback?code=…`
3. Usuario hace click → `/auth/callback` (route handler) intercambia código por sesión, redirige a `/pipeline`
4. `middleware.ts` valida en cada request:
   - Si no hay sesión → redirige a `/login`
   - Si hay sesión pero email no está en `ALLOWED_EMAILS` → signOut + redirige a `/login?error=unauthorized`
5. Logout: POST a `/auth/logout` → invalida sesión + redirige a `/login`

## Estructura

```
app/
  layout.tsx              raíz: fonts + Toaster
  page.tsx                redirect → /pipeline
  login/                  login + magic link form
  auth/
    callback/             intercambia code por sesión
    logout/               invalida sesión
  (protected)/            grupo de rutas autenticadas
    layout.tsx            sidebar + verificación de sesión
    pipeline/             placeholder Fase 1
    approval-queue/       placeholder Fase 1
    inbox/                placeholder Fase 1
    kb/                   placeholder Fase 1
    metrics/              placeholder Fase 1
    settings/             placeholder Fase 1
components/
  sidebar-nav.tsx
  logout-button.tsx
  placeholder-panel.tsx
  ui/                     shadcn primitives
lib/
  supabase/
    client.ts             createBrowserClient
    server.ts             createServerClient para Server Components / route handlers
    middleware.ts         updateSession para Next.js middleware
  utils.ts                cn helper de shadcn
middleware.ts             entry point del middleware
```

## Pendiente fuera de B3

- Contenido funcional de cada panel (Fases 1-3)
- Bloqueo de paneles según rol/feature flag
- Tema claro/oscuro toggleable (ahora es auto vía `prefers-color-scheme`)
- Persistencia de sesión cross-tab (Supabase ya lo maneja vía cookies SSR; verificado en B3)
