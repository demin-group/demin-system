"""Sesiones SQLAlchemy contra Supabase Postgres.

SQLAlchemy 2.0 + psycopg3 (Lección 2). Engine lazy por entorno; sesión
síncrona vía context manager. Sin modelos ORM — los workers trabajan con
`session.execute(text(...))`.

Connection string viene de `config.get_db_url(env)`, que lee
`apps/workers/.env.{env}` y aplica el prefijo `postgresql+psycopg://`
necesario para que SQLAlchemy use psycopg3.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Literal

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_db_url

EnvName = Literal["dev", "prod"]

_engines: dict[EnvName, Engine] = {}
_sessionmakers: dict[EnvName, sessionmaker[Session]] = {}


def get_engine(env: EnvName) -> Engine:
    if env not in _engines:
        _engines[env] = create_engine(
            get_db_url(env),
            pool_pre_ping=True,
            pool_recycle=3600,
            future=True,
        )
        _sessionmakers[env] = sessionmaker(bind=_engines[env], future=True)
    return _engines[env]


@contextmanager
def get_session(env: EnvName) -> Iterator[Session]:
    """Context manager con commit/rollback automático.

    `with get_session("dev") as s: s.execute(text("..."))`. El commit ocurre
    al salir del bloque sin excepción; cualquier excepción dispara rollback
    y se re-lanza.
    """
    get_engine(env)  # inicializa lazy
    sm = _sessionmakers[env]
    session = sm()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
