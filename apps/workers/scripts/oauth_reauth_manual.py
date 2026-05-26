"""oauth_reauth_manual.py -- variante PM-mensajero de gmail_oauth_setup.py.

Diseñada para el flow donde Gonzalo autoriza en SU navegador pero PM/Code
está en OTRA máquina. `gmail_oauth_setup.py` original usa
`InstalledAppFlow.run_local_server` que abre el navegador en la máquina
DEL script y levanta server local -- inservible para escenario remoto.

Aquí en cambio: construimos URL de autorización a mano con redirect_uri
http://localhost:<port> (Desktop OAuth client solo acepta localhost o
127.0.0.1; IPs públicas están prohibidas), imprimimos URL para que PM la
pase a Gonzalo, y luego intercambiamos el code que vuelva.

Gonzalo verá "no se puede conectar a localhost:8765" en su navegador
después de aceptar el consent -- es esperado. La URL en su barra contiene
`?code=...&scope=...&state=...`. PM nos pega esa URL completa (o el code).

Flujo en dos comandos:

    # Paso 1 -- generar URL
    cd apps/workers
    PYTHONPATH=. .venv/Scripts/python scripts/oauth_reauth_manual.py \\
        --credentials credentials.json --step generate

    # Paso 2 -- intercambiar code (URL completa o code pelado)
    PYTHONPATH=. .venv/Scripts/python scripts/oauth_reauth_manual.py \\
        --credentials credentials.json --step exchange \\
        --code 4/0AeXXXXX
    # ó:
    PYTHONPATH=. .venv/Scripts/python scripts/oauth_reauth_manual.py \\
        --credentials credentials.json --step exchange \\
        --auth-url 'http://localhost:8765/?state=...&code=...&scope=...'

Validaciones en exchange:
1. Scopes recibidos incluyen `gmail.modify`. Si no, exit 3 sin guardar.
2. Email autorizado == gonzalo.perez@demingroupmadrid.com (via userinfo).
   Si no, exit 4 sin guardar -- evita quemar token de cuenta equivocada.
3. refresh_token presente. Si no (porque Google no lo devolvió aunque
   pedimos prompt=consent), exit 5.

Solo si las 3 validaciones pasan: guarda en
`.gmail_refresh_token_gonzalo.perez@demingroupmadrid.com.txt` (gitignored).
Luego se persiste a BD con seed_oauth_token.py --env prod.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
from google_auth_oauthlib.flow import Flow  # type: ignore[import-untyped]


SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
REDIRECT_URI = "http://localhost:8765"
EXPECTED_EMAIL = "gonzalo.perez@demingroupmadrid.com"
TOKEN_FILE_NAME = f".gmail_refresh_token_{EXPECTED_EMAIL}.txt"
# PKCE verifier persistido entre 'generate' y 'exchange' (ambos comandos
# crean Flow distintos; el verifier de generate debe matchear el del
# exchange o Google rechaza el code).
PKCE_FILE_NAME = ".oauth_pkce_verifier.txt"


def cmd_generate(credentials_path: Path) -> int:
    flow = Flow.from_client_secrets_file(str(credentials_path), scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="false",
        login_hint=EXPECTED_EMAIL,
    )
    # Persistir code_verifier para que exchange use el mismo (PKCE).
    pkce_path = Path(PKCE_FILE_NAME).resolve()
    verifier = getattr(flow, "code_verifier", None)
    if not verifier:
        print(
            "ERROR: Flow.code_verifier vacio tras authorization_url; "
            "la lib no genero PKCE. Algo raro.",
            file=sys.stderr,
        )
        return 8
    pkce_path.write_text(verifier, encoding="utf-8")
    print(f"PKCE verifier guardado en {pkce_path.name} (gitignored).")
    print()
    print("=" * 78)
    print("PASO 1 -- URL de autorizacion generada")
    print("=" * 78)
    print()
    print("URL para Gonzalo:")
    print()
    print(auth_url)
    print()
    print("=" * 78)
    print("Que va a pasar:")
    print("  1. Gonzalo abre la URL en su navegador.")
    print(f"  2. Inicia sesion con {EXPECTED_EMAIL} (NO cuenta personal).")
    print("  3. Acepta el consent screen (texto 'leer/redactar/enviar/")
    print("     eliminar emails' -- es normal, scope gmail.modify).")
    print("  4. Google redirige a http://localhost:8765/?code=...&scope=...")
    print("     El navegador mostrara 'no se puede conectar' -- es esperado.")
    print("  5. La URL en la barra del navegador es lo unico que nos importa.")
    print("     PM copia esa URL completa y me la pasa.")
    print()
    print(f"State generado (no necesario para exchange con code): {state[:16]}...")
    print()
    print("Tras recibir la URL/code, ejecutar paso 2:")
    print(
        "  scripts/oauth_reauth_manual.py --credentials credentials.json"
        " --step exchange --auth-url '<URL pegada>'"
    )
    return 0


def extract_code(auth_url: str | None, code_arg: str | None) -> str:
    if code_arg:
        return code_arg.strip()
    if auth_url:
        parsed = urlparse(auth_url)
        qs = parse_qs(parsed.query)
        codes = qs.get("code", [])
        if not codes:
            print(
                f"ERROR: --auth-url no contiene ?code=... query param: {auth_url}",
                file=sys.stderr,
            )
            sys.exit(2)
        return codes[0]
    print("ERROR: necesitas --auth-url o --code", file=sys.stderr)
    sys.exit(2)


def cmd_exchange(
    credentials_path: Path, code: str | None, auth_url: str | None
) -> int:
    code_value = extract_code(auth_url, code)
    print(f"[1/4] code recibido (primeros 10 chars): {code_value[:10]}...")

    flow = Flow.from_client_secrets_file(str(credentials_path), scopes=SCOPES)
    flow.redirect_uri = REDIRECT_URI
    # Cargar PKCE verifier persistido por cmd_generate (sino Google rechaza
    # el code porque el challenge no matchea).
    pkce_path = Path(PKCE_FILE_NAME).resolve()
    if not pkce_path.exists():
        print(
            f"ERROR: {pkce_path.name} no existe. Ejecuta --step generate primero.",
            file=sys.stderr,
        )
        return 9
    flow.code_verifier = pkce_path.read_text(encoding="utf-8").strip()
    try:
        flow.fetch_token(code=code_value)
    except Exception as e:
        print(f"ERROR: fetch_token fallo: {e}", file=sys.stderr)
        print(
            "Causas tipicas: code ya usado (Google los invalida tras 1 uso),"
            " expirado (~10 min ventana), pegado con caracteres de mas,"
            " o PKCE verifier desincronizado (re-genera URL).",
            file=sys.stderr,
        )
        return 6

    creds = flow.credentials
    print(f"[2/4] fetch_token OK. Scopes concedidos: {creds.scopes}")

    # Guarda inmediatamente en fichero temporal para que el refresh_token
    # NO se pierda si una validacion posterior falla (el code de Google
    # solo se puede canjear una vez -- si abortamos sin guardar, hay que
    # regenerar URL completa).
    tmp_path = Path(f"{TOKEN_FILE_NAME}.tmp").resolve()
    if creds.refresh_token:
        tmp_path.write_text(creds.refresh_token, encoding="utf-8")
        print(f"      refresh_token guardado en TMP: {tmp_path.name}")

    # Validacion 1: scope contiene gmail.modify.
    granted = set(creds.scopes or [])
    if SCOPES[0] not in granted:
        print(
            f"ERROR: scope insuficiente. Esperado {SCOPES[0]} en {granted}",
            file=sys.stderr,
        )
        return 3

    # Validacion 2: email autorizado == EXPECTED_EMAIL.
    # Usar Gmail API users/getProfile (cubierto por gmail.modify) en lugar
    # de oauth2/userinfo (que requiere openid/email/profile scopes, no
    # pedidos aqui -- daria 401).
    try:
        profile = httpx.get(
            "https://gmail.googleapis.com/gmail/v1/users/me/profile",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=10.0,
        )
        profile.raise_for_status()
        info = profile.json()
        actual_email = info.get("emailAddress")
    except Exception as e:
        print(f"ERROR: gmail users.getProfile fallo: {e}", file=sys.stderr)
        return 7
    print(f"[3/4] userinfo email={actual_email}")
    if actual_email != EXPECTED_EMAIL:
        print(
            f"ERROR: cuenta autorizada {actual_email!r} NO coincide con "
            f"esperada {EXPECTED_EMAIL!r}. Token NO se guarda.",
            file=sys.stderr,
        )
        return 4

    # Validacion 3: refresh_token presente.
    if not creds.refresh_token:
        print(
            "ERROR: Google no devolvio refresh_token. Revoca consent en "
            "https://myaccount.google.com/permissions y reintenta el flow.",
            file=sys.stderr,
        )
        return 5

    # Promueve TMP -> final tras todas las validaciones OK.
    out_path = Path(TOKEN_FILE_NAME).resolve()
    out_path.write_text(creds.refresh_token, encoding="utf-8")
    if tmp_path.exists():
        try:
            tmp_path.unlink()
        except OSError:
            pass
    print(f"[4/4] refresh_token guardado en: {out_path}")
    print()
    print("=" * 78)
    print(f"OK. Validaciones pasadas: scope=gmail.modify, email={actual_email}")
    print("=" * 78)
    print()
    print("Siguiente paso (persistir a BD prod):")
    print(
        f"  scripts/seed_oauth_token.py --env prod --email {EXPECTED_EMAIL}"
        f" --token-file {out_path.name}"
    )
    print()
    print(f"NOTA: borrar {out_path.name} del disco tras seed OK (Leccion 31).")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--credentials",
        required=True,
        help="Path a credentials.json de Google Cloud Console (Desktop).",
    )
    p.add_argument(
        "--step",
        choices=["generate", "exchange"],
        required=True,
        help="generate=imprime URL. exchange=intercambia code recibido.",
    )
    p.add_argument(
        "--code",
        help="Authorization code pelado (4/0AeXXXXX). Alt a --auth-url.",
    )
    p.add_argument(
        "--auth-url",
        help="URL completa de la barra del navegador de Gonzalo tras "
        "consent. El script extrae ?code=... y lo usa.",
    )
    args = p.parse_args()

    creds_path = Path(args.credentials).resolve()
    if not creds_path.exists():
        print(f"ERROR: {creds_path} no existe.", file=sys.stderr)
        return 1

    if args.step == "generate":
        return cmd_generate(creds_path)
    return cmd_exchange(creds_path, args.code, args.auth_url)


if __name__ == "__main__":
    sys.exit(main())
