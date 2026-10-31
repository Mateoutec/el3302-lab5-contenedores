"""Acceso de la capa de presentación a los servicios (creados en main.py)."""
from __future__ import annotations

from fastapi import Request

from app.negocio.servicios import ServicioPartidos, ServicioPredicciones


def servicio_partidos(request: Request) -> ServicioPartidos:
    return request.app.state.servicio_partidos


def servicio_predicciones(request: Request) -> ServicioPredicciones:
    return request.app.state.servicio_predicciones
