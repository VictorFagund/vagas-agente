"""Fontes além da Gupy: quadros públicos do Greenhouse e do Lever.

As duas APIs são oficiais e feitas para outros sites listarem as vagas (job board API),
sem login. Não têm busca: cada empresa tem seu quadro, listado em empresas.txt.
Devolvem vagas no mesmo formato de coleta.normalizar, com `fonte` preenchida.
"""
import html
import json
import re
import urllib.request
from datetime import datetime, timezone

from coleta import texto_limpo

# Ids das três fontes vivem na mesma coluna; um deslocamento por fonte evita colisão com os da Gupy
BASE_GREENHOUSE = 10**12
BASE_LEVER = 2 * 10**12

BRASIL = re.compile(r"\b(brasil|brazil|br|latam|latin america|s[ãa]o paulo|rio de janeiro|curitiba|"
                    r"belo horizonte|florian[óo]polis|porto alegre|recife|campinas)\b", re.I)
REMOTO = re.compile(r"remot|home ?office|anywhere|teletrabalho|100% online", re.I)


def _json(url: str, abrir=urllib.request.urlopen):
    with abrir(urllib.request.Request(url, headers={"Accept": "application/json"}), timeout=30) as r:
        return json.load(r)


def ler_empresas(caminho: str) -> list[tuple[str, str]]:
    """Linhas 'greenhouse quintoandar' ou 'lever ciandt'."""
    pares = []
    for l in open(caminho, encoding="utf-8"):
        partes = l.split("#")[0].split()
        if len(partes) == 2:
            pares.append((partes[0].lower(), partes[1]))
    return pares


def tipo_local_por_texto(local: str, titulo: str) -> str:
    """Greenhouse não tem campo de modelo de trabalho: decide pelo texto do local e do título."""
    t = f"{local} {titulo}"
    if re.search(r"h[íi]brid|hybrid", t, re.I):
        return "hybrid"
    so_remoto = re.fullmatch(r"\W*(remote|remoto|teletrabalho|home ?office|anywhere)\W*", local.strip(), re.I)
    if REMOTO.search(t) and (BRASIL.search(t) or so_remoto):
        return "remote"          # "Remoto" puro ou "Remote - Brazil"; "London | Remote" não
    return "on-site" if local else ""


def greenhouse(token: str, abrir=urllib.request.urlopen) -> list[dict]:
    dados = _json(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true", abrir)
    vagas = []
    for j in dados.get("jobs", []):
        local = (j.get("location") or {}).get("name") or ""
        vagas.append({
            "id": BASE_GREENHOUSE + int(j["id"]),
            "titulo": (j.get("title") or "").strip(),
            "empresa": token,
            "tipo_local": tipo_local_por_texto(local, j.get("title") or ""),
            "cidade": local,
            "publicada": (j.get("first_published") or j.get("updated_at") or "")[:10],
            "prazo": "",
            "url": j.get("absolute_url") or "",
            # o content vem com o HTML escapado uma vez a mais
            "descricao": texto_limpo(html.unescape(j.get("content") or "")),
            "termo": "",
            "fonte": "greenhouse",
        })
    return vagas


def lever(empresa: str, abrir=urllib.request.urlopen) -> list[dict]:
    dados = _json(f"https://api.lever.co/v0/postings/{empresa}?mode=json", abrir)
    vagas = []
    for j in dados:
        cat = j.get("categories") or {}
        secoes = "\n".join(f"{s.get('text', '')}\n{texto_limpo(s.get('content', ''))}" for s in j.get("lists") or [])
        modelo = (j.get("workplaceType") or "").lower()
        pais = (j.get("country") or "").upper()
        criada = j.get("createdAt")
        vagas.append({
            "id": BASE_LEVER + int(j["id"].replace("-", "")[:12], 16),
            "titulo": (j.get("text") or "").strip(),
            "empresa": empresa,
            # remoto fora do Brasil costuma exigir residência ou fuso de outro país
            "tipo_local": {"onsite": "on-site"}.get(modelo, modelo) if pais in ("", "BR") or modelo != "remote"
                          else f"remote-{pais.lower()}",
            "cidade": cat.get("location") or "",
            "publicada": datetime.fromtimestamp(criada / 1000, timezone.utc).strftime("%Y-%m-%d") if criada else "",
            "prazo": "",
            "url": j.get("hostedUrl") or "",
            "descricao": "\n".join(x for x in (j.get("descriptionPlain"), secoes, j.get("additionalPlain")) if x),
            "termo": "",
            "fonte": "lever",
        })
    return vagas


def coletar(fonte: str, quadro: str) -> list[dict]:
    return {"greenhouse": greenhouse, "lever": lever}[fonte](quadro)
