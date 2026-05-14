"""One-shot check estado drafts B6 en BD prod antes de send_gmail."""
import os
os.environ["ENV"] = "prod"
import psycopg
from shared.config import load_settings

s = load_settings("prod")
url = s.DATABASE_URL
if url.startswith("postgres://"):
    url = "postgresql://" + url[len("postgres://"):]

with psycopg.connect(url) as conn, conn.cursor() as cur:
    cur.execute("""
        select m.id::text, m.status, c.email, co.nombre, m.gmail_message_id, m.subject
        from messages m
        join contacts c on c.id = m.contact_id
        join companies co on co.id = c.company_id
        where m.id::text like '3a82e9b4%' or m.id::text like '4cc9eb8c%'
        order by co.nombre
    """)
    for r in cur.fetchall():
        print("draft:", r)
    print("---")
    cur.execute("select count(*), status from messages group by status order by status")
    for r in cur.fetchall():
        print("status:", r)
    print("---")
    cur.execute("select id::text, email_address, status, current_day_sent, daily_cap, last_send_reset from mailboxes")
    for r in cur.fetchall():
        print("mailbox:", r)
