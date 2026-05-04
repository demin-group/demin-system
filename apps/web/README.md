# DEMIN Group — sitio público (`apps/web`)

Landing one-pager pública de DEMIN Group, desplegable a `demingroupmadrid.com`. Stack: Next.js 15 (App Router) + Tailwind v4 + Geist Sans. Sin shadcn, sin tracking de terceros.

> Especificación de referencia: §13 de `tasks/todo.md` y prompt de Bloque C en el repo. Las decisiones marcadas como `[DECIDIDO]` no se cuestionan sin pregunta explícita.

---

## Estructura

```
apps/web/
├── app/
│   ├── (legal)/                    # Layout compartido para páginas legales
│   │   ├── aviso-legal/page.tsx
│   │   ├── privacidad/page.tsx
│   │   ├── cookies/page.tsx
│   │   └── layout.tsx
│   ├── api/contact/route.ts        # POST → web_leads (zod + Supabase + honeypot)
│   ├── globals.css                 # Tailwind v4 + CSS variables de paleta
│   ├── layout.tsx                  # Metadata SEO global, Geist Sans, lang=es
│   ├── page.tsx                    # Home one-pager
│   ├── robots.ts
│   ├── sitemap.ts
│   └── favicon.ico
├── components/
│   ├── icons/SocialIcons.tsx       # SVG inline (sin lucide/heroicons)
│   ├── seo/LocalBusinessJsonLd.tsx # JSON-LD Schema.org
│   ├── sections/                   # Header, Hero, Servicios, Proceso, Valores,
│   │                                 Proyectos, Contacto, Footer
│   └── ui/                         # Client components: ContactForm, Lightbox,
│                                     WhatsAppFloat, CookieBanner, SectionHeading
├── lib/supabase.ts                 # Cliente server-side con service role
├── public/
│   ├── obras/                      # 6 fotos antiguas (sin uso desde sección Proyectos)
│   ├── proyectos/                  # 1 carpeta por proyecto (slug); fotos manuales
│   ├── uploads-raw/                # Originales WhatsApp + logo (gitignore opcional)
│   ├── logo-demin.jpg              # Logo blanco sobre fondo gris
│   └── og-image.jpg                # Placeholder (= hero) — ver TODO pre-launch
└── .env.example                    # Plantilla de variables de entorno
```

---

## Desarrollo local

```bash
cd apps/web
cp .env.example .env.local
# rellenar .env.local con valores reales (ver Bitwarden)
npm install
npm run dev
```

Abrir <http://localhost:3000>.

Para probar el formulario de contacto en local hace falta apuntar `.env.local` a `demin-dev` (no producción). El insert va a la tabla `web_leads`.

### Variables de entorno (ver `.env.example`)

| Variable | Dónde se usa | Bitwarden |
|---|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | cliente + server | `demin-supabase-{dev\|prod}-publishable` |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | cliente (no se usa hoy) | idem |
| `SUPABASE_SERVICE_ROLE_KEY` | solo `/api/contact` (Node runtime) | `demin-supabase-{dev\|prod}-service-role` |
| `CONTACT_NOTIFICATION_EMAIL` | destino del aviso de leads inbound vía Resend (ver detalle abajo) | n/a |
| `RESEND_API_KEY` | solo `/api/contact` — auth contra Resend para enviar la notificación | `demin-resend-api-key` |
| `CONTACT_FROM_EMAIL` | remitente del aviso. Default `DEMIN Group <noreply@demingroupmadrid.com>`. Dominio raíz verificado en Resend (ver detalle abajo) | n/a |
| `NEXT_PUBLIC_SITE_URL` | metadata SEO + JSON-LD | n/a |

Nunca commitear `.env.local`. El `.gitignore` ya lo excluye.

#### Detalle: notificación de leads inbound (Resend)

1. **Qué hace.** Cuando alguien envía el formulario de `/contacto`, el route handler `/api/contact`:
   1. Valida el payload con zod.
   2. Inserta en `web_leads` de Supabase (con service role).
   3. Envía un email de notificación a `CONTACT_NOTIFICATION_EMAIL` vía Resend.
2. **Best-effort en el envío.** El paso 2 (insert en BD) es la única operación que puede devolver 500. El paso 3 es best-effort: si Resend falla por cualquier motivo (timeout, 4xx/5xx, `RESEND_API_KEY` ausente, dominio no verificado, `CONTACT_NOTIFICATION_EMAIL` vacío) se loguea con `[resend]` prefix y se devuelve **200** al cliente igualmente. El lead nunca se pierde por un fallo de notificación.
3. **Proveedor.** Resend (region `eu-west-1`, dominio `demingroupmadrid.com` verificado). Razón de no usar Gmail SMTP: el dominio está en warmup activo vía Lemwarm sobre `gonzalo.perez@` y meter SMTP por ahí compromete la reputación SPF/DKIM/DMARC (ver Lección 4).
4. **Remitente.** `CONTACT_FROM_EMAIL` default: `DEMIN Group <noreply@demingroupmadrid.com>`. La API key generada en Resend está **restringida al dominio raíz** `demingroupmadrid.com`; intentar enviar desde `@send.demingroupmadrid.com` devuelve `403 — API key not authorized to send emails from X`. Aunque el remitente visible es del dominio raíz, los DNS de Resend (SPF/DKIM/return-path) viven en `send.demingroupmadrid.com` y mantienen la reputación de envío transaccional aislada del Workspace de Gonzalo (que está en warmup activo vía Lemwarm sobre `gonzalo.perez@`).
5. **Valor recomendado en prod.** `CONTACT_NOTIFICATION_EMAIL=gonzalo.perez@demingroupmadrid.com`. En Vercel se configura en *Project Settings → Environment Variables*. En local/dev mismo destinatario con el acuerdo explícito de no superar 1-2 envíos de prueba para no contaminar el warmup.

---

## Verificación

```bash
npm run build    # type-check + production build
npm run lint
```

Lighthouse local recomendado antes de cada despliegue: Performance ≥ 90, Accessibility ≥ 95, Best Practices ≥ 95, SEO = 100. Probar también el lightbox con teclado (Esc, ←, →) y el envío del formulario contra `demin-dev`.

---

## Despliegue a Vercel

1. **Crear proyecto en Vercel** apuntando al repo `demin-group/demin-system`. Root directory: `apps/web/`. Framework preset: Next.js (auto-detectado).
2. **Configurar variables de entorno** en *Project Settings → Environment Variables*. Copiar las de `.env.example` con valores de producción (`demin-prod` en Bitwarden).
3. **Apuntar el dominio** `demingroupmadrid.com` desde Namecheap a Vercel (registros A/CNAME que indique Vercel). NO tocar `app.demingroupmadrid.com` — pertenece al dashboard.
4. **Verificar dominio** en Google Search Console y enviar `sitemap.xml`. Postmaster Tools ya está verificado del Bloque A.
5. **Sanity check post-deploy**:
   - Lighthouse mobile real
   - Formulario de contacto end-to-end (un envío real entra en `web_leads` de prod)
   - JSON-LD válido en <https://search.google.com/test/rich-results>
   - OG image visible en <https://www.opengraph.xyz/url/https%3A%2F%2Fdemingroupmadrid.com>

---

## Bloqueadores pre-launch (no cierran Bloque C en local, sí cierran ir a producción)

1. **NIF de Gonzalo** en `app/(legal)/aviso-legal/page.tsx` (LSSI 10.1).
2. **Crear alias `contacto@demingroupmadrid.com`** en Workspace Admin (apunta al buzón principal).
3. **OG image real** (1200×630 con logo + tagline + foto). Ahora es copia del hero.
4. **Verificar dominio en Google Search Console** y enviar sitemap.

---

## Reglas no negociables aplicables a este sitio

Del Apéndice A de `tasks/todo.md`:

- **Regla 5:** sin `localhost` ni credenciales hardcoded en commits.
- **Regla 11:** nunca inventar clientes, testimonios, casos de éxito o cifras.
- **Regla 12:** separación estricta `demingroupmadrid.com` (público) ≠ `app.demingroupmadrid.com` (dashboard auth).
