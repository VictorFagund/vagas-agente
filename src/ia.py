"""Avaliação de encaixe vaga x perfil por LLM, com saída em JSON validado por esquema.

Qualquer API compatível com a da OpenAI serve (Groq, OpenAI). A nota segue uma régua
escrita aqui, para ser comparável entre vagas e entre execuções.
"""
import json
import os
import sys
import re
import time

from openai import BadRequestError, OpenAI, RateLimitError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from funil import recortar  # noqa: E402

MAX_DESCRICAO = 3000   # caracteres do recorte (requisitos e atividades); o plano gratuito limita tokens

NIVEIS = ["estagio", "junior", "pleno", "senior", "nao_informado"]
AREAS = ["desenvolvimento", "banco_de_dados", "dados_bi", "ia_automacao", "analise_sistemas",
         "suporte_n2_n3", "suporte_n1", "outra"]
INGLES = ["nao_exige", "leitura", "intermediario", "fluente"]

ESQUEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["nivel", "area", "ingles", "tem", "falta", "nota", "motivo"],
    "properties": {
        "nivel": {"type": "string", "enum": NIVEIS},
        "area": {"type": "string", "enum": AREAS},
        "ingles": {"type": "string", "enum": INGLES},
        "tem": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "falta": {"type": "array", "items": {"type": "string"}, "maxItems": 5},
        "nota": {"type": "integer", "minimum": 0, "maximum": 100},
        "motivo": {"type": "string"},
    },
}

INSTRUCAO = """Você avalia se uma vaga de emprego serve para um candidato específico.
Leia o perfil e a vaga e responda só com o JSON pedido.

Campos:
- nivel: nível que a VAGA pede (pelo título e pelos requisitos de experiência).
- area: área principal do trabalho do dia a dia.
- ingles: o que a vaga exige de inglês. "fluente" = conversação, entrevista ou reunião em inglês.
- tem: até 5 requisitos DA VAGA que o candidato cumpre, cada um com a evidência do perfil, curto.
- falta: até 5 requisitos DA VAGA que ele não cumpre. Só o que a vaga pede de fato; não invente.
- nota: encaixe de 0 a 100 pela régua abaixo.
- motivo: uma ou duas frases dizendo o que decide a nota.

Régua da nota:
- 85-100: área e nível certos, remoto, ele cumpre quase todos os obrigatórios. Vale candidatar hoje.
- 70-84: bom encaixe com uma ou duas lacunas que dá para admitir na candidatura.
- 50-69: encaixe parcial; área vizinha ou lacunas importantes.
- 25-49: fraco; nível acima, stack muito diferente ou inglês fluente obrigatório.
- 0-24: não serve (outra área, nível muito acima, degrau abaixo do que ele já faz).
Penalize: exigência de inglês fluente falado; sênior ou mais de 4 anos de experiência
obrigatórios em stack que ele não tem; suporte N1/help desk puro; salário informado abaixo do piso dele.
Não penalize requisito marcado como diferencial ou desejável.
Se a vaga for exclusiva ou afirmativa para um grupo (PcD, mulheres etc.), não mude a nota por
isso, mas comece o motivo com "Vaga exclusiva para ...". O perfil não informa esses dados."""


def montar_mensagens(perfil: str, vaga: dict) -> list[dict]:
    corpo = (
        f"PERFIL DO CANDIDATO\n{perfil}\n\n"
        f"VAGA\nTítulo: {vaga['titulo']}\nEmpresa: {vaga['empresa']}\n"
        f"Modelo de trabalho: {vaga['tipo_local']}\n\n{recortar(vaga['descricao'], MAX_DESCRICAO)}"
    )
    return [{"role": "system", "content": INSTRUCAO}, {"role": "user", "content": corpo}]


def validar(r: dict) -> dict:
    """O modo JSON de alguns provedores deixa passar valor fora do enum; corrigimos aqui."""
    if r.get("nivel") not in NIVEIS:
        r["nivel"] = "nao_informado"
    if r.get("area") not in AREAS:
        r["area"] = "outra"
    if r.get("ingles") not in INGLES:
        r["ingles"] = "leitura"
    r["nota"] = max(0, min(100, int(r.get("nota", 0))))
    r["tem"] = [str(x) for x in (r.get("tem") or [])][:5]
    r["falta"] = [str(x) for x in (r.get("falta") or [])][:5]
    r["motivo"] = str(r.get("motivo") or "")
    return r


class Avaliador:
    def __init__(self, env: dict | None = None):
        env = env or os.environ
        self.modelo = env["MODELO_TEXTO"]
        # max_retries alto: o plano gratuito da Groq devolve 429 com Retry-After e o cliente espera sozinho
        self.cliente = OpenAI(api_key=env["IA_API_KEY"], base_url=env.get("IA_BASE_URL") or None, max_retries=2)

    def avaliar(self, perfil: str, vaga: dict) -> tuple[dict, float, int]:
        t0 = time.time()
        for tentativa in range(6):
            try:
                resp = self.cliente.chat.completions.create(
                    model=self.modelo,
                    messages=montar_mensagens(perfil, vaga),
                    response_format={"type": "json_schema", "json_schema": {"name": "avaliacao", "schema": ESQUEMA}},
                    temperature=0,
                )
                break
            except BadRequestError as e:
                # o modelo às vezes gera JSON fora do esquema e o provedor recusa; outra tentativa costuma passar
                if tentativa >= 2 or "validate JSON" not in str(e):
                    raise
            except RateLimitError as e:
                # limite por minuto do plano gratuito: a mensagem diz quanto esperar ("try again in 12.3s")
                if tentativa == 5 or "per day" in str(e):
                    raise
                espera = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(e))
                time.sleep((int(espera.group(1) or 0) * 60 + float(espera.group(2)) if espera else 30) + 1)
        r = validar(json.loads(resp.choices[0].message.content))
        tokens = resp.usage.total_tokens if resp.usage else 0
        return r, time.time() - t0, tokens
