"""Bancada: mede quanto a nota da IA concorda com o julgamento do candidato.

    .venv/Scripts/python src/bancada.py sortear 30   # cria bancada/rotulos.csv (às cegas, sem a nota da IA)
    .venv/Scripts/python src/bancada.py medir        # compara as respostas dele com a IA

No CSV, a coluna `sua_resposta` recebe sim, talvez ou nao: "eu me candidataria?".
A nota da IA vira classe pelos mesmos cortes do relatório: 70+ sim, 50-69 talvez, abaixo de 50 nao.
"""
import csv
import os
import random
import sys
from collections import Counter

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)
import banco  # noqa: E402

CSV = os.path.join(RAIZ, "bancada", "rotulos.csv")
CLASSES = ["sim", "talvez", "nao"]


def classe(nota: int) -> str:
    return "sim" if nota >= 70 else "talvez" if nota >= 50 else "nao"


def sortear(con, n: int, semente: int = 7):
    """Amostra estratificada pela classe da IA, para a bancada não ser só de 'nao'."""
    linhas = con.execute("SELECT v.id, v.titulo, v.empresa, v.url, a.nota FROM avaliacoes a JOIN vagas v USING(id)").fetchall()
    por_classe = {c: [r for r in linhas if classe(r["nota"]) == c] for c in CLASSES}
    rnd = random.Random(semente)
    escolhidas = []
    for c in CLASSES:
        rnd.shuffle(por_classe[c])
        escolhidas += por_classe[c][: n // 3]
    sobra = [r for r in linhas if r not in escolhidas]
    rnd.shuffle(sobra)
    escolhidas += sobra[: n - len(escolhidas)]
    rnd.shuffle(escolhidas)
    os.makedirs(os.path.dirname(CSV), exist_ok=True)
    with open(CSV, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: o Excel abre acentos certo
        w = csv.writer(f, delimiter=";")
        w.writerow(["id", "titulo", "empresa", "url", "sua_resposta"])
        for r in escolhidas:
            w.writerow([r["id"], r["titulo"], r["empresa"], r["url"], ""])
    print(f"{len(escolhidas)} vagas em {CSV}")


def kappa(pares: list[tuple[str, str]]) -> float:
    n = len(pares)
    obs = sum(a == b for a, b in pares) / n
    ca, cb = Counter(a for a, _ in pares), Counter(b for _, b in pares)
    esp = sum(ca[c] * cb[c] for c in CLASSES) / (n * n)
    return (obs - esp) / (1 - esp) if esp < 1 else 1.0


def medir(con) -> dict:
    notas = {r["id"]: r["nota"] for r in con.execute("SELECT id, nota FROM avaliacoes")}
    pares, casos = [], []
    with open(CSV, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            humano = (r["sua_resposta"] or "").strip().lower().replace("ã", "a")
            if humano not in CLASSES or int(r["id"]) not in notas:
                continue
            ia = classe(notas[int(r["id"])])
            pares.append((humano, ia))
            casos.append((humano, ia, notas[int(r["id"])], r["titulo"]))
    if not pares:
        print("Nenhuma resposta preenchida ainda.")
        return {}
    graves = [c for c in casos if {c[0], c[1]} == {"sim", "nao"}]
    perdidas = [c for c in casos if c[0] == "sim" and c[1] != "sim"]
    res = {
        "n": len(pares),
        "concordancia": sum(a == b for a, b in pares) / len(pares),
        "kappa": kappa(pares),
        "erros_graves": len(graves),
        "boas_perdidas": len(perdidas),
    }
    print(f"{res['n']} vagas rotuladas")
    print(f"concordância exata: {res['concordancia']:.0%}   kappa de Cohen: {res['kappa']:.2f}")
    print(f"erros graves (um disse sim, o outro não): {res['erros_graves']}")
    print(f"vagas que você quer e a IA não pôs em 'sim': {res['boas_perdidas']}")
    print("\nmatriz (linha = você, coluna = IA):")
    print("          " + "".join(f"{c:>8}" for c in CLASSES))
    for h in CLASSES:
        print(f"{h:>8}  " + "".join(f"{sum(1 for p in pares if p == (h, i)):>8}" for i in CLASSES))
    for h, i, nota, t in graves + [c for c in perdidas if c not in graves]:
        print(f"  você={h:<6} IA={i:<6} ({nota})  {t[:70]}")
    return res


if __name__ == "__main__":
    con = banco.abrir(os.path.join(RAIZ, "data", "vagas.db"))
    if sys.argv[1:2] == ["sortear"]:
        sortear(con, int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif sys.argv[1:2] == ["medir"]:
        medir(con)
    else:
        print(__doc__)
