"""seed_oauth_token.py -- persiste refresh_token Gmail en mailboxes BD.

Intenta cifrar via Supabase Vault (vault.create_secret). Si Vault no esta
disponible o no tiene permisos para el role, fallback a guardar plaintext
con prefijo 'PLAINTEXT:' en el campo (para que send_gmail.py sepa que NO
es un UUID de Vault).

Idempotente: UPDATE on the mailbox de --email. Re-ejecutar reemplaza el
token previo (util si rotacion/revocacion).

Pre-requisito: el mailbox debe existir en BD (migration 11 lo seedea para
gonzalo.perez@demingroupmadrid.com). Si no existe, UPDATE devuelve 0 filas
y este script aborta con exit code 2.

Uso:

    cd apps/workers

    # Con fichero (generado por gmail_oauth_setup.py):
    uv run python scripts/seed_oauth_token.py --env prod \\
        --email gonzalo.perez@demingroupmadrid.com \\
        --token-file .gmail_refresh_token_gonzalo.perez@demingroupmadrid.com.txt

    # Con token inline (cuidado: queda en shell history):
    uv run python scripts/seed_oauth_token.py --env prod \\
        --email gonzalo.perez@demingroupmadrid.com \\
        --token 1//0eXXXXXXXX

Comportamiento sobre cifrado:

- Intenta `SELECT vault.create_secret(:tok, :name, :desc)` -- Supabase Vault
  con pgsodium. Si exito, el campo `mailboxes.oauth_refresh_token_encrypted`
  guarda el UUID del secret. send_gmail.py debe entonces hacer
  `SELECT decrypted_secret FROM vault.decrypted_secrets WHERE id = :uuid`
  para resolverlo en runtime.
- Si Vault no esta habilitado o el role no tiene permisos, captura el
  error y fallback a guardar `PLAINTEXT:<token>` en el campo. send_gmail.py
  ya esta preparado para detectar este prefijo (si no lo esta, hay que
  modificar `fetch_active_mailbox` para strip-prefix).

Integracion con send_gmail.py:

`outreach.send_gmail.resolve_refresh_token` ya soporta los 3 formatos que
este script puede persistir:
- UUID (Vault) -> resuelve via vault.decrypted_secrets en runtime.
- PLAINTEXT:<token> -> strip prefijo.
- Plaintext directo -> uso literal.

Asi que el seed funciona con Vault o sin Vault sin tocar send_gmail.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal

from typing import Any

from sqlalchemy import CursorResult, text

from shared.db import get_session

EnvName = Literal["dev", "prod"]


def try_vault_encrypt(env: EnvName, token: str, name: str) -> str | None:
    """Intenta crear secret en Supabase Vault. Devuelve UUID del secret
    si exito, None si Vault no disponible o permisos insuficientes."""
    try:
        with get_session(env) as s:
            row = s.execute(
                text(
                    "SELECT vault.create_secret("
                    "  new_secret := cast(:tok as text), "
                    "  new_name   := cast(:name as text), "
                    "  new_description := cast(:desc as text)"
                    ")"
                ),
                {
                    "tok": token,
                    "name": name,
                    "desc": f"Gmail OAuth refresh_token for {name}",
                },
            ).scalar()
        return str(row) if row else None
    except Exception as e:
        msg = str(e).splitlines()[0] if str(e) else type(e).__name__
        print(f"[vault] no disponible o error: {msg}", file=sys.stderr)
        return None


def persist(env: EnvName, email: str, value: str) -> int:
    """UPDATE mailboxes SET oauth_refresh_token_encrypted=value WHERE email."""
    with get_session(env) as s:
        result: CursorResult[Any] = s.execute(  # type: ignore[assignment]
            text(
                "UPDATE mailboxes "
                "SET oauth_refresh_token_encrypted = :v "
                "WHERE email = :e"
            ),
            {"v": value, "e": email},
        )
        return result.rowcount or 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env", choices=("dev", "prod"), required=True)
    p.add_argument("--email", required=True, help="Email del mailbox.")
    grp = p.add_mutually_exclusive_group(required=True)
    grp.add_argument(
        "--token",
        help="refresh_token como argumento (cuidado: queda en shell history).",
    )
    grp.add_argument(
        "--token-file",
        help="Path al fichero con el refresh_token (output de gmail_oauth_setup.py).",
    )
    args = p.parse_args()

    if args.token_file:
        token_path = Path(args.token_file)
        if not token_path.exists():
            print(f"ERROR: {token_path} no existe.", file=sys.stderr)
            return 1
        tok = token_path.read_text(encoding="utf-8").strip()
    else:
        tok = args.token.strip()

    if not tok:
        print("ERROR: refresh_token vacio.", file=sys.stderr)
        return 1

    print("=" * 76)
    print(f"seed_oauth_token  env={args.env}  email={args.email}")
    print("=" * 76)
    print(f"refresh_token length: {len(tok)} chars (preview: {tok[:8]}...{tok[-4:]})")
    print()
    print("Intentando cifrado via Supabase Vault...")
    secret_name = f"mailbox_oauth_{args.email}"
    uuid = try_vault_encrypt(args.env, tok, secret_name)

    if uuid:
        value_to_persist = uuid
        print(f"  OK -- vault secret id={uuid}")
        print(
            "  send_gmail.resolve_refresh_token() lo resolvera en runtime "
            "via vault.decrypted_secrets."
        )
    else:
        value_to_persist = f"PLAINTEXT:{tok}"
        print(
            "  WARN -- vault no disponible. Persistiendo plaintext con "
            "prefijo 'PLAINTEXT:' como fallback."
        )
        print(
            "          send_gmail.resolve_refresh_token() strip-eara el "
            "prefijo en runtime. Cifrado real queda como deuda tecnica "
            "(habilitar pgsodium / Vault en Supabase, Fase 3)."
        )

    print()
    rows = persist(args.env, args.email, value_to_persist)
    if rows == 0:
        print(
            f"ERROR: no se actualizo ningun mailbox. "
            f"email='{args.email}' no existe? Aplica migration 11 primero.",
            file=sys.stderr,
        )
        return 2

    print(f"OK -- mailbox {args.email} actualizado ({rows} fila).")
    print()
    print("Verificacion:")
    print(f"  uv run python -c \"from shared.db import get_session; from sqlalchemy import text;")
    print(f"with get_session('{args.env}') as s:")
    print(f"    print(s.execute(text('SELECT email, length(oauth_refresh_token_encrypted) FROM mailboxes WHERE email = :e'), {{'e':'{args.email}'}}).first())\"")
    print()
    print(f"Proximo paso: B5 smoke E2E.")
    print(f"  uv run python -m outreach.send_gmail --env {args.env} \\")
    print(f"      --max-sends 1 --override-to albertobueno10@gmail.com \\")
    print(f"      --skip-business-hours-check")
    return 0


if __name__ == "__main__":
    sys.exit(main())
