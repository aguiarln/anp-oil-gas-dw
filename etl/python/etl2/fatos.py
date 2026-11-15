"""Carga das tabelas fato. As duas são recarregadas por completo a cada execução (decisão do autor) e
apontam para a versão vigente das dimensões; a linha 0 (DNQ) entra quando a dimensão não se aplica."""

import re
from collections import defaultdict
from decimal import Decimal

from .dimensoes import dias_do_mes
from .extracao import MEDIDAS
from .normalizacao import chave, chave_contrato

M3_POR_BARRIL = Decimal("0.158987294928")
VOLUMES = {"oleo_bbl_dia": "md_oleo_bbl", "condensado_bbl_dia": "md_condensado_bbl", "petroleo_bbl_dia": "md_petroleo_bbl",
           "agua_bbl_dia": "md_agua_bbl", "gas_assoc_mm3_dia": "md_gas_assoc_mil_m3",
           "gas_nao_assoc_mm3_dia": "md_gas_nao_assoc_mil_m3", "gas_total_mm3_dia": "md_gas_total_mil_m3"}
COLUNAS_PRODUCAO = ["sk_data", "sk_poco", "sk_campo", "sk_empresa", "sk_contrato", "sk_instalacao", "sk_corrente",
                    *VOLUMES.values(), "md_horas_producao", "md_preco_rs_m3", "md_receita_estimada_rs"]


def precos(st) -> tuple[dict, dict]:
    """Preço do petróleo do campo no mês (T11, T17, T18): média dos preços publicados na versão mais recente,
    por (chave do contrato, campo normalizado, mês). Também por (campo, mês) quando um só contrato publica."""
    por_contrato = defaultdict(list)
    por_campo = defaultdict(lambda: defaultdict(list))
    for numero, campo_nome, periodo, valor in st.execute("""
            SELECT c.numero, p.campo_nome, p.periodo, p.valor_rs_m3
            FROM (SELECT pp.*, max(id_carga) OVER (PARTITION BY id_contrato, campo_nome, id_corrente, periodo, tipo_preco) AS ultima
                  FROM preco_petroleo pp) p
            JOIN contrato c USING (id_contrato)
            WHERE p.id_carga = p.ultima AND p.valor_rs_m3 IS NOT NULL""").fetchall():
        por_contrato[(chave_contrato(numero), chave(campo_nome), periodo)].append(valor)
        por_campo[(chave(campo_nome), periodo)][chave_contrato(numero)].append(valor)
    media = lambda vs: sum(vs) / len(vs)
    unico = {k: media(next(iter(v.values()))) for k, v in por_campo.items() if len(v) == 1}
    return {k: media(v) for k, v in por_contrato.items()}, unico


def producao(st, dw, sk: dict) -> dict:
    """ft_producao a partir de `cons` (grão poço × campo × mês)."""
    preco_contrato, preco_campo = precos(st)
    nome_campo = dict(st.execute("SELECT id_campo, nome FROM campo").fetchall())
    numero_contrato = dict(st.execute("SELECT id_contrato, numero FROM contrato").fetchall())
    resumo = defaultdict(int)
    dw.execute("TRUNCATE ft_producao")
    cols = ["id_poco", "id_campo", "periodo", "id_empresa", "id_contrato", "id_instalacao", "id_caracterizacao", *MEDIDAS]
    with st.cursor(name="cons_fato") as cur, dw.cursor().copy(f"COPY ft_producao ({', '.join(COLUNAS_PRODUCAO)}) FROM STDIN") as cp:
        cur.itersize = 20000
        cur.execute(f"SELECT {', '.join(cols)} FROM cons")
        for r in cur:
            d = dict(zip(cols, r))
            periodo, dias = d["periodo"], dias_do_mes(d["periodo"])
            vol = {dest: (d[orig] or 0) * dias for orig, dest in VOLUMES.items()}
            k_campo, k_contrato = chave(nome_campo[d["id_campo"]]), chave_contrato(numero_contrato[d["id_contrato"]])
            preco = preco_contrato.get((k_contrato, k_campo, periodo))
            if preco is None:
                preco = preco_campo.get((k_campo, periodo))
                resumo["preco_pelo_campo"] += preco is not None
            receita = vol["md_petroleo_bbl"] * M3_POR_BARRIL * preco if preco is not None else None
            linha = [int(periodo.strftime("%Y%m01")), sk["poco"][d["id_poco"]], sk["campo"][d["id_campo"]],
                     sk["empresa"].get(d["id_empresa"], 0), sk["contrato"].get(d["id_contrato"], 0),
                     sk["instalacao"].get(d["id_instalacao"], 0), sk["corrente"].get(d["id_caracterizacao"], 0),
                     *vol.values(), d["horas_producao"], preco, receita]
            cp.write_row(linha)
            resumo["linhas"] += 1
            resumo["sem_preco"] += preco is None
            resumo["sem_instalacao"] += linha[5] == 0
            resumo["sem_corrente"] += linha[6] == 0
    return dict(resumo)


def participacao(st, dw, sk_empresa: dict, sk_contrato: dict) -> dict:
    """ft_participacao: uma linha por empresa (sócia), contrato e foto da relação de concessionários."""
    dw.execute("TRUNCATE ft_participacao")
    linhas = defaultdict(lambda: [Decimal(0), False])
    for id_empresa, id_contrato, nome_arquivo, percentual, operador in st.execute("""
            SELECT p.id_empresa, p.id_contrato, c.nome_arquivo, p.percentual, p.operador
            FROM participacao_contrato p JOIN carga c USING (id_carga)""").fetchall():
        data = re.search(r"/(\d{4})-(\d{2})-(\d{2})/", nome_arquivo)  # data do download = data da foto
        chave_linha = (int("".join(data.groups())), sk_empresa.get(id_empresa, 0), sk_contrato.get(id_contrato, 0))
        linhas[chave_linha][0] += percentual  # grafias unidas (T07) no mesmo contrato somam a participação
        linhas[chave_linha][1] |= operador
    with dw.cursor().copy("COPY ft_participacao (sk_data, sk_empresa, sk_contrato, md_percentual, dd_operador) FROM STDIN") as cp:
        for (sk_data, sk_e, sk_c), (pct, op) in linhas.items():
            cp.write_row([sk_data, sk_e, sk_c, pct, "S" if op else "N"])
    return {"linhas": len(linhas)}
