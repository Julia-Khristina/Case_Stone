"""Camada 3: sorteia posts para rotulagem manual às cegas (sem a resposta da IA e sem dizer se é top ou controle).

Uso: python scripts/preparar_validacao.py --coleta data/raw/2026-11-22 [--n 50]

Gera data/validacao/rotulagem_manual.csv. Preencha as colunas em branco seguindo data/validacao/LEIA-ME.md e
depois rode scripts/validar_rotulos.py para medir a concordância (kappa) entre você e a IA, campo a campo.
Não sobrescreve uma planilha existente, para não apagar rótulos já feitos.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.collection.storage import read_jsonl  # noqa: E402

CAMPOS = ["tema_principal", "tipo_hook", "tipo_cta", "convite_participacao", "mensagem_generica", "patrocinado"]
LEIA_ME = """# Rotulagem manual (camada 3)

Abra cada post pelo link, leia o título e o texto e preencha as colunas em branco. **Não consulte a resposta da IA.**
Use exatamente um dos valores abaixo. Se ficar em dúvida entre dois, escolha o que melhor descreve o post inteiro.

| Coluna | Valores |
|---|---|
| tema_principal | vendas, financas, marketing, atendimento, gestao, motivacao, ferramentas, historia_de_empreendedor, receita_ou_tecnica, outro |
| tipo_hook | pergunta, promessa, dor, numero, polemica, curiosidade, historia, nenhum (como o título ou a primeira frase prende) |
| tipo_cta | comentar, salvar, compartilhar, link, dm, seguir, comprar, nenhum (o que o post pede ao público) |
| convite_participacao | sim, nao (convida a comentar, contar a própria história ou interagir?) |
| mensagem_generica | sim, nao (frase motivacional genérica, sem dor, número ou exemplo concreto?) |
| patrocinado | sim, nao (sinal de parceria paga: #publi, #ad, marca patrocinadora) |

Leva cerca de 1 hora para 50 posts. Quando terminar, rode `python scripts/validar_rotulos.py`.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Sorteia posts para a validação manual às cegas")
    parser.add_argument("--coleta", required=True)
    parser.add_argument("--n", type=int, default=50)
    parser.add_argument("--semente", type=int, default=42)
    args = parser.parse_args()

    destino = ROOT / "data" / "validacao" / "rotulagem_manual.csv"
    if destino.exists():
        print(f"{destino} já existe: não sobrescrevo para não apagar rótulos feitos. Apague-o se quiser sortear de novo.")
        return 1
    rotulados = {str(r["post_id"]) for r in read_jsonl(ROOT / "data" / "processed" / "rotulos_texto.jsonl")}
    scores = pd.read_csv(ROOT / "data" / "processed" / "scores.csv", dtype={"post_id": str}, low_memory=False)
    posts = pd.DataFrame(read_jsonl(Path(args.coleta) / "posts.jsonl"))
    posts["post_id"] = posts["post_id"].astype(str)                # ids do Instagram são longos: sempre como texto
    base = scores[scores["grupo"].isin(["top", "controle"]) & scores["post_id"].isin(rotulados)]
    base = base[["plataforma", "post_id", "grupo"]].merge(
        posts[["plataforma", "post_id", "link", "titulo", "legenda"]], on=["plataforma", "post_id"])

    # Estratifica por plataforma e grupo, para a validação cobrir os quatro recortes
    por_estrato = max(1, -(-args.n // 4))   # arredonda para cima: o TAPI pede no mínimo 50
    amostra = pd.concat([g.sample(min(len(g), por_estrato), random_state=args.semente)
                         for _, g in base.groupby(["plataforma", "grupo"])])
    amostra = amostra.sample(frac=1, random_state=args.semente)          # embaralha: a ordem não revela o grupo
    planilha = amostra[["post_id", "plataforma", "link", "titulo"]].copy()
    planilha["texto"] = amostra["legenda"].fillna("").map(lambda t: " ".join(str(t).split())[:400])
    for campo in CAMPOS:
        planilha[campo] = ""
    destino.parent.mkdir(parents=True, exist_ok=True)
    planilha.to_csv(destino, index=False, encoding="utf-8-sig")
    (destino.parent / "LEIA-ME.md").write_text(LEIA_ME, encoding="utf-8")
    print(f"{len(planilha)} posts sorteados em {destino}")
    print(f"Instruções: {destino.parent / 'LEIA-ME.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
