"""Etapas baratas do funil, antes da IA: recorte do texto e ranqueamento por embedding.

O embedding roda local (fastembed, ONNX, sem GPU) e não gasta cota de API. Ele só ORDENA;
quem dá a nota continua sendo a IA, e só para as vagas do topo.
"""
import re
import unicodedata

MODELO_EMBEDDING = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# Títulos de seção. Comparados sem acento e em minúsculas, no começo de uma linha curta.
SECOES_UTEIS = ["requisito", "qualifica", "o que esperamos", "o que buscamos", "o que voce precisa",
                "o que procuramos", "responsabilidade", "atribuic", "atividade", "o que voce vai fazer",
                "o que voce fara", "seu dia a dia", "desafio", "diferencia", "desejave", "conhecimento",
                "experiencia", "perfil", "competencia", "habilidade", "stack", "tecnologia", "sobre a vaga",
                "descricao da vaga", "missao do cargo"]
SECOES_INUTEIS = ["beneficio", "sobre a empresa", "sobre nos", "quem somos", "nossa historia",
                  "etapas", "processo seletivo", "informacoes adicionais", "remuneracao e beneficio",
                  "o que oferecemos", "por que trabalhar", "nossos valores", "diversidade", "local de trabalho"]


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


# A Gupy monta toda vaga com as mesmas seções fixas, e o HTML costuma colar o título no texto
# ("Responsabilidades e atribuiçõesCompor o time..."), então elas são achadas por texto, não por linha.
GUPY_INICIO = "Responsabilidades e atribuições"
GUPY_REQUISITOS = "Requisitos e qualificações"
GUPY_FIM = "Informações adicionais"


def secoes_gupy(descricao: str) -> tuple[str, str] | None:
    """(responsabilidades, requisitos) de uma vaga da Gupy, ou None se o texto não segue o modelo."""
    i, r = descricao.find(GUPY_INICIO), descricao.find(GUPY_REQUISITOS)
    if r < 0:
        return None
    f = descricao.find(GUPY_FIM, r)
    resp = descricao[i + len(GUPY_INICIO):r] if 0 <= i < r else ""
    req = descricao[r + len(GUPY_REQUISITOS):f if f > 0 else None]
    return resp.strip(), req.strip()


def recortar(descricao: str, maximo: int = 3000) -> str:
    """Fica só com requisitos, atividades e diferenciais. Sem seção reconhecível, devolve o começo."""
    gupy = secoes_gupy(descricao)
    if gupy and len(gupy[1]) > 30:
        resp, req = gupy
        # requisitos primeiro: se precisar cortar, que corte as atividades
        return f"Requisitos e qualificações:\n{req}\n\nResponsabilidades:\n{resp}"[:maximo]
    manter, atual, achou = [], None, False
    for linha in descricao.splitlines():
        n = _norm(linha).strip(" :-•*#")
        if len(n) <= 60:
            if any(n.startswith(s) or s in n[:30] for s in SECOES_INUTEIS):
                atual = False
                continue
            if any(n.startswith(s) or s in n[:30] for s in SECOES_UTEIS):
                atual, achou = True, True
        if atual:
            manter.append(linha)
    texto = "\n".join(manter) if achou and sum(map(len, manter)) > 200 else descricao
    return texto[:maximo]


PALAVRAS_POR_PEDACO = 60   # o MiniLM lê até 128 tokens; texto maior é cortado em silêncio


def pedacos_para_embedding(titulo: str, descricao: str, maximo: int = 6) -> list[str]:
    """Título + pedaços curtos do recorte. Cada pedaço cabe inteiro na janela do modelo."""
    palavras = recortar(descricao, 2400).split()
    blocos = [" ".join(palavras[i:i + PALAVRAS_POR_PEDACO]) for i in range(0, len(palavras), PALAVRAS_POR_PEDACO)]
    return [titulo] + [f"{titulo}: {b}" for b in blocos[:maximo]]


class Ranqueador:
    def __init__(self):
        from fastembed import TextEmbedding  # import aqui: carrega o ONNX só quando precisa
        self.modelo = TextEmbedding(MODELO_EMBEDDING)

    def vetores(self, textos: list[str]):
        import numpy as np
        m = np.array(list(self.modelo.embed(textos, batch_size=32)), dtype="float32")
        return m / np.linalg.norm(m, axis=1, keepdims=True)

    def similaridades(self, consultas: list[str], vagas: list[list[str]]) -> list[float]:
        """Nota de cada vaga = o par (pedaço da vaga, frase da busca) mais parecido.

        Medido em 30/10 contra a média entre frases: a média premiava vaga genérica que toca em tudo
        um pouco e jogava "Desenvolvedor PL SQL Pleno" para 15º; o máximo o pôs em 1º.
        """
        q = self.vetores(consultas)
        planos = [p for ps in vagas for p in ps]
        m = self.vetores(planos) @ q.T          # (pedaços x frases)
        notas, i = [], 0
        for ps in vagas:
            bloco = m[i:i + len(ps)]
            notas.append(float(bloco.max()))
            i += len(ps)
        return notas


def consulta_do_perfil(perfil_md: str) -> list[str]:
    """As frases do bloco 'Busca' do perfil (uma por linha que começa com '-')."""
    m = re.search(r"(?s)## Busca\n(.*?)(\n## |\Z)", perfil_md)
    texto = m.group(1) if m else perfil_md
    frases = [re.sub(r"[#*`]", "", l).strip(" -") for l in texto.splitlines() if l.strip().startswith("-")]
    return frases or [re.sub(r"[#*`]", "", texto).strip()]
