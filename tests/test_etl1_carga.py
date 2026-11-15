"""ETL 1 de ponta a ponta sobre as amostras, num banco temporário.

Premissas:
- [autor] o pipeline é fixo e a carga de dados é atualizável; nada é substituído no transacional;
- [recomendação aceita] versionamento (C05/T17): arquivo repetido não é recarregado; só a linha que mudou
  de verdade entra como versão nova, ignorando a "Data de atualização";
- [autor] dado bruto: grafia exata, só sem os espaços das pontas (C02);
- [autor] duplicatas da produção ficam na stage (tratadas no ETL 2);
- cada arquivo é gravado numa transação: entra inteiro ou não entra nada.
"""

import pytest

from etl.python.etl1 import exportar

from .conftest import ESPERADO, amostra, consultar, rodar_etl1, valor

pytestmark = pytest.mark.integracao

CDP = ("raw", "anp", "producao-por-poco-cdp")


def _contagens(banco):
    return {t: valor(banco, f"SELECT count(*) FROM {t}") for t in ("carga", "producao_mensal", "preco_petroleo", "participacao_contrato")}


def _cdp(dados, data, nome, conteudo: bytes):
    pasta = dados.joinpath(*CDP, data)
    pasta.mkdir(parents=True, exist_ok=True)
    (pasta / nome).write_bytes(conteudo)


def _revisado() -> bytes:
    """A amostra de 12/2023 como a CDP a devolveria depois: operador trocado na 1ª linha e data de exportação nova."""
    texto = amostra("L48_2023_12_producao_Terra.csv").decode("latin1")
    cab, *linhas = texto.splitlines(keepends=True)
    linhas = [ln.replace("26/11/2025", "01/10/2026 09:15") for ln in linhas]
    linhas[0] = linhas[0].replace(";3R Potiguar;", ";3R Potiguar SPE;", 1)
    return (cab + "".join(linhas)).encode("latin1")


def test_carga_inicial(banco, dados_teste):
    assert rodar_etl1(banco) == 0
    assert _contagens(banco) == {"carga": ESPERADO["cargas"], "producao_mensal": ESPERADO["producao_mensal"],
                                 "preco_petroleo": ESPERADO["preco_petroleo"],
                                 "participacao_contrato": ESPERADO["participacao_contrato"]}
    assert valor(banco, "SELECT count(*) FROM carga WHERE situacao <> 'carregada'") == 0
    # toda linha aponta para a sua carga, e a soma bate com qtd_linhas
    assert valor(banco, "SELECT sum(qtd_linhas) FROM carga WHERE fonte LIKE 'producao%%'") == ESPERADO["producao_mensal"]


def test_os_5_layouts_e_as_3_origens_entram(banco, dados_teste):
    rodar_etl1(banco)
    origens = consultar(banco, "SELECT arquivo_origem, count(*) FROM producao_mensal GROUP BY 1 ORDER BY 1")
    assert origens == [("mar", 6), ("presal", 5), ("terra", 23)]
    assert valor(banco, "SELECT count(DISTINCT periodo) FROM producao_mensal") == 6
    # caracterização só a partir de 2018
    assert valor(banco, """SELECT count(*) FROM producao_mensal WHERE id_caracterizacao IS NOT NULL
                           AND periodo < '2018-01-01'""") == 0
    # 16 linhas de 2018+; a do poço 1-ALV-8D-BA (2019) não traz nenhuma análise
    assert valor(banco, "SELECT count(*) FROM producao_mensal WHERE id_caracterizacao IS NOT NULL") == 15


def test_mes_repetido_no_csv_mensal_nao_e_gravado_de_novo(banco, dados_teste):
    # os zips de 2010-2015 trazem cada mês num CSV mensal e no anual, com volumes idênticos (C05a)
    rodar_etl1(banco)
    anual, mensal = consultar(banco, """SELECT qtd_linhas FROM carga WHERE nome_arquivo LIKE '%%2010.zip::2010/2010%%producao_mar.csv'
                                         ORDER BY id_carga""")
    assert (anual[0], mensal[0]) == (6, 0)


def test_arquivo_repetido_nao_e_carregado_de_novo(banco, dados_teste):
    rodar_etl1(banco)
    antes = _contagens(banco)
    assert rodar_etl1(banco) == 0
    depois = _contagens(banco)
    assert depois["carga"] == antes["carga"] + ESPERADO["cargas"]  # só as tentativas são registradas
    assert valor(banco, "SELECT count(*) FROM carga WHERE situacao = 'repetida'") == ESPERADO["cargas"]
    assert {k: v for k, v in depois.items() if k != "carga"} == {k: v for k, v in antes.items() if k != "carga"}


def test_revisao_da_anp_vira_versao_nova_so_na_linha_alterada(banco, dados_teste):
    rodar_etl1(banco)
    _cdp(dados_teste, "2026-02-01", "2023_12_producao_Terra.csv", _revisado())
    assert rodar_etl1(banco) == 0
    # 6 linhas lidas; 5 só mudaram a "Data de atualização" (ignorada); 1 trocou de operador
    assert valor(banco, "SELECT qtd_linhas FROM carga WHERE fonte = 'producao_por_poco_cdp'") == 1
    versoes = consultar(banco, """SELECT e.nome_fantasia FROM producao_mensal p JOIN poco USING (id_poco)
                                  JOIN empresa e USING (id_empresa)
                                  WHERE poco.nome_anp = '7-ET-994-RN' AND periodo = '2023-12-01' ORDER BY p.id_carga""")
    assert versoes == [("3R Potiguar",), ("3R Potiguar SPE",)]  # a versão anterior fica preservada


def test_erro_num_arquivo_desfaz_a_carga_dele(banco, dados_teste):
    rodar_etl1(banco)
    antes = _contagens(banco)
    quebrado = amostra("L48_2023_12_producao_Terra.csv") + b"Bahia;X;P;P;C;Op;1;2023/12" + b";0" * 22 + b"\n"
    _cdp(dados_teste, "2026-03-01", "2023_12_producao_Terra.csv", quebrado)
    assert rodar_etl1(banco) == 1
    assert _contagens(banco)["producao_mensal"] == antes["producao_mensal"]
    assert valor(banco, "SELECT count(*) FROM carga WHERE fonte = 'producao_por_poco_cdp'") == 0


def test_grafia_exata_sem_unificar_nomes(banco, dados_teste):
    rodar_etl1(banco)
    # o mesmo tipo de petróleo em duas grafias (PDF 2005-2008 x CSV 2009) fica como duas correntes
    correntes = {c for (c,) in consultar(banco, "SELECT nome FROM corrente WHERE lower(nome) = 'baiano mistura'")}
    assert correntes == {"Baiano Mistura", "baiano mistura"}
    campos = {c for (c,) in consultar(banco, "SELECT DISTINCT campo_nome FROM preco_petroleo WHERE campo_nome ILIKE '%%gua grande'")}
    assert campos == {"ÁGUA GRANDE", "agua grande", "Água Grande"}
    # o contrato "#N/D" do preço de referência fica como veio
    assert valor(banco, "SELECT count(*) FROM contrato WHERE numero = '#N/D'") == 1


def test_textos_sem_espacos_nas_pontas(banco, dados_teste):
    rodar_etl1(banco)
    for tabela, coluna in (("poco", "nome_anp"), ("campo", "nome"), ("empresa", "nome_fantasia"), ("bacia", "nome"),
                           ("contrato", "rodada"), ("grupo_economico", "pais")):
        assert valor(banco, f"SELECT count(*) FROM {tabela} WHERE {coluna} <> btrim({coluna})") == 0, tabela


def test_operador_marcado_na_participacao(banco, dados_teste):
    rodar_etl1(banco)
    assert valor(banco, "SELECT count(*) FROM participacao_contrato WHERE operador") == 8
    assert valor(banco, "SELECT count(*) FROM empresa WHERE nome_fantasia LIKE '(Operador)%%'") == 0


def test_estado_com_sigla_e_regiao_do_ibge(banco, dados_teste):
    rodar_etl1(banco)
    estados = consultar(banco, "SELECT nome, sigla, regiao FROM estado")
    assert ("Rio Grande do Norte", "RN", "Nordeste") in estados and ("Rio de Janeiro", "RJ", "Sudeste") in estados
    assert all(sigla and regiao for _, sigla, regiao in estados)


def test_etl1_e_deterministico(novo_banco, dados_teste):
    # duas execuções sobre os mesmos arquivos geram o mesmo banco, com os mesmos IDs
    import psycopg
    from etl.python.etl1.config import conninfo
    a, b = novo_banco(), novo_banco()
    rodar_etl1(a)
    rodar_etl1(b)
    with psycopg.connect(conninfo(a)) as ca, psycopg.connect(conninfo(b)) as cb:
        for t in exportar.TABELAS:
            assert exportar._hash_conteudo(ca, t) == exportar._hash_conteudo(cb, t), t


# ---------- coordenadas ----------

def _troca_amostra(dados, fonte, nome, antes, depois, data="2026-02-01"):
    pasta = dados / "raw" / "anp" / fonte / data
    pasta.mkdir(parents=True, exist_ok=True)
    texto = amostra(nome).decode("utf-8")
    assert antes in texto
    (pasta / nome).write_bytes(texto.replace(antes, depois, 1).encode("utf-8"))


def test_coordenadas_carregadas(banco, dados_teste):
    rodar_etl1(banco)
    assert valor(banco, "SELECT count(*) FROM coordenada_poco") == ESPERADO["coordenada_poco"]
    assert valor(banco, "SELECT count(*) FROM coordenada_campo") == ESPERADO["coordenada_campo"]
    # o poço da produção e o da camada são o mesmo cadastro (casamento pelo nome ANP exato)
    assert valor(banco, """SELECT count(*) FROM coordenada_poco c JOIN poco p USING (id_poco)
                           WHERE p.nome_anp = '7-ET-994-RN' AND EXISTS (SELECT 1 FROM producao_mensal m WHERE m.id_poco = c.id_poco)""") == 1
    assert valor(banco, """SELECT count(*) FROM coordenada_campo c JOIN campo cp USING (id_campo) JOIN bacia b USING (id_bacia)
                           WHERE cp.nome = 'ESTREITO' AND b.nome = 'Potiguar'
                           AND EXISTS (SELECT 1 FROM producao_mensal m WHERE m.id_campo = c.id_campo)""") == 1


def test_pocos_que_nunca_produziram_entram_no_cadastro(banco, dados_teste):
    # [autor] "Cadastre todos os poços": quem não está na produção é criado pela grafia exata (C01)
    rodar_etl1(banco)
    assert valor(banco, """SELECT count(*) FROM coordenada_poco c
                           WHERE NOT EXISTS (SELECT 1 FROM producao_mensal m WHERE m.id_poco = c.id_poco)""") == 2
    assert valor(banco, "SELECT count(*) FROM bacia WHERE nome LIKE %s", ["%\xad%"]) == 1  # grafia da camada, sem correção


def test_coordenada_alterada_vira_versao_nova(banco, dados_teste):
    rodar_etl1(banco)
    texto = amostra("POCOS_SIRGAS.csv").decode("utf-8")
    linha = next(l for l in texto.splitlines() if ",7-ET-994-RN," in l)
    ponto = linha.split("POINT (", 1)[1].split(")", 1)[0]
    _troca_amostra(dados_teste, "pocos-georreferenciados", "POCOS_SIRGAS.csv", f"POINT ({ponto})", "POINT (-36.5 -5.5)")
    assert rodar_etl1(banco) == 0
    # só o poço que mudou ganha versão nova; a anterior fica preservada
    assert valor(banco, "SELECT qtd_linhas FROM carga WHERE nome_arquivo LIKE '%%2026-02-01/POCOS_SIRGAS.csv'") == 1
    assert [g for (g,) in consultar(banco, """SELECT geometria_wkt FROM coordenada_poco JOIN poco USING (id_poco)
                                               WHERE nome_anp = '7-ET-994-RN' ORDER BY id_carga""")][-1] == "POINT (-36.5 -5.5)"
    assert valor(banco, "SELECT count(*) FROM coordenada_poco") == ESPERADO["coordenada_poco"] + 1
