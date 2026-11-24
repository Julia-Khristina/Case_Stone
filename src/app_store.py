"""Estado do app (peças criadas, versões, decisões) em SQLite: vem com o Python e não exige servidor.

Cada peça guarda todas as versões e decisões (aprovar, pedir ajuste com motivo), para auditoria: quem decidiu o quê.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[1]
CAMINHO_PADRAO = ROOT / "data" / "app" / "boapauta.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS pecas (
    id TEXT PRIMARY KEY,
    criado_em TEXT NOT NULL,
    atualizado_em TEXT NOT NULL,
    data_agenda TEXT,
    horario TEXT,
    formato TEXT NOT NULL,
    segmento TEXT,
    objetivo TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('revisar', 'aprovada', 'ajuste', 'falhou')),
    atual TEXT NOT NULL,        -- JSON: versão atual (criativo, conferências, juiz, refs)
    historico TEXT NOT NULL     -- JSON: versões anteriores e decisões
);
CREATE TABLE IF NOT EXISTS playbooks (   -- guias detalhados (nome antigo da tabela mantido para não perder os já gerados)
    id TEXT PRIMARY KEY,
    inicio TEXT NOT NULL,
    fim TEXT NOT NULL,
    gerado_em TEXT NOT NULL,
    conteudo TEXT NOT NULL      -- JSON: seções, dicas, próxima semana, falhas e o HTML do e-mail
);
CREATE TABLE IF NOT EXISTS convites (
    plataforma TEXT NOT NULL,
    perfil TEXT NOT NULL,
    nome TEXT,
    nota INTEGER,
    adicionado_em TEXT NOT NULL,
    PRIMARY KEY (plataforma, perfil)
);
"""


class Store:
    def __init__(self, caminho: Path = CAMINHO_PADRAO) -> None:
        self.caminho = Path(caminho)
        self.caminho.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.caminho)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _linha(row: sqlite3.Row) -> dict[str, Any]:
        d = dict(row)
        d["atual"], d["historico"] = json.loads(d["atual"]), json.loads(d["historico"])
        return d

    def criar(self, formato: str, objetivo: str, atual: dict, segmento: Optional[str] = None,
              data_agenda: Optional[str] = None, horario: Optional[str] = None, status: str = "revisar") -> dict:
        agora = datetime.now().isoformat(timespec="seconds")
        peca_id = uuid.uuid4().hex[:10]
        with self._conn() as c:
            c.execute("INSERT INTO pecas VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (peca_id, agora, agora, data_agenda, horario, formato, segmento, objetivo, status,
                       json.dumps(atual, ensure_ascii=False), json.dumps([], ensure_ascii=False)))
        return self.obter(peca_id)

    def obter(self, peca_id: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM pecas WHERE id = ?", (peca_id,)).fetchone()
        return self._linha(row) if row else None

    def listar(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM pecas ORDER BY COALESCE(data_agenda, criado_em), criado_em").fetchall()
        return [self._linha(r) for r in rows]

    def convidar(self, plataforma: str, perfil: str, nome: str = "", nota: int | None = None) -> None:
        with self._conn() as c:
            c.execute("INSERT OR IGNORE INTO convites VALUES (?,?,?,?,?)",
                      (plataforma, perfil, nome, nota, datetime.now().isoformat(timespec="seconds")))

    def convites(self) -> list[dict]:
        with self._conn() as c:
            return [dict(r) for r in c.execute("SELECT * FROM convites ORDER BY adicionado_em").fetchall()]

    def salvar_guia(self, pb: dict) -> dict:
        pb_id = uuid.uuid4().hex[:10]
        with self._conn() as c:
            c.execute("INSERT INTO playbooks VALUES (?,?,?,?,?)",
                      (pb_id, pb["inicio"], pb["fim"], pb["gerado_em"], json.dumps(pb, ensure_ascii=False)))
        return {"id": pb_id, **pb}

    def guias(self) -> list[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT id, inicio, fim, gerado_em, conteudo FROM playbooks ORDER BY gerado_em DESC").fetchall()
        return [{"id": r["id"], **json.loads(r["conteudo"])} for r in rows]

    def guia(self, pb_id: str) -> Optional[dict]:
        return next((p for p in self.guias() if p["id"] == pb_id), None)

    def registrar(self, peca_id: str, status: str, decisao: dict, nova_versao: Optional[dict] = None) -> dict:
        """Guarda a decisão no histórico; se houver nova versão, a anterior vai para o histórico também."""
        peca = self.obter(peca_id)
        if peca is None:
            raise KeyError(peca_id)
        agora = datetime.now().isoformat(timespec="seconds")
        historico = peca["historico"] + [{**decisao, "em": agora}]
        atual = peca["atual"]
        if nova_versao is not None:
            historico.append({"versao_anterior": atual, "em": agora})
            atual = nova_versao
        with self._conn() as c:
            c.execute("UPDATE pecas SET status = ?, atual = ?, historico = ?, atualizado_em = ? WHERE id = ?",
                      (status, json.dumps(atual, ensure_ascii=False), json.dumps(historico, ensure_ascii=False), agora, peca_id))
        return self.obter(peca_id)
