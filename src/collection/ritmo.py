"""Limitador de chamadas por hora, em janela móvel.

A Graph API em modo de desenvolvimento aceita cerca de 200 chamadas por hora por app. O limitador fica abaixo
disso (config/limiares.yaml: instagram_chamadas_por_hora) e conta só chamadas que vão à rede: respostas que saem
do cache não gastam limite.
"""
from __future__ import annotations

import time
from collections import deque
from typing import Callable


class LimiteLocalAtingido(RuntimeError):
    def __init__(self, segundos_para_liberar: float) -> None:
        super().__init__(f"Limite local de chamadas por hora atingido; libera em {segundos_para_liberar / 60:.0f} min")
        self.segundos_para_liberar = segundos_para_liberar


class LimitadorChamadas:
    def __init__(self, max_por_hora: int, esperar: bool = False, relogio: Callable[[], float] = time.monotonic,
                 dormir: Callable[[float], None] = time.sleep, janela_s: float = 3600.0,
                 avisar: Callable[[str], None] | None = None) -> None:
        self.max_por_hora = max_por_hora
        self.esperar = esperar
        self.relogio, self.dormir, self.janela_s = relogio, dormir, janela_s
        self.avisar = avisar or (lambda msg: None)
        self.chamadas: deque[float] = deque()

    def _limpar(self, agora: float) -> None:
        while self.chamadas and agora - self.chamadas[0] >= self.janela_s:
            self.chamadas.popleft()

    def antes_da_chamada(self) -> None:
        """Chamar antes de cada requisição à rede. Espera ou levanta LimiteLocalAtingido quando a janela está cheia."""
        agora = self.relogio()
        self._limpar(agora)
        if len(self.chamadas) >= self.max_por_hora:
            espera = self.janela_s - (agora - self.chamadas[0]) + 1
            if not self.esperar:
                raise LimiteLocalAtingido(espera)
            self.avisar(f"Limite de {self.max_por_hora} chamadas/hora: esperando {espera / 60:.0f} min")
            self.dormir(espera)
            agora = self.relogio()
            self._limpar(agora)
        self.chamadas.append(agora)

    @property
    def usadas(self) -> int:
        self._limpar(self.relogio())
        return len(self.chamadas)
