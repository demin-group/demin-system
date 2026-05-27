"""Tests de poll_imap matchers (revision 2026-05-27).

Cobertura de las funciones puras introducidas por el fix de los 3 bugs
encadenados:

1. `_strip_reply_prefixes`: ahora incluye RV: / R: (español) ademas de
   Re/Fwd/Fw. Iterativo para "Re: RV: ..." encadenados.
2. `extract_matching_ids_from_headers`: extrae In-Reply-To + References
   normalizados (sin angle brackets, lowercase).
3. `_normalize_message_id_header`: angle brackets + case insensitive.
4. `_normalize_rfc_id` (send_gmail): mismo helper espejo persistido en BD.

Los 3 matchers contra BD (`find_matching_message_by_*`) se testean en
backfill real contra prod y journalctl, no aqui (requieren BD prod
con replies historicos y rompen los principios de tests unitarios).
"""
from __future__ import annotations

from replies.poll_imap import (
    _normalize_message_id_header,
    _strip_reply_prefixes,
    extract_matching_ids_from_headers,
)
from outreach.send_gmail import _normalize_rfc_id


# --- _strip_reply_prefixes (fix Bug B, P1b) --------------------------------


def test_strip_re_prefix() -> None:
    assert _strip_reply_prefixes("RE: Demolición interior CABBSA") == \
        "Demolición interior CABBSA"


def test_strip_lowercase_re_prefix() -> None:
    assert _strip_reply_prefixes("re: hola") == "hola"


def test_strip_rv_spanish_forward() -> None:
    """L del fix: RV: (reenvío español) no estaba en la lista anterior.
    El caso real Umavial era: from amartin@umavial.es subject
    'RV: Demoliciones interiores...'.
    """
    assert _strip_reply_prefixes("RV: Demoliciones interiores") == \
        "Demoliciones interiores"


def test_strip_lowercase_rv() -> None:
    assert _strip_reply_prefixes("rv: algo") == "algo"


def test_strip_fwd_english() -> None:
    assert _strip_reply_prefixes("Fwd: tema") == "tema"
    assert _strip_reply_prefixes("FW: tema") == "tema"


def test_strip_chained_re_rv() -> None:
    """Subject reenviado de un reply: 'Re: RV: original'. Strip iterativo."""
    assert _strip_reply_prefixes("Re: RV: original") == "original"


def test_strip_chained_three_levels() -> None:
    assert _strip_reply_prefixes("RE: Fwd: RV: tema") == "tema"


def test_strip_no_prefix_unchanged() -> None:
    assert _strip_reply_prefixes("ALTA PROVEEDORES CADOR") == \
        "ALTA PROVEEDORES CADOR"


def test_strip_only_whitespace() -> None:
    assert _strip_reply_prefixes("   ") == ""


def test_strip_empty_string() -> None:
    assert _strip_reply_prefixes("") == ""


def test_strip_r_short_prefix() -> None:
    """R: variante corta de Re: que algunos clientes españoles usan."""
    assert _strip_reply_prefixes("R: tema") == "tema"


# --- _normalize_message_id_header (matcher RFC, fix Bug B, P0a) -----------


def test_normalize_strips_angle_brackets() -> None:
    assert _normalize_message_id_header("<abc@gmail.com>") == "abc@gmail.com"


def test_normalize_lowercases() -> None:
    assert _normalize_message_id_header("<ABC@GMAIL.COM>") == "abc@gmail.com"


def test_normalize_no_brackets_passthrough() -> None:
    assert _normalize_message_id_header("xyz@dominio.es") == "xyz@dominio.es"


def test_normalize_whitespace_trim() -> None:
    assert _normalize_message_id_header("  <abc@x>  ") == "abc@x"


# --- extract_matching_ids_from_headers (matcher RFC) -----------------------


def test_extract_in_reply_to_only() -> None:
    ids = extract_matching_ids_from_headers({
        "in-reply-to": "<abc@x.com>",
    })
    assert ids == ["abc@x.com"]


def test_extract_references_multiple() -> None:
    """References puede tener varios IDs separados por whitespace."""
    ids = extract_matching_ids_from_headers({
        "references": "<a@x> <b@y> <c@z>",
    })
    assert ids == ["a@x", "b@y", "c@z"]


def test_extract_both_dedup_preserves_order() -> None:
    """In-Reply-To duplica el ultimo de References tipicamente -- dedup."""
    ids = extract_matching_ids_from_headers({
        "in-reply-to": "<c@z>",
        "references": "<a@x> <b@y> <c@z>",
    })
    assert ids == ["c@z", "a@x", "b@y"]


def test_extract_real_umavial_pattern() -> None:
    """Caso real Umavial: in-reply-to es un id interno del dominio del
    forwarder; references contiene NUESTRO Message-ID como primer ref."""
    ids = extract_matching_ids_from_headers({
        "in-reply-to": "<006901dcecf3$05b75020$1125f060$@umavial.es>",
        "references": "<CAEJHDhPpku6mg2W_=BcedZkmUEbW554ruW=1VVGmEBGApJyuJQ@mail.gmail.com> "
                      "<006901dcecf3$05b75020$1125f060$@umavial.es>",
    })
    # Nuestro RFC Message-ID enviado tiene que estar en la lista para que
    # find_matching_message_by_rfc_id pueda matchear.
    assert "caejhdhppku6mg2w_=bcedzkmuebw554ruw=1vvgmebgapjyujq@mail.gmail.com" in ids


def test_extract_empty_headers() -> None:
    """Caso Cador: in_reply_to=''. No genera ids."""
    assert extract_matching_ids_from_headers({}) == []
    assert extract_matching_ids_from_headers({"in-reply-to": "", "references": ""}) == []


# --- _normalize_rfc_id (espejo en send_gmail) ------------------------------


def test_normalize_rfc_id_strips_brackets() -> None:
    """send_gmail._normalize_rfc_id es espejo de
    poll_imap._normalize_message_id_header. Garantiza que lo que
    persistimos en messages.rfc_message_id matchea con lo que extraemos
    de In-Reply-To/References en los replies recibidos."""
    rfc_id_with_brackets = "<CAEJHDhM+tOTOh_DBMB410zW3Gz66fHjhWpid7p--0hQs0v8sVA@mail.gmail.com>"
    expected = "caejhdhm+totoh_dbmb410zw3gz66fhjhwpid7p--0hqs0v8sva@mail.gmail.com"
    assert _normalize_rfc_id(rfc_id_with_brackets) == expected


def test_normalize_rfc_id_none() -> None:
    assert _normalize_rfc_id(None) is None
    assert _normalize_rfc_id("") is None


def test_normalize_rfc_id_matches_extracted_header() -> None:
    """Test integracion: lo que escribimos en BD debe ser igual a lo que
    leeriamos de un In-Reply-To que apunte a ese mismo Message-ID."""
    rfc_id = "<abc-123@demingroupmadrid.com>"
    persisted = _normalize_rfc_id(rfc_id)
    extracted = extract_matching_ids_from_headers({"in-reply-to": rfc_id})
    assert persisted in extracted
