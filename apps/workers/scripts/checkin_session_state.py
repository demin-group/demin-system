"""Check-in sesion 2026-05-25: estado BD prod tras cierre Sprint 6."""
import os
os.environ["ENV"] = "prod"
import psycopg
from shared.config import load_settings

s = load_settings("prod")
url = s.DATABASE_URL
if url.startswith("postgres://"):
    url = "postgresql://" + url[len("postgres://"):]

with psycopg.connect(url) as conn, conn.cursor() as cur:
    print("=== messages.status counts ===")
    cur.execute("""
        select status, count(*)
        from messages
        group by status
        order by status
    """)
    for row in cur.fetchall():
        print(f"  {row[0]:20s} {row[1]}")

    print("\n=== messages B6 productivos (id LIKE '3a82e9b4%' OR '4cc9eb8c%') ===")
    cur.execute("""
        select id, status, angle, sent_at, scheduled_for, gmail_message_id,
               (subject) as subject
        from messages
        where id::text like '3a82e9b4%' or id::text like '4cc9eb8c%'
        order by created_at
    """)
    rows = cur.fetchall()
    if not rows:
        print("  (sin match por prefijo — quizá no eran UUIDs exactos)")
    for r in rows:
        print(f"  id={str(r[0])[:8]}.. status={r[1]} angle={r[2]} sent_at={r[3]} sched={r[4]} gmid={r[5]}")
        print(f"     subject={r[6]!r}")

    print("\n=== Ultimos 10 messages sent o approved ===")
    cur.execute("""
        select id, status, angle, sent_at, created_at, subject
        from messages
        where status in ('sent','approved','queued','sending')
        order by coalesce(sent_at, created_at) desc
        limit 10
    """)
    for r in cur.fetchall():
        print(f"  status={r[1]:10s} angle={r[2]:15s} sent={r[3]} created={r[4]}  {r[5][:60] if r[5] else ''!r}")

    print("\n=== mailboxes prod state (todas columnas) ===")
    cur.execute("""
        select column_name from information_schema.columns
        where table_name='mailboxes' order by ordinal_position
    """)
    cols = [r[0] for r in cur.fetchall()]
    print(f"  columnas: {cols}")

    cur.execute("select * from mailboxes")
    rows = cur.fetchall()
    for r in rows:
        for col, val in zip(cols, r):
            if 'token' in col.lower() or 'secret' in col.lower():
                val = '<redacted>'
            print(f"  {col}: {val}")
        print("  ---")

    print("\n=== Drafts en cola HITL prod (drafted) ===")
    cur.execute("""
        select count(*) from messages where status='drafted'
    """)
    print(f"  drafted: {cur.fetchone()[0]}")

    print("\n=== Replies inbound recibidas ===")
    cur.execute("""
        select count(*) from replies
    """)
    print(f"  replies total: {cur.fetchone()[0]}")
    cur.execute("""
        select category, count(*) from replies group by category order by 2 desc
    """)
    for r in cur.fetchall():
        print(f"  cat={r[0]!r:30s} {r[1]}")

    print("\n=== events columnas ===")
    cur.execute("""
        select column_name from information_schema.columns
        where table_name='events' order by ordinal_position
    """)
    ev_cols = [r[0] for r in cur.fetchall()]
    print(f"  {ev_cols}")

    # detectar la columna que actúa como 'kind' (event_type / name / type)
    candidates = [c for c in ev_cols if c in ('event_type','type','name','kind','action','category')]
    if candidates:
        col = candidates[0]
        print(f"\n=== Eventos ({col}) ultimas 24h ===")
        cur.execute(f"""
            select {col}, count(*) from events
            where created_at > now() - interval '24 hours'
            group by {col} order by 2 desc
            limit 20
        """)
        for r in cur.fetchall():
            print(f"  {r[0]!r:40s} {r[1]}")

        print(f"\n=== Eventos ({col}) ultimos 7 dias top 15 ===")
        cur.execute(f"""
            select {col}, count(*), max(created_at) from events
            where created_at > now() - interval '7 days'
            group by {col} order by 2 desc limit 15
        """)
        for r in cur.fetchall():
            print(f"  {r[0]!r:40s} count={r[1]} last={r[2]}")
    else:
        print("  (no se detecta columna kind/event_type/name)")
