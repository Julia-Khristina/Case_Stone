"""Gravação da coleta em JSONL: o bruto fica imutável (data/raw) e os registros validados ao lado.

Reprocessar a base não exige coletar de novo, e o README pode mostrar exatamente o que veio de cada API.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel


def append_jsonl(path: str | Path, records: Iterable[Any]) -> int:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("a", encoding="utf-8") as file:
        for record in records:
            if isinstance(record, BaseModel):
                record = record.model_dump(mode="json")
            file.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    return [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]


def posts_com_midia_renovada(coleta: str | Path) -> list[dict[str, Any]]:
    """Posts da coleta com os links de mídia renovados por scripts/renovar_midia.py, quando existem.

    Os links do Instagram expiram em poucos dias; a renovação fica num arquivo à parte e a coleta original não muda.
    """
    coleta = Path(coleta)
    novos = {str(r["post_id"]): r for r in read_jsonl(coleta / "midia_renovada.jsonl")}
    posts = read_jsonl(coleta / "posts.jsonl")
    for p in posts:
        r = novos.get(str(p.get("post_id")))
        if r:
            p["media_url"] = r.get("media_url") or p.get("media_url")
            p["thumbnail_url"] = r.get("thumbnail_url") or p.get("thumbnail_url")
    return posts
