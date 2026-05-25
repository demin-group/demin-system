"""Bloque 0 diagnostics 2026-05-25: 0.2 + 0.4 + 0.5 en una sola corrida."""
import os
os.environ["ENV"] = "prod"
import json
import psycopg
from shared.config import load_settings

s = load_settings("prod")
url = s.DATABASE_URL
if url.startswith("postgres://"):
    url = "postgresql://" + url[len("postgres://"):]

def H(t):
    print("\n" + "=" * 78)
    print(f"  {t}")
    print("=" * 78)

with psycopg.connect(url) as conn, conn.cursor() as cur:
    # ============================================================
    # 0.2 — DRAFT JAIME NOZALEDA (CLOSING)
    # ============================================================
    H("0.2.a — Draft closing en cola para nozar.es (Jaime/Lena)")
    cur.execute("""
        select m.id, m.status, m.step_index, m.angle, m.subject,
               m.scheduled_for, m.created_at, m.sent_at,
               ct.email, ct.nombre, ct.cargo,
               co.nombre as empresa, co.nif
        from messages m
        join contacts ct on ct.id = m.contact_id
        join companies co on co.id = ct.company_id
        where ct.email ilike '%@nozar.es' or co.nif = 'A78062601'
        order by m.created_at
    """)
    rows = cur.fetchall()
    if not rows:
        print("  (sin match para nozar.es ni NIF A78062601)")
    for r in rows:
        print(f"\n  msg_id={r[0]}  status={r[1]}  step={r[2]}  angle={r[3]}")
        print(f"    subject={r[4]!r}")
        print(f"    scheduled_for={r[5]}  created_at={r[6]}  sent_at={r[7]}")
        print(f"    contact={r[8]} ({r[9]} / {r[10]})  empresa={r[11]} nif={r[12]}")

    H("0.2.b — Body literal del draft closing nozar.es")
    cur.execute("""
        select m.id, m.subject, m.body
        from messages m
        join contacts ct on ct.id = m.contact_id
        where ct.email ilike '%nozaleda%' and m.status='drafted' and m.angle='closing'
    """)
    rows = cur.fetchall()
    for r in rows:
        print(f"\n  msg_id={r[0]}")
        print(f"  SUBJECT: {r[1]!r}")
        print(f"  BODY:\n---")
        print(r[2])
        print("---")
        body_lower = (r[2] or "").lower()
        for needle in ("demingroup.es", "demingroupmadrid.com", "gonzalo.perez@",
                       "gonzalo@demingroup", "perez@", "@gmail.com", "692 319",
                       "692319"):
            if needle in body_lower:
                print(f"  FOUND in body: {needle!r}")
        subj_lower = (r[1] or "").lower()
        for needle in ("ultimo correo", "último correo", "ultima oportunidad",
                       "última oportunidad", "me rindo", "definitivamente",
                       "lo descartamos", "me bajo"):
            if needle in subj_lower or needle in body_lower:
                print(f"  TONE FLAG: {needle!r} aparece")

    H("0.2.c — research_data Lena Construcciones (NIF A78062601)")
    cur.execute("""
        select id, nombre, tier, ia_fit, ia_fit_reason, web, research_done_at,
               research_data
        from companies where nif='A78062601'
    """)
    rows = cur.fetchall()
    if not rows:
        print("  (sin company con NIF A78062601 — busco por nombre)")
        cur.execute("""
            select id, nif, nombre, tier, ia_fit, web, research_data
            from companies where nombre ilike '%lena%' or nombre ilike '%nozar%'
            limit 5
        """)
        for r in cur.fetchall():
            print(f"  id={r[0]} nif={r[1]} nombre={r[2]} tier={r[3]} ia_fit={r[4]} web={r[5]}")
            if r[6]:
                print(f"  research_data keys: {list(r[6].keys())}")
    for r in rows:
        print(f"  id={r[0]}  nombre={r[1]}  tier={r[2]}  ia_fit={r[3]}")
        print(f"  ia_fit_reason={r[4]!r}")
        print(f"  web={r[5]}  research_done_at={r[6]}")
        rd = r[7] or {}
        print(f"\n  research_data (JSON literal):\n{json.dumps(rd, ensure_ascii=False, indent=2)}")
        # buscar menciones suspectas
        rd_str = json.dumps(rd, ensure_ascii=False).lower()
        for needle in ("17 promociones", "diecisiete promociones", "el cañaveral",
                       "cañaveral", "canaveral"):
            if needle in rd_str:
                print(f"  FOUND: {needle!r} aparece en research_data")
            else:
                print(f"  NOT FOUND: {needle!r} NO aparece en research_data")

    H("0.2.d — Historial completo de mensajes a Jaime Nozaleda")
    cur.execute("""
        select m.id, m.status, m.step_index, m.angle, m.subject,
               m.created_at, m.scheduled_for, m.sent_at, m.gmail_message_id,
               ct.email, ct.is_primary, ct.email_priority
        from messages m
        join contacts ct on ct.id = m.contact_id
        where ct.email ilike '%nozaleda%' or ct.email ilike '%jaime%@nozar%'
        order by m.created_at
    """)
    rows = cur.fetchall()
    for r in rows:
        print(f"  step={r[2]} angle={r[3]:8s} status={r[1]:10s} "
              f"sent_at={str(r[7])[:19]:19s} sched={str(r[6])[:19]:19s}")
        print(f"     subject={r[4]!r}")
        print(f"     created_at={r[5]}  is_primary={r[10]} prio={r[11]} email={r[9]}")

    # ============================================================
    # 0.4 — POOL DE CONTACTOS ELEGIBLES
    # ============================================================
    H("0.4.a — Companies ia_fit='fit' por tier")
    cur.execute("""
        select tier, count(*) from companies where ia_fit='fit'
        group by tier order by 1
    """)
    for r in cur.fetchall():
        print(f"  tier={r[0]}  fit_count={r[1]}")
    cur.execute("select count(*) from companies where ia_fit='fit'")
    print(f"  TOTAL fit (cualquier tier): {cur.fetchone()[0]}")

    H("0.4.b — De esas fit, cuántas con research_done_at NOT NULL, por tier")
    cur.execute("""
        select tier,
               count(*) filter (where research_done_at is not null) as researched,
               count(*) filter (where research_done_at is null) as pending,
               count(*) as total
        from companies where ia_fit='fit'
        group by tier order by 1
    """)
    for r in cur.fetchall():
        print(f"  tier={r[0]}  research_done={r[1]}  pending={r[2]}  total={r[3]}")

    H("0.4.c — De researched, cuántas con al menos un contact (NOT optout, primary)")
    cur.execute("""
        select c.tier,
               count(distinct c.id) filter (
                 where exists (
                   select 1 from contacts ct
                   where ct.company_id = c.id
                     and ct.is_optout = false
                     and ct.is_primary = true
                 )
               ) as con_contact_primary,
               count(distinct c.id) filter (
                 where exists (
                   select 1 from contacts ct
                   where ct.company_id = c.id
                     and ct.is_optout = false
                     and ct.is_primary = true
                     and ct.email_verified = true
                 )
               ) as con_contact_primary_verified
        from companies c
        where c.ia_fit='fit' and c.research_done_at is not null
        group by c.tier order by 1
    """)
    for r in cur.fetchall():
        print(f"  tier={r[0]}  con_primary={r[1]}  con_primary_verified={r[2]}")

    H("0.4.d — CANDIDATOS VIRGENES para opening (sin ningún message en ningún estado)")
    cur.execute("""
        select c.tier,
               count(distinct c.id) as virgenes
        from companies c
        join contacts ct on ct.company_id = c.id
        where c.ia_fit='fit'
          and c.research_done_at is not null
          and ct.is_optout = false
          and ct.is_primary = true
          and not exists (
            select 1 from messages m
            where m.contact_id = ct.id
              and m.status in ('sent','scheduled','drafted','approved')
          )
        group by c.tier order by 1
    """)
    for r in cur.fetchall():
        print(f"  tier={r[0]}  virgenes={r[1]}")
    cur.execute("""
        select count(distinct c.id)
        from companies c
        join contacts ct on ct.company_id = c.id
        where c.ia_fit='fit'
          and c.research_done_at is not null
          and ct.is_optout = false
          and ct.is_primary = true
          and not exists (
            select 1 from messages m
            where m.contact_id = ct.id
              and m.status in ('sent','scheduled','drafted','approved')
          )
    """)
    print(f"  TOTAL VIRGENES (todos los tiers): {cur.fetchone()[0]}")

    H("0.4.e — Mismo, pero relajando is_primary y email_verified")
    cur.execute("""
        select c.tier,
               count(distinct c.id) as con_cualquier_contact_sin_mensaje
        from companies c
        join contacts ct on ct.company_id = c.id
        where c.ia_fit='fit'
          and c.research_done_at is not null
          and ct.is_optout = false
          and not exists (
            select 1 from messages m
            where m.contact_id = ct.id
              and m.status in ('sent','scheduled','drafted','approved')
          )
        group by c.tier order by 1
    """)
    for r in cur.fetchall():
        print(f"  tier={r[0]}  empresas_con_contact_sin_mensaje={r[1]}")

    H("0.4.f — Contactos distintos que han recibido >=1 correo enviado")
    cur.execute("""
        select ct.email, ct.nombre, co.nombre as empresa,
               count(*) as msgs_sent,
               min(m.sent_at) as primer_envio,
               max(m.sent_at) as ultimo_envio,
               array_agg(distinct m.angle order by m.angle) as angulos
        from messages m
        join contacts ct on ct.id = m.contact_id
        join companies co on co.id = ct.company_id
        where m.status='sent'
        group by ct.email, ct.nombre, co.nombre
        order by msgs_sent desc, ultimo_envio desc
    """)
    rows = cur.fetchall()
    print(f"  contactos distintos con envíos: {len(rows)}")
    for r in rows:
        flag = " <-- BANDERA ROJA (>=3 en 14d)" if r[3] >= 3 else ""
        print(f"  msgs={r[3]} angulos={r[6]} {r[2][:35]:35s} {r[0][:35]:35s}{flag}")

    # ============================================================
    # 0.5 — CADENCIA REAL
    # ============================================================
    H("0.5.a — sequences.steps activa (literal)")
    cur.execute("select nombre, is_active, steps from sequences")
    for r in cur.fetchall():
        print(f"  sequence={r[0]}  is_active={r[1]}")
        print(f"  steps (literal JSONB):\n{json.dumps(r[2], indent=2)}")

    H("0.5.b — Tabla 12 mensajes enviados (verifica intervalos)")
    cur.execute("""
        select m.id, m.contact_id, m.step_index, m.angle, m.sent_at,
               ct.email, co.nombre as empresa
        from messages m
        join contacts ct on ct.id = m.contact_id
        join companies co on co.id = ct.company_id
        where m.status='sent'
        order by ct.email, m.step_index
    """)
    rows = cur.fetchall()
    by_contact = {}
    for r in rows:
        by_contact.setdefault(r[5], []).append(r)
    for email, msgs in by_contact.items():
        print(f"\n  contact={email}  empresa={msgs[0][6]}")
        prev_sent = None
        for m in sorted(msgs, key=lambda x: x[2]):
            delta = ""
            if prev_sent and m[4]:
                d = (m[4] - prev_sent).total_seconds() / 86400
                delta = f"  (delta={d:.1f}d desde step anterior)"
            print(f"    step={m[2]} angle={m[3]:8s} sent_at={m[4]}{delta}")
            prev_sent = m[4]

    H("0.5.c — Drafts pendientes: step + scheduled_for + days desde step0 mismo contact")
    cur.execute("""
        select m.id, m.step_index, m.angle, m.scheduled_for, m.created_at,
               ct.email, co.nombre,
               (select min(sent_at) from messages m0
                where m0.contact_id = m.contact_id and m0.step_index=0 and m0.status='sent'
               ) as sent_at_step0
        from messages m
        join contacts ct on ct.id = m.contact_id
        join companies co on co.id = ct.company_id
        where m.status='drafted'
        order by m.created_at
    """)
    for r in cur.fetchall():
        delta_str = ""
        if r[7] and r[4]:
            delta_d = (r[4] - r[7]).total_seconds() / 86400
            delta_str = f"  draft_creado={delta_d:.1f}d desde step0_sent"
        print(f"  step={r[1]} angle={r[2]:8s} sched={str(r[3])[:19]:19s} {r[5][:35]:35s} {r[6][:30]:30s}{delta_str}")
