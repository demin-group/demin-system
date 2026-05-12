"""gmail_oauth_setup.py -- standalone para obtener Gmail refresh_token.

Bloqueador B1 de Sprint 4 paso 7: una vez resuelto B1.1 (Google Cloud Console
setup), este script genera el refresh_token offline de larga duracion que
send_gmail.py necesita para enviar correos vía Gmail API sin re-autenticar.

Setup previo (humano en Google Cloud Console, una sola vez):

1. Crear o seleccionar proyecto en https://console.cloud.google.com
2. APIs & Services -> Library -> "Gmail API" -> Enable.
3. APIs & Services -> OAuth consent screen:
   - User type: External (o Internal si Google Workspace).
   - Scopes: anadir `https://www.googleapis.com/auth/gmail.send`.
   - Test users: anadir gonzalo.perez@demingroupmadrid.com (mientras esten
     en modo "Testing"; en "Production" no hace falta whitelist).
4. APIs & Services -> Credentials -> Create Credentials -> OAuth client ID:
   - Application type: **Desktop application** (importante; no Web).
   - Name: "DEMIN Workers (desktop)".
   - Authorized redirect URIs: (Desktop no requiere; deja vacio).
5. Download JSON -> guardar como `credentials.json` en `apps/workers/` (o
   donde sea, pero el path debe pasarse a --credentials).
   El fichero ya esta en .gitignore (no se commitea).

Uso del script:

    cd apps/workers
    uv run python scripts/gmail_oauth_setup.py \\
        --credentials credentials.json \\
        --email gonzalo.perez@demingroupmadrid.com

Comportamiento:

- Abre tu browser default en la URL de autorizacion de Google.
- Inicias sesion CON LA CUENTA DEL BUZON (gonzalo.perez@...), no la tuya.
  El refresh_token sera para esa cuenta especifica.
- Autorizas el scope gmail.send.
- Google redirige a localhost:<puerto-efimero> donde el script captura el
  authorization_code.
- Script intercambia code -> access_token + refresh_token.
- Imprime refresh_token a stdout (para copy/paste) Y lo guarda en
  `.gmail_refresh_token_<email>.txt` (gitignored).

NOTA importante:

Google solo devuelve refresh_token la PRIMERA vez que un usuario autoriza
una app, o cuando se fuerza `prompt=consent`. Este script siempre pasa
`prompt=consent` para garantizar que el refresh_token venga. Si ya
autorizaste antes y quieres regenerar: revoca acceso en
https://myaccount.google.com/permissions y reintenta.

Proximo paso (despues de este script):

    uv run python scripts/seed_oauth_token.py --env prod \\
        --email gonzalo.perez@demingroupmadrid.com \\
        --token-file .gmail_refresh_token_gonzalo.perez@demingroupmadrid.com.txt

Tras seed, send_gmail.py tendra todo lo que necesita para B5 (smoke E2E).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# google_auth_oauthlib esta en pyproject como dependencia.
from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore[import-untyped]

SCOPES = ["https://www.googleapis.com/auth/gmail.send"]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--credentials",
        required=True,
        help="Path al credentials.json descargado de Google Cloud Console "
        "(OAuth client type Desktop application).",
    )
    p.add_argument(
        "--email",
        required=True,
        help="Email del buzon. Solo se usa para nombrar el fichero de "
        "salida; el flow OAuth lo determina la cuenta con la que te "
        "logues en el browser.",
    )
    p.add_argument(
        "--port",
        type=int,
        default=0,
        help="Puerto local para el callback OAuth. 0 (default) = puerto "
        "efimero. Solo cambiarlo si tienes firewall bloqueando puertos altos.",
    )
    args = p.parse_args()

    creds_path = Path(args.credentials).resolve()
    if not creds_path.exists():
        print(f"ERROR: {creds_path} no existe.", file=sys.stderr)
        print(
            "Descarga credentials.json desde Google Cloud Console "
            "(OAuth client type Desktop) y vuelve a invocar.",
            file=sys.stderr,
        )
        return 1

    print("=" * 76)
    print(f"gmail_oauth_setup  email={args.email}")
    print("=" * 76)
    print(f"[1/3] Iniciando OAuth flow.")
    print(f"      Credentials JSON: {creds_path}")
    print(f"      Scope:            {SCOPES[0]}")
    print(f"      Callback port:    {args.port if args.port else 'efimero'}")
    print()
    print("      Se abrira tu browser. IMPORTANTE: inicia sesion con la")
    print(f"      cuenta del buzon ({args.email}), no con tu cuenta.")
    print()

    flow = InstalledAppFlow.from_client_secrets_file(str(creds_path), SCOPES)
    # access_type=offline + prompt=consent fuerzan que Google devuelva
    # refresh_token incluso si el usuario ya autorizo antes.
    creds = flow.run_local_server(
        port=args.port,
        access_type="offline",
        prompt="consent",
        open_browser=True,
    )

    print(f"[2/3] Tokens obtenidos.")
    if not creds.refresh_token:
        print(
            "ERROR: Google no devolvio refresh_token. Suele pasar si la "
            "cuenta ya autorizo la app antes y `prompt=consent` no se "
            "aplico correctamente.",
            file=sys.stderr,
        )
        print(
            "Solucion: revoca acceso en "
            "https://myaccount.google.com/permissions (busca el nombre del "
            "OAuth client), y reintenta este script.",
            file=sys.stderr,
        )
        return 2

    out_path = Path(f".gmail_refresh_token_{args.email}.txt").resolve()
    out_path.write_text(creds.refresh_token, encoding="utf-8")

    print(f"      refresh_token guardado en: {out_path}")
    print()
    print("=" * 76)
    print(f"REFRESH TOKEN ({args.email}):")
    print(creds.refresh_token)
    print("=" * 76)
    print()
    print(f"[3/3] Proximo paso: persistir en BD del entorno target.")
    print()
    print(f"  uv run python scripts/seed_oauth_token.py --env prod \\")
    print(f"      --email {args.email} \\")
    print(f"      --token-file {out_path.name}")
    print()
    print(f"NOTA: el fichero {out_path.name} contiene un secret. Borralo o")
    print(f"muevelo a Bitwarden cuando termines. Esta gitignored asi que")
    print(f"no se commiteara accidentalmente, pero igual NO lo dejes en disco.")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
