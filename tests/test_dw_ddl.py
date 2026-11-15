"""DDL do Data Warehouse (database/dw/dim_data.sql + database/dw/criar_tabelas.sql), num banco temporário.

Premissas: modelo estrela; [autor] modelo aprovado em 18/10/2026: duas estrelas (ft_producao e
ft_participacao) com dimensões conformadas, SCD2 (etl_dt_inicio, etl_dt_fim, etl_versao), DNQ (linha 0) em
todas as dimensões, dd_operador como dimensão degenerada e nomenclatura padrão (dim_, ft_, md_, sk_, nk_).
"""

import psycopg
import pytest

from etl.python.etl1.config import conninfo

from .conftest import RAIZ, consultar, valor

pytestmark = pytest.mark.integracao

DW = RAIZ / "database" / "dw"
DIMENSOES = ["dim_poco", "dim_campo", "dim_empresa", "dim_contrato", "dim_instalacao", "dim_corrente"]
FKS = {
    "ft_producao": {"dim_data", "dim_poco", "dim_campo", "dim_empresa", "dim_contrato", "dim_instalacao", "dim_corrente"},
    "ft_participacao": {"dim_data", "dim_empresa", "dim_contrato"},
}


@pytest.fixture
def dw(novo_banco):
    nome = novo_banco(ddl=None)
    with psycopg.connect(conninfo(nome)) as c:
        c.execute((DW / "dim_data.sql").read_text(encoding="utf-8"))
        c.execute((DW / "criar_tabelas.sql").read_text(encoding="utf-8"))
    return nome


def test_as_tabelas_do_modelo_e_a_de_controle(dw):
    tabelas = {t for (t,) in consultar(dw, "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")}
    # 9 do modelo estrela + etl_depara, a tabela de controle do ETL 2 (T22)
    assert tabelas == {"dim_data", *DIMENSOES, "ft_producao", "ft_participacao", "etl_depara"}


def test_fatos_ligadas_as_suas_dimensoes(dw):
    fks = {}
    for t, ref in consultar(dw, """
            SELECT tc.table_name, ccu.table_name FROM information_schema.table_constraints tc
            JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'public'"""):
        fks.setdefault(t, set()).add(ref)
    assert fks == FKS
    # dimensões conformadas: as mesmas tabelas nas duas estrelas
    assert FKS["ft_producao"] & FKS["ft_participacao"] == {"dim_data", "dim_empresa", "dim_contrato"}


@pytest.mark.parametrize("fato, grao", [("ft_producao", {"sk_data", "sk_poco", "sk_campo"}),
                                        ("ft_participacao", {"sk_data", "sk_empresa", "sk_contrato"})])
def test_grao_declarado_na_chave_primaria(dw, fato, grao):
    pk = consultar(dw, f"""SELECT a.attname FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                          WHERE i.indrelid = '{fato}'::regclass AND i.indisprimary""")
    assert {c for (c,) in pk} == grao


@pytest.mark.parametrize("dim", DIMENSOES)
def test_dimensao_com_sk_nk_scd2_e_dnq(dw, dim):
    sufixo = dim[4:]
    colunas = {c for (c,) in consultar(dw, "SELECT column_name FROM information_schema.columns WHERE table_name = %s", [dim])}
    assert {f"sk_{sufixo}", f"nk_{sufixo}", "etl_dt_inicio", "etl_dt_fim", "etl_versao"} <= colunas
    assert consultar(dw, f"SELECT nk_{sufixo}, etl_versao FROM {dim} WHERE sk_{sufixo} = 0") == [("N/A", 1)]
    # a sequência da surrogate key começa em 1: a linha 0 fica reservada para a DNQ
    assert valor(dw, f"SELECT nextval(pg_get_serial_sequence('{dim}', 'sk_{sufixo}'))") == 1


def test_dim_data_com_a_linha_0(dw):
    assert valor(dw, "SELECT count(*) FROM dim_data WHERE sk_data > 0") == 11322
    assert consultar(dw, "SELECT nk_data::text, nm_mes FROM dim_data WHERE sk_data = 0") == [("1900-01-01", "N/A")]


def test_nomenclatura_padrao(dw):
    medidas = {c for (c,) in consultar(dw, """SELECT column_name FROM information_schema.columns
                                             WHERE table_name IN ('ft_producao', 'ft_participacao') AND column_name NOT LIKE 'sk\\_%'""")}
    assert all(c.startswith(("md_", "dd_")) for c in medidas), medidas


def test_dd_operador_so_aceita_s_ou_n(dw):
    with pytest.raises(Exception):
        consultar(dw, "INSERT INTO ft_participacao VALUES (0, 0, 0, 100, 'X') RETURNING 1")
    assert consultar(dw, "INSERT INTO ft_participacao VALUES (0, 0, 0, 100, 'S') RETURNING dd_operador") == [("S",)]


def test_tipo_de_preco_nao_e_coluna_da_fato(dw):
    # [autor] derivado do mês (até 12/2017 mínimo; a partir de 2018 referência), sem dimensão degenerada
    assert valor(dw, "SELECT count(*) FROM information_schema.columns WHERE table_name = 'ft_producao' AND column_name LIKE '%%tipo%%'") == 0
