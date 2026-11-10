# Agente de busca de vaga

Um agente que lê vagas de três fontes, descarta o que não serve por regra, ranqueia o resto por
similaridade com o perfil do candidato e só então chama um LLM para dar nota a cada vaga, com o
motivo, o que o candidato tem e o que falta. Sai um relatório HTML ordenado por nota.

Projeto de estudo de agentes com LLM: funil de custo, saída estruturada e avaliação do modelo.

## Números de uma rodada real (30/10 a 06/11/2026)

| | |
|---|---|
| Vagas lidas | **3.102** (Gupy 1.340, Greenhouse 1.533, Lever 229) |
| Descartadas por regra, sem custo de IA | **2.899** (2.630 presenciais ou híbridas, o resto por título ou prazo) |
| Avaliadas pelo LLM | **93**, as do topo do ranqueamento |
| Com nota 70+ | **38** |
| Custo | **R$ 0** (Groq, plano gratuito) — ~3 mil tokens e ~14 s por vaga |
| Execuções | 12 |

Ler 3.100 anúncios a um minuto cada seriam ~50 horas; o relatório deixa umas 40 para ler.

## Como funciona

```
coleta (Gupy, Greenhouse, Lever)
  -> regras: só remoto, prazo aberto, título fora do perfil (sênior, gerente, staff...)
  -> embedding local: ranqueia cada vaga contra as frases de "Busca" do perfil
  -> LLM só no topo (--limite): nota 0-100, nível, área, inglês, tem/falta, motivo
  -> SQLite (cada vaga é avaliada uma vez) -> saida/vagas.html
```

O funil existe por causa do custo: o plano gratuito da Groq dá 200 mil tokens por dia, umas
60 avaliações. Regra e embedding são de graça e cortam 97% antes de chegar no modelo.

## Decisões que foram medidas, não chutadas

- **Modelo:** testei `gpt-oss-20b` como avaliador e reprovei. A mesma vaga levou 55 e depois 75,
  outra 60 e depois 30, e 3 de 12 chamadas quebraram o JSON. Fiquei com `gpt-oss-120b` e saída
  em `json_schema`.
- **Embedding cortando texto em silêncio:** o MiniLM multilíngue lê ~128 tokens. Com a vaga
  inteira ele só via "somos a maior multinacional...". Agora a descrição vira pedaços de 60
  palavras e a nota é o máximo entre (pedaço × frase do perfil). Uma vaga de "Desenvolvedor PL/SQL"
  saiu da 97ª posição para a 1ª.
- **A Gupy cola os títulos de seção no texto** ("Responsabilidades e atribuiçõesCompor...").
  `funil.secoes_gupy` separa pelas seções fixas antes de recortar.
- **"Remote" nem sempre é para o Brasil:** o Greenhouse não tem campo de modelo de trabalho,
  então o local é lido como texto, e "London | Remote" não passa; no Lever, remoto de outro
  país vira `remote-us` e é descartado.
- **Vaga fantasma:** vaga sem prazo e publicada há mais de 90 dias é tratada como encerrada.
- **Cota:** o agente lê o "try again in Xs" da API e espera; no limite diário para, ou espera a
  cota liberar com `--esperar-cota` (para rodar de madrugada).

## Bancada de avaliação

`src/bancada.py` sorteia vagas avaliadas (estratificado por classe, às cegas) para o candidato
marcar "eu me candidataria?" e mede a concordância com a IA (kappa, matriz de confusão e erros
graves, como a IA dar 90 numa vaga que ele recusaria).

## Rodar

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # no Linux/Mac: .venv/bin/pip
cp .env.example .env                              # cole sua chave
cp perfil.exemplo.md perfil.md                    # escreva o seu perfil
.venv/Scripts/python src/agente.py --limite 20
```

`buscas.txt` tem os termos pesquisados na Gupy; `empresas.txt` os quadros públicos de
Greenhouse e Lever. Testes: `.venv/Scripts/python -m pytest` (16).

O perfil vai para a API do modelo, por isso não leva telefone, e-mail nem endereço.
