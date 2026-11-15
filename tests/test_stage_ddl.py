"""DDL da stage (database/st/criar_tabelas.sql), aplicado num banco temporário.

Premissas: [autor] várias tabelas, todas com PK e com FOREIGN KEY declaradas; [recomendação aceita] 3FN
com 8 a 15 tabelas e pelo menos um N:N (contrato x empresa); [autor] modelo de 14 tabelas aprovado em
01/10/2026, com os ajustes de DDL feitos na carga, mais as tabelas de coordenadas (17/10/2026): 16 tabelas.
"""

from pathlib import Path

import pytest

from .conftest import consultar, valor

pytestmark = pytest.mark.integracao

TABELAS = {"carga", "grupo_economico", "empresa", "participacao_contrato", "contrato", "bacia", "campo", "estado",
           "poco", "instalacao", "corrente", "caracterizacao_petroleo", "producao_mensal", "preco_petroleo",
           "coordenada_poco", "coordenada_campo"}

# Tabela -> tabelas referenciadas pelas FKs.
FKS = {
    "empresa": {"grupo_economico"},
    "contrato": {"bacia"},
    "participacao_contrato": {"empresa", "contrato", "carga"},
    "campo": {"bacia"},
    "caracterizacao_petroleo": {"corrente"},
    "producao_mensal": {"carga", "estado", "poco", "campo", "empresa", "contrato", "instalacao", "caracterizacao_petroleo"},
    "preco_petroleo": {"carga", "contrato", "corrente"},
    "coordenada_poco": {"poco", "carga"},
    "coordenada_campo": {"campo", "carga"},
}


def _fks(banco):
    linhas = consultar(banco, """
        SELECT tc.table_name, ccu.table_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
        WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'""")
    fks = {}
    for t, ref in linhas:
        fks.setdefault(t, set()).add(ref)
    return fks


def _coluna(banco, tabela, coluna):
    return consultar(banco, """SELECT data_type, is_nullable FROM information_schema.columns
                               WHERE table_name = %s AND column_name = %s""", [tabela, coluna])


def test_as_16_tabelas_existem(banco):
    tabelas = {t for (t,) in consultar(banco, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert tabelas == TABELAS


def test_todas_as_tabelas_tem_chave_primaria(banco):
    com_pk = {t for (t,) in consultar(banco, """SELECT table_name FROM information_schema.table_constraints
                                                WHERE constraint_type = 'PRIMARY KEY' AND table_schema = 'public'""")}
    assert com_pk == TABELAS


def test_chaves_estrangeiras_declaradas(banco):
    assert _fks(banco) == FKS


def test_participacao_e_o_n_n_contrato_empresa_por_carga(banco):
    pk = consultar(banco, """
        SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
        WHERE i.indrelid = 'participacao_contrato'::regclass AND i.indisprimary""")
    assert {c for (c,) in pk} == {"id_empresa", "id_contrato", "id_carga"}


def test_campo_e_identificado_por_nome_e_bacia(banco):
    # FAZENDA BELEM existe nas bacias Potiguar e Recôncavo
    with pytest.raises(Exception):
        consultar(banco, """INSERT INTO bacia (nome) VALUES ('A'), ('B');
                            INSERT INTO campo (nome, id_bacia) VALUES ('FAZENDA BELEM', 1), ('FAZENDA BELEM', 2);
                            INSERT INTO campo (nome, id_bacia) VALUES ('FAZENDA BELEM', 1) RETURNING 1""")


def test_producao_mantem_duplicatas_da_fonte(banco):
    # [autor] o OLTP espelha a fonte: PK substituta, sem chave única (poço, campo, período)
    unicas = consultar(banco, """SELECT indexname FROM pg_indexes WHERE tablename = 'producao_mensal'
                                 AND indexdef ILIKE '%%UNIQUE%%'""")
    assert [i for (i,) in unicas] == ["producao_mensal_pkey"]


def test_um_conteudo_so_pode_ser_carregado_uma_vez(banco):
    # C05: o mesmo hash pode aparecer várias vezes como 'repetida', mas só uma como 'carregada'
    h = "a" * 64
    consultar(banco, f"""INSERT INTO carga (nome_arquivo, fonte, hash_sha256, situacao) VALUES
                         ('x', 'f', '{h}', 'carregada'), ('x', 'f', '{h}', 'repetida'), ('x', 'f', '{h}', 'repetida')
                         RETURNING 1""")
    with pytest.raises(Exception):
        consultar(banco, f"INSERT INTO carga (nome_arquivo, fonte, hash_sha256, situacao) VALUES ('x', 'f', '{h}', 'carregada') RETURNING 1")


@pytest.mark.parametrize("tabela, coluna, tipo, nula", [
    ("caracterizacao_petroleo", "id_corrente", "integer", "YES"),        # ~38 mil análises só do gás
    ("preco_petroleo", "valor_rs_m3", "numeric", "YES"),                 # preços em branco e códigos de erro
    ("producao_mensal", "data_atualizacao", "timestamp without time zone", "YES"),  # 69 mil linhas com hora
    ("producao_mensal", "id_contrato", "integer", "NO"),
    ("producao_mensal", "id_instalacao", "integer", "YES"),              # vazia em ~60% das linhas
    ("producao_mensal", "id_estado", "integer", "YES"),                  # formato sem a coluna Estado
])
def test_ajustes_de_ddl_feitos_na_carga(banco, tabela, coluna, tipo, nula):
    assert _coluna(banco, tabela, coluna) == [(tipo, nula)]


def test_nome_do_poco_no_operador_nao_e_carregado(banco):
    # [autor] repete o nome ANP em 96% dos poços e nenhum RQ o usa
    assert valor(banco, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'poco'") == 2


def test_exportacao_da_base_origem_cobre_todas_as_tabelas(banco):
    # [autor] toda tabela da stage vira um CSV em dist/base-origem (auditoria)
    from etl.python.etl1 import exportar
    tabelas = {t for (t,) in consultar(banco, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    assert set(exportar.TABELAS) == tabelas
    texto = (Path(__file__).resolve().parents[1] / "database" / "st" / "carregar_base.sql").read_text(encoding="utf-8")
    assert all(f"\\copy {t} " in texto for t in tabelas)


def test_coordenadas_por_carga(banco):
    # uma coordenada por poço (ou campo) por carga; a geometria fica como a ANP publica (texto WKT)
    for tabela, chave in (("coordenada_poco", "id_poco"), ("coordenada_campo", "id_campo")):
        pk = consultar(banco, f"""
            SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
            WHERE i.indrelid = '{tabela}'::regclass AND i.indisprimary""")
        assert {c for (c,) in pk} == {chave, "id_carga"}
        assert _coluna(banco, tabela, "geometria_wkt") == [("text", "NO")]
