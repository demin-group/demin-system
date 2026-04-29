"""Sesión SQLAlchemy contra Supabase Postgres.

Engine + sessionmaker con `psycopg[binary]` (psycopg3) sobre el connection string
de Supabase. La extensión `vector` para pgvector se activa vía migración
(`infra/supabase/migrations/`), no desde la app.

Pendiente de implementar el engine real en cuanto B6 cree el schema.
"""
