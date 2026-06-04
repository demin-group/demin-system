"""Tests de la deteccion de bounces/DSN en poll_imap (fix 2026-06-04).

Sin red, sin BD: solo las funciones puras `is_dsn` y
`extract_bounced_recipient`. El caso real que motivo el fix:
postmaster@decon.gr con subject "Undeliverable: Demoliciones interiores
para rehabilitaciones" quedaba en skipped_no_match y el bounce era
invisible para auto_pause.
"""
from __future__ import annotations

from replies.poll_imap import extract_bounced_recipient, is_dsn

OUR = {"gonzalo.perez@demingroupmadrid.com"}


# ─── is_dsn ────────────────────────────────────────────────────────────────


def test_dsn_por_remitente_postmaster() -> None:
    assert is_dsn("postmaster@decon.gr", "Undeliverable: Demoliciones interiores")
    assert is_dsn("Mail Delivery System <MAILER-DAEMON@mx.acme.es>", "cualquier cosa")


def test_dsn_por_subject_sin_remitente_tipico() -> None:
    assert is_dsn("noreply@relay.example.com", "Undeliverable: hola")
    assert is_dsn("x@y.com", "Mail delivery failed: returning message to sender")
    assert is_dsn("x@y.com", "Delivery Status Notification (Failure)")
    assert is_dsn("x@y.com", "No se pudo entregar el mensaje")


def test_reply_normal_no_es_dsn() -> None:
    assert not is_dsn("carmen@poaestudio.com", "Re: Demolición interior para vuestras reformas")
    assert not is_dsn("juanvalle@grupooliveros.com", "RE: Demolición interior")
    # 'post' en el local part normal no dispara
    assert not is_dsn("postventa@acme.es", "Re: consulta")


# ─── extract_bounced_recipient ─────────────────────────────────────────────

_DSN_RFC3464 = """
This is the mail system at host mx.decon.gr.

Final-Recipient: rfc822; jflores@decon.gr
Original-Recipient: rfc822;jflores@decon.gr
Action: failed
Status: 5.1.1
"""

_DSN_PROSA = """
Your message to ana.garcia@empresa.es couldn't be delivered.
The address wasn't found at the destination domain.
"""

_DSN_X_FAILED = """
X-Failed-Recipients: pedro@obras.com
The mail server could not deliver the message.
"""


def test_extract_final_recipient_rfc3464() -> None:
    assert extract_bounced_recipient(_DSN_RFC3464, OUR) == "jflores@decon.gr"


def test_extract_fallback_prosa() -> None:
    assert extract_bounced_recipient(_DSN_PROSA, OUR) == "ana.garcia@empresa.es"


def test_extract_x_failed_recipients() -> None:
    assert extract_bounced_recipient(_DSN_X_FAILED, OUR) == "pedro@obras.com"


def test_extract_excluye_nuestro_email_y_postmaster() -> None:
    body = """
    Final-Recipient: rfc822; postmaster@decon.gr
    Your message from gonzalo.perez@demingroupmadrid.com bounced.
    Recipient: jflores@decon.gr
    """
    # postmaster (header) y nuestro email (cuerpo) no son candidatos validos;
    # cae al fallback y elige jflores.
    assert extract_bounced_recipient(body, OUR) == "jflores@decon.gr"


def test_extract_sin_candidata_devuelve_none() -> None:
    assert extract_bounced_recipient("", OUR) is None
    assert extract_bounced_recipient("mensaje sin direcciones", OUR) is None
    assert (
        extract_bounced_recipient(
            "from gonzalo.perez@demingroupmadrid.com via postmaster@x.es", OUR
        )
        is None
    )
