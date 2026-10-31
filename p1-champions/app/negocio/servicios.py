"""Lógica de negocio: sincronización de partidos y reglas de las predicciones."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from sqlalchemy.orm import sessionmaker

from app.datos.cliente_api_partidos import ClienteApiPartidos, ErrorApiPartidos
from app.datos.repositorios import RepositorioPartidos, RepositorioPredicciones
from app.dominio.entidades import EstadoPartido, Partido, Prediccion, Resultado

log = logging.getLogger(__name__)

MAX_GOLES = 20
PUNTOS_MARCADOR_EXACTO = 3
PUNTOS_RESULTADO = 1


class ErrorNegocio(Exception):
    """Error de validación que se muestra al usuario."""


class PartidoNoEncontrado(ErrorNegocio):
    pass


class PrediccionInvalida(ErrorNegocio):
    pass


@dataclass
class ResumenSincronizacion:
    recibidos: int
    nuevos: int
    actualizados: int


class ServicioPartidos:
    def __init__(self, fabrica_sesiones: sessionmaker, cliente: ClienteApiPartidos, competicion: str, temporada: str = ""):
        self.fabrica_sesiones = fabrica_sesiones
        self.cliente = cliente
        self.competicion = competicion
        self.temporada = temporada

    def sincronizar(self) -> ResumenSincronizacion:
        """Consume la API y guarda (o actualiza) todos los partidos en la base de datos."""
        partidos = self.cliente.obtener_partidos(self.competicion, self.temporada)
        with self.fabrica_sesiones.begin() as sesion:
            nuevos, actualizados = RepositorioPartidos(sesion).guardar_o_actualizar(partidos)
        resumen = ResumenSincronizacion(len(partidos), nuevos, actualizados)
        log.info("Sincronización: %s", resumen)
        return resumen

    def sincronizar_con_reintentos(self, intentos: int, espera_s: float = 3.0) -> ResumenSincronizacion | None:
        for intento in range(1, intentos + 1):
            try:
                return self.sincronizar()
            except ErrorApiPartidos as error:
                log.warning("Intento %d/%d de sincronización falló: %s", intento, intentos, error)
                if intento < intentos:
                    time.sleep(espera_s)
        log.error("No se pudo sincronizar; la app sigue con los partidos ya guardados.")
        return None

    def listar(self, estado: EstadoPartido | None = None, jornada: int | None = None) -> list[Partido]:
        with self.fabrica_sesiones() as sesion:
            return RepositorioPartidos(sesion).listar(estado, jornada)

    def obtener(self, partido_id: int) -> Partido:
        with self.fabrica_sesiones() as sesion:
            partido = RepositorioPartidos(sesion).obtener(partido_id)
        if partido is None:
            raise PartidoNoEncontrado(f"No existe el partido {partido_id}")
        return partido

    def jornadas(self) -> list[int]:
        with self.fabrica_sesiones() as sesion:
            return RepositorioPartidos(sesion).jornadas()

    def total(self) -> int:
        with self.fabrica_sesiones() as sesion:
            return RepositorioPartidos(sesion).contar()

    def predicciones_por_partido(self) -> dict[int, int]:
        with self.fabrica_sesiones() as sesion:
            return RepositorioPredicciones(sesion).contar_por_partido()


class ServicioPredicciones:
    def __init__(self, fabrica_sesiones: sessionmaker):
        self.fabrica_sesiones = fabrica_sesiones

    def registrar(self, partido_id: int, autor: str, resultado: Resultado | str,
                  goles_local: int, goles_visitante: int) -> Prediccion:
        autor = (autor or "").strip()
        if not autor:
            raise PrediccionInvalida("Indica tu nombre para registrar la predicción.")
        if len(autor) > 60:
            raise PrediccionInvalida("El nombre no puede tener más de 60 caracteres.")
        try:
            resultado = Resultado(resultado)
        except ValueError:
            raise PrediccionInvalida("El resultado debe ser LOCAL, EMPATE o VISITANTE.") from None
        for goles in (goles_local, goles_visitante):
            if not isinstance(goles, int) or goles < 0 or goles > MAX_GOLES:
                raise PrediccionInvalida(f"Los goles deben ser enteros entre 0 y {MAX_GOLES}.")
        if Resultado.desde_marcador(goles_local, goles_visitante) != resultado:
            raise PrediccionInvalida(
                f"El marcador {goles_local}-{goles_visitante} no corresponde al resultado elegido ({resultado.value})."
            )

        with self.fabrica_sesiones.begin() as sesion:
            partido = RepositorioPartidos(sesion).obtener(partido_id)
            if partido is None:
                raise PartidoNoEncontrado(f"No existe el partido {partido_id}")
            if not partido.admite_predicciones:
                raise PrediccionInvalida("Solo se puede predecir partidos que aún no han comenzado.")
            creada = RepositorioPredicciones(sesion).crear(
                Prediccion(partido_id=partido_id, autor=autor, resultado=resultado,
                           goles_local=goles_local, goles_visitante=goles_visitante)
            )
        creada.partido = partido
        return creada

    def listar(self, partido_id: int | None = None) -> list[Prediccion]:
        with self.fabrica_sesiones() as sesion:
            predicciones = RepositorioPredicciones(sesion).listar(partido_id)
        for prediccion in predicciones:
            prediccion.puntos = calcular_puntos(prediccion)
        return predicciones


def calcular_puntos(prediccion: Prediccion) -> int | None:
    """3 puntos por marcador exacto, 1 por acertar ganador/empate, 0 si falla.
    None mientras el partido no haya terminado."""
    partido = prediccion.partido
    if partido is None or partido.resultado is None:
        return None
    if (prediccion.goles_local, prediccion.goles_visitante) == (partido.goles_local, partido.goles_visitante):
        return PUNTOS_MARCADOR_EXACTO
    if prediccion.resultado == partido.resultado:
        return PUNTOS_RESULTADO
    return 0
