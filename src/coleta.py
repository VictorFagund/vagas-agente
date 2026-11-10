"""Coleta de vagas na API pública da Gupy e filtro por regras fixas.

A API é a mesma que o portal.gupy.io usa para listar vagas a qualquer visitante:
sem login, sem credencial. Paginamos por offset e paramos quando a página vem incompleta.
"""
import html
import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

API = "https://portal.gupy.io/api/job-search/jobs"
POR_PAGINA = 100
OFFSET_MAX = 1000          # trava de segurança por termo
PAUSA = 0.3                # segundos entre páginas, para não martelar a API

# Título com estas palavras sai antes de gastar IA. Nível acima do dele ou fora da área.
FORA = [
    r"\bs[eê]nior\b", r"\bsr\.?\b", r"\bespecialista\b", r"\bcoordenador", r"\bgerente\b",
    r"\bhead\b", r"\blead\b", r"\bl[ií]der\b", r"\bdiretor", r"\bsupervisor",
    r"\bvendedor", r"\bcomercial\b", r"\bsdr\b", r"\bcloser\b", r"\bjovem aprendiz\b",
    r"\baprendiz\b", r"\bbanco de talentos\b", r"\btalent pool\b", r"\bgeneral interest\b",
    r"\balways hiring\b", r"\bstaff\b", r"\bprincipal\b", r"\biii\b", r"\biv\b", r"\bmanager\b",
]


def buscar(termo: str, abrir=urllib.request.urlopen) -> list[dict]:
    vagas, offset = [], 0
    while offset <= OFFSET_MAX:
        url = f"{API}?{urllib.parse.urlencode({'jobName': termo, 'limit': POR_PAGINA, 'offset': offset})}"
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with abrir(req, timeout=30) as r:
            dados = json.load(r).get("data", [])
        vagas.extend(dados)
        if len(dados) < POR_PAGINA:
            break
        offset += POR_PAGINA
        time.sleep(PAUSA)
    return vagas


def texto_limpo(descricao_html: str) -> str:
    t = re.sub(r"<(br|/p|/li|/h\d|/div)[^>]*>", "\n", descricao_html or "")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"[ \t\xa0]+", " ", t)
    return "\n".join(l.strip() for l in t.splitlines() if l.strip())


def normalizar(j: dict, termo: str) -> dict:
    return {
        "id": j["id"],
        "titulo": (j.get("name") or "").strip(),
        "empresa": (j.get("careerPageName") or "").strip(),
        "tipo_local": j.get("workplaceType") or "",
        "cidade": " / ".join(x for x in (j.get("city"), j.get("state")) if x),
        "publicada": (j.get("publishedDate") or "")[:10],
        "prazo": (j.get("applicationDeadline") or "")[:10],
        "url": j.get("jobUrl") or "",
        "descricao": texto_limpo(j.get("description") or ""),
        "termo": termo,
    }


DIAS_SEM_PRAZO = 90


def _dias_antes(dia: str, n: int) -> str:
    return (datetime.strptime(dia, "%Y-%m-%d") - timedelta(days=n)).strftime("%Y-%m-%d")


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def filtro_regras(v: dict, hoje: str | None = None) -> str | None:
    """Devolve o motivo de descarte, ou None se a vaga segue para a IA."""
    hoje = hoje or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if v["tipo_local"] != "remote":
        return f"não é remota ({v['tipo_local'] or 'sem tipo'})"
    if v["prazo"] and v["prazo"] < hoje:
        return f"prazo encerrado ({v['prazo']})"
    # A API não diz se a vaga fechou: sem prazo e publicada há meses, quase sempre já encerrou
    if not v["prazo"] and v.get("publicada") and v["publicada"] < _dias_antes(hoje, DIAS_SEM_PRAZO):
        return f"sem prazo e antiga ({v['publicada']})"
    titulo = v["titulo"].lower()
    for padrao in FORA:
        achou = re.search(padrao, titulo) or re.search(padrao, _sem_acento(titulo))
        if achou:
            return f"título fora do perfil ({achou.group(0)})"
    return None
