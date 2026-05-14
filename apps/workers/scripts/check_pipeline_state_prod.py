"""Estado pipeline prod antes de poblamiento adicional."""
import os
os.environ["ENV"] = "prod"
import psycopg
from shared.config import load_settings

s = load_settings("prod")
url = s.DATABASE_URL
if url.startswith("postgres://"):
    url = "postgresql://" + url[len("postgres://"):]

with psycopg.connect(url) as conn, conn.cursor() as cur:
    print("=== Companies T3 fit con web ===")
    cur.execute("""
        select count(*) filter (where research_done_at is null)            as pending_research,
               count(*) filter (where research_done_at is not null)        as research_done,
               count(*)                                                    as total
        from companies
        where tier='T3' and ia_fit='fit' and web is not null and web <> ''
    """)
    print(cur.fetchone())

    print("\n=== Contacts en empresas con research_done ===")
    cur.execute("""
        select count(distinct co.id) as companies_with_contact,
               count(c.id)           as total_contacts,
               count(distinct co.id) filter (where co.research_done_at is not null and co.tier='T3' and co.ia_fit='fit') as t3_research_done_with_contact
        from companies co
        left join contacts c on c.company_id = co.id
        where co.tier='T3' and co.ia_fit='fit'
    """)
    print(cur.fetchone())

    print("\n=== Drafts en cola (status=drafted) ===")
    cur.execute("""
        select count(*) from messages where status='drafted'
    """)
    print(cur.fetchone())

    print("\n=== Empresas T3 fit con web SIN research_done (candidatas) ===")
    cur.execute("""
        select count(*) from companies
        where tier='T3' and ia_fit='fit' and web is not null and web <> ''
              and research_done_at is null
    """)
    print(cur.fetchone())

    print("\n=== Empresas T3 fit con research+contact pero SIN draft ===")
    cur.execute("""
        select count(distinct co.id) from companies co
        join contacts c on c.company_id = co.id
        where co.tier='T3' and co.ia_fit='fit' and co.research_done_at is not null
              and not exists (
                select 1 from messages m where m.contact_id = c.id
              )
    """)
    print(cur.fetchone())
