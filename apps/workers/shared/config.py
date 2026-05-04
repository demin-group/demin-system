"""Configuración centralizada de los workers Python.

Carga `apps/workers/.env.{ENV}` (gitignored) según la variable de entorno `ENV`
(default `"dev"`). Convención validada en B7: cada entorno tiene su propio
fichero con `DATABASE_URL` ya construida (Session pooler, Lección 6) más las
keys de Anthropic, Voyage y discriminador `SUPABASE_ENV`.

Reglas que aplican aquí:
- Lección 15: el código lee los nombres exactos que documenta `.env.example`
  (`DATABASE_URL`, `SUPABASE_URL`, etc.). No se renombra ni se reconstruye.
- Apéndice A regla 5: NUNCA hardcodear credenciales — solo `.env` o env vars.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

EnvName = Literal["dev", "prod"]

WORKERS_DIR: Path = Path(__file__).resolve().parent.parent
"""Raíz de `apps/workers/`. Sirve para localizar `.env.{ENV}`."""


def env_file_path(env: EnvName) -> Path:
    if env not in ("dev", "prod"):
        raise ValueError(f"ENV inválido: {env!r}. Esperado 'dev' o 'prod'.")
    return WORKERS_DIR / f".env.{env}"


class Settings(BaseSettings):
    DATABASE_URL: str
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str
    SUPABASE_ENV: EnvName

    ANTHROPIC_API_KEY: str
    ANTHROPIC_MODEL_CLASSIFY: str = "claude-haiku-4-5-20251001"
    ANTHROPIC_MODEL_GENERATE: str = "claude-sonnet-4-6"
    ANTHROPIC_MODEL_RESEARCH: str = "claude-sonnet-4-6"
    ANTHROPIC_MODEL_REPLY: str = "claude-haiku-4-5-20251001"

    VOYAGE_API_KEY: str
    VOYAGE_MODEL: str = "voyage-multilingual-2"
    VOYAGE_EMBEDDING_DIM: int = 1024

    LOG_LEVEL: str = "INFO"

    model_config = SettingsConfigDict(
        case_sensitive=True,
        extra="ignore",
        env_file_encoding="utf-8",
    )

    @field_validator("DATABASE_URL")
    @classmethod
    def _check_db_url(cls, v: str) -> str:
        accepted_prefixes = ("postgres://", "postgresql://", "postgresql+psycopg://")
        if not v.startswith(accepted_prefixes):
            raise ValueError(
                "DATABASE_URL inválida: debe empezar por postgres://, postgresql:// o "
                f"postgresql+psycopg:// (recibido: {v[:24]!r}…)"
            )
        return v


def load_settings(env: EnvName | None = None) -> Settings:
    """Carga `Settings` desde `apps/workers/.env.{env}`.

    Si `env` es `None`, usa la variable de entorno `ENV` (default `"dev"`).
    Falla rápido y claro si el fichero no existe o si `SUPABASE_ENV` dentro
    del fichero no coincide con el `env` solicitado.
    """
    if env is None:
        candidate = os.environ.get("ENV", "dev")
        if candidate not in ("dev", "prod"):
            raise ValueError(
                f"ENV inválido: {candidate!r}. Esperado 'dev' o 'prod' "
                f"(o variable ENV no definida → default 'dev')."
            )
        env = candidate  # type: ignore[assignment]

    path = env_file_path(env)
    if not path.exists():
        raise FileNotFoundError(
            f"No existe {path}. Crea el fichero copiando "
            f"apps/workers/.env.example y rellenando los valores reales."
        )

    s = Settings(_env_file=str(path))  # type: ignore[call-arg]
    if s.SUPABASE_ENV != env:
        raise ValueError(
            f"Inconsistencia de entorno: cargué {path.name} pero "
            f"SUPABASE_ENV={s.SUPABASE_ENV!r}. Esperado SUPABASE_ENV={env!r}. "
            f"Revisa el .env."
        )
    return s


_ACTIVE_ENV: EnvName = (os.environ.get("ENV", "dev"))  # type: ignore[assignment]
settings: Settings = load_settings(_ACTIVE_ENV)
ACTIVE_ENV_FILE: Path = env_file_path(_ACTIVE_ENV)
"""Path del `.env.{ENV}` cargado al importar este módulo. Útil para logs/smoke."""


def get_db_url(env: EnvName) -> str:
    """Devuelve la `DATABASE_URL` del entorno indicado, prefijada para
    SQLAlchemy 2.0 + psycopg3 (`postgresql+psycopg://`).

    Carga una instancia temporal de `Settings` desde `.env.{env}` sin
    alterar el singleton global `settings`.
    """
    s = load_settings(env)
    url = s.DATABASE_URL
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    raise ValueError(
        f"DATABASE_URL en .env.{env} con prefijo desconocido: {url[:24]!r}…"
    )
