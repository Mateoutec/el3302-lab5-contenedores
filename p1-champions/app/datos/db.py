"""Conexión a la base de datos relacional (PostgreSQL en Docker, SQLite en pruebas)."""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def crear_motor(database_url: str) -> Engine:
    argumentos = {}
    if database_url.startswith("sqlite"):
        argumentos["connect_args"] = {"check_same_thread": False}
    return create_engine(database_url, pool_pre_ping=True, **argumentos)


def crear_fabrica_sesiones(motor: Engine) -> sessionmaker:
    return sessionmaker(bind=motor, expire_on_commit=False)


def crear_tablas(motor: Engine) -> None:
    from app.datos import modelos  # noqa: F401  (registra las tablas en Base)

    Base.metadata.create_all(motor)


def base_de_datos_disponible(motor: Engine) -> bool:
    try:
        with motor.connect() as conexion:
            conexion.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
