"""Vagas com nota alta que ainda não foram avisadas. Feito para automação (n8n, cron).

    .venv/Scripts/python src/novas.py              # imprime JSON (não marca nada)
    .venv/Scripts/python src/novas.py --nota 80    # corte diferente (padrão 70)
    .venv/Scripts/python src/novas.py --marcar 1,2 # marca como avisadas, depois que o envio deu certo

Saída (uma linha de JSON): {"total": N, "mensagem": "texto pronto para Telegram/e-mail", "vagas": [...]}
Uma vaga só é avisada uma vez (tabela `avisadas`) e vaga com prazo vencido não entra.
"""
import argparse
import json
import os
import sys
from datetime import date, datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import banco  # noqa: E402


def pendentes(con, nota_min: int, hoje: str) -> list[dict]:
    con.execute("CREATE TABLE IF NOT EXISTS avisadas (id INTEGER PRIMARY KEY, em TEXT)")
    linhas = con.execute(
        """SELECT v.id, v.titulo, v.empresa, v.url, v.prazo, a.nota, a.motivo
           FROM avaliacoes a JOIN vagas v USING(id)
           WHERE a.nota >= ? AND v.id NOT IN (SELECT id FROM avisadas)
             AND v.url NOT LIKE '%inactive%'
             AND (v.prazo IS NULL OR v.prazo = '' OR substr(v.prazo, 1, 10) >= ?)
           ORDER BY a.nota DESC""", (nota_min, hoje)).fetchall()
    return [dict(zip(("id", "titulo", "empresa", "url", "prazo", "nota", "motivo"), r)) for r in linhas]


def mensagem(vagas: list[dict]) -> str:
    if not vagas:
        return ""
    partes = [f"{len(vagas)} vaga(s) nova(s) com nota alta:"]
    for v in vagas[:10]:
        prazo = f" · até {v['prazo'][8:10]}/{v['prazo'][5:7]}" if v["prazo"] else ""
        partes.append(f"\n{v['nota']} · {v['titulo']} — {v['empresa']}{prazo}\n{v['url']}")
    if len(vagas) > 10:
        partes.append(f"\n…e mais {len(vagas) - 10} no relatório.")
    return "\n".join(partes)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--nota", type=int, default=70)
    p.add_argument("--marcar", help="ids separados por vírgula: marca como avisadas e sai")
    a = p.parse_args()
    con = banco.abrir(os.path.join(RAIZ, "data", "vagas.db"))
    vagas = pendentes(con, a.nota, date.today().isoformat())
    sys.stdout.reconfigure(encoding="utf-8")
    if a.marcar is not None:
        agora = datetime.now().strftime("%Y-%m-%d %H:%M")
        ids = [int(x) for x in a.marcar.split(",") if x.strip()]
        con.executemany("INSERT OR IGNORE INTO avisadas VALUES (?, ?)", [(i, agora) for i in ids])
        con.commit()
        print(json.dumps({"marcadas": len(ids)}))
        return
    print(json.dumps({"total": len(vagas), "mensagem": mensagem(vagas), "vagas": vagas}, ensure_ascii=False))


if __name__ == "__main__":
    main()
