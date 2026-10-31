"""Tablas de la base de datos (ORM SQLAlchemy)."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.datos.db import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class PartidoORM(Base):
    __tablename__ = "partidos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_externo: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    competicion: Mapped[str] = mapped_column(String(10))
    etapa: Mapped[str] = mapped_column(String(40))
    jornada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    estado: Mapped[str] = mapped_column(String(20), index=True)
    equipo_local: Mapped[str] = mapped_column(String(80))
    equipo_visitante: Mapped[str] = mapped_column(String(80))
    escudo_local: Mapped[str | None] = mapped_column(String(300), nullable=True)
    escudo_visitante: Mapped[str | None] = mapped_column(String(300), nullable=True)
    goles_local: Mapped[int | None] = mapped_column(Integer, nullable=True)
    goles_visitante: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora, onupdate=_ahora)

    predicciones: Mapped[list["PrediccionORM"]] = relationship(back_populates="partido")


class PrediccionORM(Base):
    __tablename__ = "predicciones"
    __table_args__ = (
        CheckConstraint("resultado IN ('LOCAL', 'EMPATE', 'VISITANTE')", name="ck_prediccion_resultado"),
        CheckConstraint("goles_local >= 0 AND goles_visitante >= 0", name="ck_prediccion_goles"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    partido_id: Mapped[int] = mapped_column(ForeignKey("partidos.id", ondelete="CASCADE"), index=True)
    autor: Mapped[str] = mapped_column(String(60))
    resultado: Mapped[str] = mapped_column(String(10))
    goles_local: Mapped[int] = mapped_column(Integer)
    goles_visitante: Mapped[int] = mapped_column(Integer)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_ahora)

    partido: Mapped[PartidoORM] = relationship(back_populates="predicciones")
