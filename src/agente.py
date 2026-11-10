"""Agente de busca de vaga: coleta na Gupy, descarta por regra, avalia com IA e gera relatório.

Uso (da pasta vagas-agente):
    .venv/Scripts/python src/agente.py              # ciclo completo
    .venv/Scripts/python src/agente.py --limite 10  # a IA avalia só as 10 vagas mais parecidas com o perfil
    .venv/Scripts/python src/agente.py --relatorio  # só refaz o relatório
"""
import argparse
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
sys.path.insert(0, AQUI)

import banco      # noqa: E402
import coleta     # noqa: E402
import fontes     # noqa: E402
import funil      # noqa: E402
import relatorio  # noqa: E402


def ler_env(caminho: str) -> dict:
    env = {}
    if os.path.exists(caminho):
        for linha in open(caminho, encoding="utf-8"):
            chave, sep, valor = linha.strip().partition("=")
            if sep and not chave.startswith("#"):
                env[chave.strip()] = valor.strip()
    return {**env, **{k: v for k, v in os.environ.items() if k in env}}


def ler_buscas(caminho: str) -> list[str]:
    return [l.strip() for l in open(caminho, encoding="utf-8") if l.strip() and not l.startswith("#")]


def _lote(con, rotulo: str, vagas: list[dict], vistas: set, descartes: Counter, agora: str) -> int:
    """Guarda as vagas ainda não vistas, já com o veredito das regras. Devolve quantas eram novas."""
    novas = 0
    for v in vagas:
        if v["id"] in vistas:
            continue
        vistas.add(v["id"])
        if banco.ja_vista(con, v["id"]):
            continue
        motivo = coleta.filtro_regras(v)
        banco.guardar_vaga(con, v, motivo, agora)
        novas += 1
        descartes[(motivo or "passou").split(" (")[0]] += 1
    print(f"  [coleta] {rotulo}: {len(vagas)} vagas, {novas} novas")
    return novas


def coletar(con, termos: list[str], quadros: list[tuple[str, str]], agora: str) -> tuple[int, int, Counter]:
    vistas, novas, descartes = set(), 0, Counter()
    for termo in termos:
        try:
            vagas = [coleta.normalizar(j, termo) for j in coleta.buscar(termo)]
        except Exception as e:  # uma busca que falha não derruba as outras
            print(f"  [coleta] gupy '{termo}': ERRO {e}")
            continue
        novas += _lote(con, f"gupy '{termo}'", vagas, vistas, descartes, agora)
    for fonte, quadro in quadros:
        try:
            vagas = fontes.coletar(fonte, quadro)
        except Exception as e:
            print(f"  [coleta] {fonte} {quadro}: ERRO {e}")
            continue
        novas += _lote(con, f"{fonte} {quadro}", vagas, vistas, descartes, agora)
    con.commit()
    return len(vistas), novas, descartes


def ranquear(con, perfil: str) -> int:
    """Dá a cada vaga nova uma similaridade com o bloco 'Busca' do perfil. Local, sem cota."""
    linhas = banco.sem_similaridade(con)
    if not linhas:
        return 0
    sims = funil.Ranqueador().similaridades(
        funil.consulta_do_perfil(perfil), [funil.pedacos_para_embedding(r["titulo"], r["descricao"]) for r in linhas])
    banco.guardar_similaridades(con, [(round(s, 4), r["id"]) for s, r in zip(sims, linhas)])
    con.commit()
    return len(linhas)


def espera_da_cota(erro: str) -> float | None:
    """Segundos que a Groq manda esperar ("try again in 6m25.3s"), ou None se não disser."""
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?([\d.]+)s", erro)
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + float(m.group(3)) if m else None


def avaliar(con, perfil: str, env: dict, limite: int | None, agora: str,
            esperar_cota: bool = False) -> tuple[int, int, int]:
    from ia import Avaliador
    av = Avaliador(env)
    fila = banco.pendentes(con)[: limite or None]
    feitas = erros = tokens = 0
    for i, v in enumerate(fila, 1):
        try:
            r, seg, tok = av.avaliar(perfil, dict(v))
        except Exception as e:
            if "per day" in str(e) and esperar_cota:
                # a cota diária é uma janela móvel de 24 h: vai liberando aos poucos
                espera = min(espera_da_cota(str(e)) or 600, 3600) + 5
                print(f"  [ia] cota diária no fim; esperando {espera / 60:.0f} min")
                time.sleep(espera)
                try:
                    r, seg, tok = av.avaliar(perfil, dict(v))
                except Exception as e2:
                    e = e2
                else:
                    e = None
            if e is not None:
                erros += 1
                print(f"  [ia] {i}/{len(fila)} ERRO em {v['id']}: {str(e)[:300]}")
                if "per day" in str(e) and not esperar_cota:  # as restantes ficam para a próxima execução
                    print("  [ia] cota diária esgotada; parando")
                    break
                continue
        banco.guardar_avaliacao(con, v["id"], r, av.modelo, seg, tok, agora)
        con.commit()
        feitas += 1
        tokens += tok
        print(f"  [ia] {i}/{len(fila)} {r['nota']:>3}  {v['titulo'][:60]} | {v['empresa'][:30]}")
    return feitas, erros, tokens


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limite", type=int, default=40,
                   help="quantas vagas do topo do ranqueamento a IA avalia nesta execução (padrão 40)")
    p.add_argument("--relatorio", action="store_true", help="só refaz o relatório")
    p.add_argument("--sem-ia", action="store_true", help="coleta e filtra, sem avaliar")
    p.add_argument("--esperar-cota", action="store_true",
                   help="quando a cota diária acabar, espera ela liberar em vez de parar (para rodar de madrugada)")
    a = p.parse_args()

    agora = datetime.now().strftime("%Y-%m-%d %H:%M")
    con = banco.abrir(os.path.join(RAIZ, "data", "vagas.db"))

    if not a.relatorio:
        t0 = time.time()
        total, novas, descartes = coletar(con, ler_buscas(os.path.join(RAIZ, "buscas.txt")),
                                          fontes.ler_empresas(os.path.join(RAIZ, "empresas.txt")), agora)
        print(f"[coleta] {total} vagas distintas, {novas} novas: {dict(descartes)}")
        arq = os.path.join(RAIZ, "perfil.md")
        if not os.path.exists(arq):  # primeira execução: copie perfil.exemplo.md para perfil.md e edite
            print("[aviso] perfil.md não existe; usando perfil.exemplo.md")
            arq = os.path.join(RAIZ, "perfil.exemplo.md")
        perfil = open(arq, encoding="utf-8").read()
        print(f"[funil] {ranquear(con, perfil)} vagas ranqueadas por embedding")
        feitas = erros = tokens = 0
        if not a.sem_ia:
            feitas, erros, tokens = avaliar(con, perfil, ler_env(os.path.join(RAIZ, ".env")), a.limite, agora, a.esperar_cota)
        con.execute("INSERT INTO execucoes VALUES (?,?,?,?,?,?,?,?)",
                    (agora, total, novas, novas - descartes.get("passou", 0), feitas, erros,
                     round(time.time() - t0, 1), tokens))
        con.commit()
        print(f"[ia] {feitas} avaliadas, {erros} erros, {tokens} tokens")

    saida = relatorio.gerar(con, os.path.join(RAIZ, "saida"))
    print(f"[relatorio] {saida}")


if __name__ == "__main__":
    main()
