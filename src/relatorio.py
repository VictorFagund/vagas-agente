"""Relatório HTML de uma página: vagas avaliadas, da melhor nota para a pior."""
import html
import json
import os
from datetime import datetime

CSS = """
:root{--bg:#f6f5f2;--card:#fff;--tx:#1d1d1f;--mut:#6b6b70;--line:#e3e1dc;--ok:#1f7a4d;--mid:#9a6b00;--low:#a3352b;--chip:#efede8}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--card:#1e1e21;--tx:#ececee;--mut:#9a9aa1;--line:#2e2e33;--ok:#4cc38a;--mid:#e0b04a;--low:#ef7a6d;--chip:#2a2a2e}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font:15px/1.5 system-ui,Segoe UI,sans-serif}
main{max-width:860px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--mut);margin:0 0 20px}.stats{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:24px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:8px 12px}
.stat b{display:block;font-size:20px}.stat span{color:var(--mut);font-size:12px}
h2{font-size:15px;color:var(--mut);font-weight:600;margin:28px 0 10px;text-transform:uppercase;letter-spacing:.04em}
.v{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin-bottom:10px;display:grid;grid-template-columns:52px 1fr;gap:12px}
.n{font-size:22px;font-weight:700;text-align:center}.n.ok{color:var(--ok)}.n.mid{color:var(--mid)}.n.low{color:var(--low)}
.t a{color:var(--tx);font-weight:600;text-decoration:none}.t a:hover{text-decoration:underline}
.meta{color:var(--mut);font-size:13px}.motivo{margin:6px 0}
.chips{display:flex;flex-wrap:wrap;gap:4px;margin-top:4px}.chip{background:var(--chip);border-radius:6px;padding:1px 7px;font-size:12.5px}
.chip.f{border:1px dashed var(--line);background:none}.novo{color:var(--ok);font-size:12px;font-weight:600;margin-left:6px}
"""


def _classe(nota: int) -> str:
    return "ok" if nota >= 70 else "mid" if nota >= 50 else "low"


def _cartao(r, hoje: str) -> str:
    e = html.escape
    tem = "".join(f'<span class="chip">✓ {e(x)}</span>' for x in json.loads(r["tem"]))
    falta = "".join(f'<span class="chip f">✗ {e(x)}</span>' for x in json.loads(r["falta"]))
    novo = '<span class="novo">NOVA</span>' if (r["vista_em"] or "").startswith(hoje) else ""
    prazo = f" · até {r['prazo'][8:10]}/{r['prazo'][5:7]}" if r["prazo"] else ""
    return (
        f'<div class="v"><div class="n {_classe(r["nota"])}">{r["nota"]}</div><div>'
        f'<div class="t"><a href="{e(r["url"])}" target="_blank" rel="noopener">{e(r["titulo"])}</a>{novo}</div>'
        f'<div class="meta">{e(r["empresa"])} ({e(r["fonte"] or "gupy")}) · {e(r["nivel"])} · {e(r["area"])} · inglês: {e(r["ingles"])}{prazo}</div>'
        f'<div class="motivo">{e(r["motivo"])}</div><div class="chips">{tem}{falta}</div></div></div>'
    )


def gerar(con, pasta: str) -> str:
    hoje = datetime.now().strftime("%Y-%m-%d")
    linhas = con.execute(
        "SELECT v.*, a.* FROM avaliacoes a JOIN vagas v ON v.id=a.id "
        "WHERE (v.prazo='' AND v.publicada>=date(?, '-90 days')) OR v.prazo>=? "
        "ORDER BY a.nota DESC, v.publicada DESC", (hoje, hoje)
    ).fetchall()
    total = con.execute("SELECT COUNT(*) FROM vagas").fetchone()[0]
    descartadas = con.execute("SELECT COUNT(*) FROM vagas WHERE descarte IS NOT NULL").fetchone()[0]
    boas = sum(1 for r in linhas if r["nota"] >= 70)

    grupos = [("Vale candidatar (70+)", [r for r in linhas if r["nota"] >= 70]),
              ("Talvez (50 a 69)", [r for r in linhas if 50 <= r["nota"] < 70]),
              ("Não serve (abaixo de 50)", [r for r in linhas if r["nota"] < 50])]
    corpo = "".join(
        f"<h2>{t} · {len(g)}</h2>" + "".join(_cartao(r, hoje) for r in g) for t, g in grupos if g
    )
    stats = "".join(f'<div class="stat"><b>{n}</b><span>{t}</span></div>' for n, t in [
        (total, "vagas lidas"), (descartadas, "descartadas por regra"), (len(linhas), "avaliadas pela IA"),
        (boas, "com nota 70+")])
    pagina = (
        f'<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>Vagas · {hoje}</title>'
        f'<style>{CSS}</style></head><body><main><h1>Vagas remotas que servem</h1>'
        f'<p class="sub">Gupy, Greenhouse e Lever · atualizado em {datetime.now().strftime("%d/%m/%Y %H:%M")}</p>'
        f'<div class="stats">{stats}</div>{corpo}</main></body></html>'
    )
    os.makedirs(pasta, exist_ok=True)
    caminho = os.path.join(pasta, "vagas.html")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(pagina)
    return caminho
