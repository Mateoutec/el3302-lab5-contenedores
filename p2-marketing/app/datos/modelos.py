"""Tablas de la base de datos (ORM SQLAlchemy)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.datos.db import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class CampanaORM(Base):
    __tablename__ = "campanas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    empresa: Mapped[str] = mapped_column(String(80))
    producto: Mapped[str] = mapped_column(String(160))
    publico: Mapped[str] = mapped_column(String(160))
    tono: Mapped[str] = mapped_column(String(40))
    red_social: Mapped[str] = mapped_column(String(20))
    foto: Mapped[str] = mapped_column(String(300))
    descripcion_foto: Mapped[str] = mapped_column(Text, default="")
    paleta: Mapped[list] = mapped_column(JSON, default=list)
    proveedor_guiones: Mapped[str] = mapped_column(String(40), default="")
    estado: Mapped[str] = mapped_column(String(30), index=True)
    error: Mapped[str] = mapped_column(Text, default="")
    guion_elegido_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora, onupdate=_ahora)

    guiones: Mapped[list["GuionORM"]] = relationship(cascade="all, delete-orphan", order_by="GuionORM.orden")
    recursos: Mapped[list["RecursoORM"]] = relationship(cascade="all, delete-orphan", order_by="RecursoORM.orden")
    publicaciones: Mapped[list["PublicacionORM"]] = relationship(cascade="all, delete-orphan", order_by="PublicacionORM.id")


class GuionORM(Base):
    __tablename__ = "guiones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campana_id: Mapped[int] = mapped_column(ForeignKey("campanas.id", ondelete="CASCADE"), index=True)
    orden: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(String(200))
    enfoque: Mapped[str] = mapped_column(Text)
    gancho: Mapped[str] = mapped_column(Text)
    escenas: Mapped[list] = mapped_column(JSON)
    llamado_accion: Mapped[str] = mapped_column(Text)
    caption: Mapped[str] = mapped_column(Text)
    hashtags: Mapped[list] = mapped_column(JSON)


class RecursoORM(Base):
    __tablename__ = "recursos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campana_id: Mapped[int] = mapped_column(ForeignKey("campanas.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(10))
    orden: Mapped[int] = mapped_column(Integer)
    ruta: Mapped[str] = mapped_column(String(300))
    proveedor: Mapped[str] = mapped_column(String(40))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)


class PublicacionORM(Base):
    __tablename__ = "publicaciones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campana_id: Mapped[int] = mapped_column(ForeignKey("campanas.id", ondelete="CASCADE"), index=True)
    red_social: Mapped[str] = mapped_column(String(20))
    modo: Mapped[str] = mapped_column(String(10))
    estado: Mapped[str] = mapped_column(String(20))
    id_externo: Mapped[str] = mapped_column(String(120), default="")
    url: Mapped[str] = mapped_column(String(400), default="")
    detalle: Mapped[str] = mapped_column(Text, default="")
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)
