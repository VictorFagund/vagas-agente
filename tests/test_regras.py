import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import coleta  # noqa: E402
import ia      # noqa: E402


def vaga(**kw):
    base = {"id": 1, "titulo": "Analista de Banco de Dados Jr", "empresa": "X", "tipo_local": "remote",
            "cidade": "", "publicada": "2026-10-20", "prazo": "2026-11-30", "url": "", "descricao": "", "termo": "SQL"}
    return {**base, **kw}


def test_remota_passa():
    assert coleta.filtro_regras(vaga(), hoje="2026-10-30") is None


def test_hibrida_sai():
    assert "não é remota" in coleta.filtro_regras(vaga(tipo_local="hybrid"), hoje="2026-10-30")


def test_prazo_vencido_sai():
    assert "prazo" in coleta.filtro_regras(vaga(prazo="2026-10-01"), hoje="2026-10-30")


def test_sem_prazo_antiga_sai_e_recente_fica():
    # Stefanini "PL SQL Pleno": publicada em 2024, sem prazo, já encerrada na página
    assert "antiga" in coleta.filtro_regras(vaga(prazo="", publicada="2024-02-20"), hoje="2026-11-06")
    assert coleta.filtro_regras(vaga(prazo="", publicada="2026-10-01"), hoje="2026-11-06") is None


def test_senior_sai_com_e_sem_acento():
    assert coleta.filtro_regras(vaga(titulo="Desenvolvedor Sênior PL/SQL"), hoje="2026-10-30")
    assert coleta.filtro_regras(vaga(titulo="Desenvolvedor Senior PL/SQL"), hoje="2026-10-30")
    assert coleta.filtro_regras(vaga(titulo="Dev Sr - Clipper/PL SQL"), hoje="2026-10-30")


def test_palavra_parcial_nao_derruba():
    # "lead" não pode pegar "leadership" nem "head" pegar "headless"; "sr" não pega "srs"
    assert coleta.filtro_regras(vaga(titulo="Analista de Dados - Headless CMS"), hoje="2026-10-30") is None
    assert coleta.filtro_regras(vaga(titulo="Programa de Residência - GenAI"), hoje="2026-10-30") is None


def test_texto_limpo_tira_html():
    assert coleta.texto_limpo("<p>Olá&nbsp;<b>mundo</b></p><p>linha 2</p>") == "Olá mundo\nlinha 2"


def test_validar_corrige_fora_do_enum():
    r = ia.validar({"nivel": "Sênior", "area": "?", "ingles": "x", "nota": 140, "tem": ["a"] * 9, "falta": None, "motivo": 1})
    assert (r["nivel"], r["area"], r["ingles"], r["nota"], len(r["tem"]), r["falta"]) == \
        ("nao_informado", "outra", "leitura", 100, 5, [])


import bancada  # noqa: E402


def test_kappa_perfeito_e_acaso():
    assert bancada.kappa([("sim", "sim"), ("nao", "nao"), ("talvez", "talvez")]) == 1.0
    assert abs(bancada.kappa([("sim", "nao"), ("nao", "sim")]) - (-1.0)) < 1e-9


def test_classe_usa_os_cortes_do_relatorio():
    assert [bancada.classe(n) for n in (70, 69, 50, 49)] == ["sim", "talvez", "talvez", "nao"]


import funil  # noqa: E402


def test_recorte_acha_secoes_coladas_da_gupy():
    d = ("Somos a maior empresa do mundo e blá blá." * 5 + "Responsabilidades e atribuiçõesCriar procedures."
         "Requisitos e qualificaçõesExperiência com PL/SQL e triggers em banco Oracle, consultas SQL e tuning."
         "Informações adicionaisVale refeição e plano de saúde.")
    r = funil.recortar(d)
    assert "PL/SQL" in r and "procedures" in r
    assert "maior empresa" not in r and "Vale refeição" not in r


def test_pedacos_cabem_na_janela_do_modelo():
    ps = funil.pedacos_para_embedding("Dev", "palavra " * 500)
    assert ps[0] == "Dev" and all(len(p.split()) <= funil.PALAVRAS_POR_PEDACO + 2 for p in ps)


def test_consulta_le_as_frases_do_bloco_busca():
    assert funil.consulta_do_perfil("## Busca\nintro\n- uma\n- duas\n## Outro\n- não") == ["uma", "duas"]


import fontes  # noqa: E402


def test_remoto_do_greenhouse_so_no_brasil():
    t = fontes.tipo_local_por_texto
    assert t("Remoto", "Dev") == "remote"
    assert t("Remote - Brazil", "Dev") == "remote"
    assert t("São Paulo, Rio de Janeiro ou Teletrabalho", "Dev") == "remote"
    assert t("London l Remote", "Dev") != "remote"
    assert t("Portugal (Remote)", "Dev") != "remote"
    assert t("Brazil (São Paulo - Hybrid)", "Dev") == "hybrid"
    assert t("São Paulo, Brazil", "Dev") == "on-site"


def test_titulos_de_nivel_alto_e_banco_de_talentos_saem():
    for titulo in ["Data Engineer III", "[Talent Pool] Analyst", "Staff Engineer", "Engineering - [Always Hiring]"]:
        assert coleta.filtro_regras(vaga(titulo=titulo), hoje="2026-10-30"), titulo


import agente  # noqa: E402


def test_espera_da_cota_le_minutos_e_segundos():
    assert agente.espera_da_cota("Please try again in 6m25.5s. Need more") == 385.5
    assert agente.espera_da_cota("try again in 12.3s") == 12.3
    assert agente.espera_da_cota("sem tempo") is None
