"""Carga das dimensões do DW com versionamento (SCD2), a partir da stage já preparada (extracao.preparar).

SCD2 (mesmo comportamento do passo "Dimension lookup/update" do PDI):
- chave natural nova: entra a versão 1, válida de 1900-01-01 a 2199-12-31;
- atributo versionado mudou: a versão vigente é fechada (etl_dt_fim = momento da carga) e entra uma versão nova;
- atributo SCD1 mudou (ex.: última produção do poço): é atualizado na própria versão vigente;
- chave natural que sumiu da fonte: a versão é mantida (o DW não apaga história).

A dim_corrente é diferente: cada período de carga da análise do óleo é uma versão (T19), com a validade
dada pelas próprias datas dos períodos.
"""

import calendar
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal

from etl.python.etl1.cadastros import IBGE

from . import de_para
from .normalizacao import centro, chave, chave_contrato, mais_frequente, ponto, sigla_pelo_nome_do_poco

INICIO, FIM = datetime(1900, 1, 1), datetime(2199, 12, 31)
NA = "N/A"


def _igual(a, b) -> bool:
    if isinstance(a, (float, Decimal)) or isinstance(b, (float, Decimal)):
        return a is not None and b is not None and round(float(a), 7) == round(float(b), 7) or (a is None and b is None)
    return a == b


def scd2(dw, tabela: str, sufixo: str, registros: dict[str, dict], versionados: list[str], scd1: list[str], agora: datetime) -> dict[str, int]:
    """Aplica os registros (chave natural -> atributos) na dimensão. Devolve chave natural -> sk vigente."""
    colunas = versionados + scd1
    atuais = {r[1]: r for r in dw.execute(
        f"SELECT sk_{sufixo}, nk_{sufixo}, etl_versao, {', '.join(colunas)} FROM {tabela} "
        f"WHERE sk_{sufixo} <> 0 AND etl_dt_fim = %s", [FIM]).fetchall()}
    inserir = f"INSERT INTO {tabela} (nk_{sufixo}, {', '.join(colunas)}, etl_dt_inicio, etl_dt_fim, etl_versao) " \
              f"VALUES (%s, {', '.join(['%s'] * len(colunas))}, %s, %s, %s) RETURNING sk_{sufixo}"
    sk = {}
    for nk, attrs in registros.items():
        valores = [attrs[c] for c in colunas]
        if nk not in atuais:
            sk[nk] = dw.execute(inserir, [nk, *valores, INICIO, FIM, 1]).fetchone()[0]
            continue
        linha = atuais[nk]
        antigos = dict(zip(colunas, linha[3:]))
        if any(not _igual(antigos[c], attrs[c]) for c in versionados):
            dw.execute(f"UPDATE {tabela} SET etl_dt_fim = %s WHERE sk_{sufixo} = %s", [agora, linha[0]])
            sk[nk] = dw.execute(inserir, [nk, *valores, agora, FIM, linha[2] + 1]).fetchone()[0]
        else:
            sk[nk] = linha[0]
            mudou = [c for c in scd1 if not _igual(antigos[c], attrs[c])]
            if mudou:
                dw.execute(f"UPDATE {tabela} SET {', '.join(f'{c} = %s' for c in mudou)} WHERE sk_{sufixo} = %s",
                           [*(attrs[c] for c in mudou), linha[0]])
    return sk


def _q(st, sql, params=None):
    return st.execute(sql, params).fetchall()


# ---------------------------------------------------------------- empresa (T07, T14, T23)
def empresas(st, dw, agora, depara: list) -> dict[int, int]:
    """id_empresa da stage -> sk_empresa."""
    lista = de_para.empresas()
    grupos_lista = de_para.grupos_economicos()
    uso = dict(_q(st, "SELECT id_empresa, count(*) FROM cons GROUP BY 1"))
    uso_part = dict(_q(st, "SELECT id_empresa, count(*) FROM participacao_contrato GROUP BY 1"))
    grupos = defaultdict(list)
    for id_, nome, razao, grupo, pais in _q(st, """SELECT e.id_empresa, e.nome_fantasia, e.razao_social, g.nome, g.pais
                                                       FROM empresa e LEFT JOIN grupo_economico g USING (id_grupo)"""):
        k = chave(nome)
        grupos[lista.get(k, k)].append((id_, nome, razao, grupo, pais))
    registros, nk_de = {}, {}
    for nk, membros in grupos.items():
        membros.sort(key=lambda m: (-uso.get(m[0], 0), -uso_part.get(m[0], 0), m[1]))
        primeiro = lambda i: next((m[i] for m in membros if m[i]), NA)
        exibicao = Counter({m[1]: uso.get(m[0], 0) + uso_part.get(m[0], 0) for m in membros})
        grupo, pais = primeiro(3), primeiro(4)
        if grupo == NA and nk in grupos_lista:  # T23: a lista só completa o grupo que a ANP não publica
            grupo, pais = grupos_lista[nk]
        registros[nk] = {"nm_empresa": mais_frequente(exibicao), "nm_razao_social": primeiro(2),
                         "nm_grupo_economico": grupo, "nm_pais": pais}
        for m in membros:
            nk_de[m[0]] = nk
            depara.append(("dim_empresa", m[0], m[1], nk))
    sk = scd2(dw, "dim_empresa", "empresa", registros, ["nm_empresa", "nm_razao_social", "nm_grupo_economico", "nm_pais"], [], agora)
    return {id_: sk[nk] for id_, nk in nk_de.items()}, nk_de


# ---------------------------------------------------------------- contrato (T15)
def contratos(st, dw, agora, depara: list) -> dict[int, int]:
    grupos = defaultdict(list)
    for id_, numero, nome, rodada, fase, amb, bacia in _q(st, """SELECT c.id_contrato, c.numero, c.nome, c.rodada, c.fase, c.ambiente, b.nome
                                                             FROM contrato c LEFT JOIN bacia b USING (id_bacia)"""):
        nk = chave_contrato(numero)
        if nk:
            grupos[nk].append((id_, numero, nome, rodada, fase, amb, bacia))
    registros, nk_de = {}, {}
    for nk, membros in grupos.items():
        membros.sort(key=lambda m: (m[3] is None, m[0]))  # primeiro os da relação de concessionários (com rodada)
        primeiro = lambda i: next((m[i] for m in membros if m[i]), NA)
        registros[nk] = {"nr_contrato": nk, "nm_contrato": primeiro(2), "nm_rodada": primeiro(3), "nm_fase": primeiro(4),
                         "nm_ambiente": primeiro(5), "nm_bacia": primeiro(6)}
        for m in membros:
            nk_de[m[0]] = nk
            depara.append(("dim_contrato", m[0], m[1], nk))
    sk = scd2(dw, "dim_contrato", "contrato", registros,
              ["nr_contrato", "nm_contrato", "nm_rodada", "nm_fase", "nm_ambiente", "nm_bacia"], [], agora)
    return {id_: sk[nk] for id_, nk in nk_de.items()}, nk_de


# ---------------------------------------------------------------- trocas de operador (T23)
def ultimas_trocas(operadora_do_mes: dict, grupo_de: dict) -> tuple:
    """(mês da última troca de operador, da última venda, da última reorganização) de um campo.

    Troca: a operadora predominante muda de um mês com produção para o seguinte. Venda: a troca em que o grupo
    econômico também muda; dentro do mesmo grupo (subsidiária, renomeação), é reorganização. Empresa sem grupo conta
    como grupo próprio. O operador "-" da fonte (sem operador informado) não conta como troca.
    """
    ordem = [m for m in sorted(operadora_do_mes) if operadora_do_mes[m] not in (NA, "-")]
    troca = venda = reorganizacao = None
    for antes, mes in zip(ordem, ordem[1:]):
        a, d = operadora_do_mes[antes], operadora_do_mes[mes]
        if a != d:
            troca = mes
            if grupo_de.get(a, a) != grupo_de.get(d, d):
                venda = mes
            else:
                reorganizacao = mes
    return troca, venda, reorganizacao


# ---------------------------------------------------------------- campo (T04, T05, T14, T20, T23)
def _estados(st) -> dict[str, tuple[str, str]]:
    """Sigla -> (nome, região): o cadastro da stage completado pela tabela fixa do IBGE."""
    estados = {sigla: (nome, regiao) for nome, sigla, regiao in _q(st, "SELECT nome, sigla, regiao FROM estado WHERE sigla IS NOT NULL")}
    for nome_sem_acento, (sigla, regiao) in IBGE.items():
        estados.setdefault(sigla, (nome_sem_acento.title(), regiao))
    return estados


def _sigla_dos_pocos(st, estados: dict) -> dict[int, str | None]:
    """Estado de cada poço (T13): pelo sufixo do nome (T13a) ou, sem sufixo válido, o estado mais informado (T13b)."""
    sigla_de = {id_: s for id_, s in _q(st, "SELECT id_estado, sigla FROM estado")}
    return {id_: sigla_pelo_nome_do_poco(nome, set(estados)) or sigla_de.get(est)
            for id_, nome, est in _q(st, """SELECT p.id_poco, p.nome_anp, mode() WITHIN GROUP (ORDER BY c.id_estado)
                                            FROM cons c JOIN poco p USING (id_poco) GROUP BY 1, 2""")}


def campos(st, dw, agora, depara: list, nk_empresa: dict[int, str]) -> dict[int, int]:
    eventos = de_para.campos()
    uso = dict(_q(st, "SELECT id_campo, count(*) FROM cons GROUP BY 1"))
    grupos = defaultdict(list)
    for id_, nome, bacia in _q(st, "SELECT c.id_campo, c.nome, b.nome FROM campo c JOIN bacia b USING (id_bacia)"):
        if id_ in uso:  # a dimensão traz os campos da produção; os da camada de contornos só fornecem o contorno
            grupos[(chave(nome), chave(bacia))].append((id_, nome, bacia))
    exib = {k: (mais_frequente(Counter({m[1]: uso[m[0]] for m in ms})), mais_frequente(Counter({m[2]: uso[m[0]] for m in ms})))
            for k, ms in grupos.items()}

    # contornos (T20): a camada usa grafias próprias; casa pelo nome + bacia, ou só pelo nome se ele for único
    por_nome = defaultdict(list)
    for k in grupos:
        por_nome[k[0]].append(k)
    contorno = {}
    for _id_campo, nome, bacia, wkt in _q(st, """SELECT c.id_campo, c.nome, b.nome, cc.geometria_wkt FROM coordenada_campo cc
                                          JOIN campo c USING (id_campo) JOIN bacia b USING (id_bacia)
                                          WHERE cc.id_carga = (SELECT max(id_carga) FROM coordenada_campo x WHERE x.id_campo = cc.id_campo)"""):
        k = (chave(nome), chave(bacia))
        if k not in grupos and len(por_nome.get(k[0], [])) == 1:
            k = por_nome[k[0]][0]
        if k in grupos:
            contorno.setdefault(k, wkt)

    # mês da última troca de operador (operador predominante de cada mês, já uniformizado)
    op_mes = defaultdict(dict)
    id_para_k = {m[0]: k for k, ms in grupos.items() for m in ms}
    contagem = defaultdict(Counter)
    for id_campo, periodo, id_empresa, n in _q(st, "SELECT id_campo, periodo, id_empresa, count(*) FROM cons GROUP BY 1, 2, 3"):
        contagem[(id_para_k[id_campo], periodo)][nk_empresa.get(id_empresa, NA)] += n
    for (k, periodo), c in contagem.items():
        op_mes[k][periodo] = mais_frequente(c)
    grupo_de = {nk: g for nk, g in dw.execute("""SELECT nk_empresa, nm_grupo_economico FROM dim_empresa
                                                   WHERE sk_empresa <> 0 AND etl_dt_fim = '2199-12-31'
                                                     AND nm_grupo_economico <> 'N/A'""").fetchall()}
    ultima_troca = {k: ultimas_trocas(meses, grupo_de) for k, meses in op_mes.items()}

    # estado e região do campo: o estado mais frequente nos registros de produção dos seus poços (T13); no empate,
    # a sigla em ordem alfabética
    estados = _estados(st)
    sigla_poco = _sigla_dos_pocos(st, estados)
    uf_campo = defaultdict(Counter)
    for id_campo, id_poco, n in _q(st, "SELECT id_campo, id_poco, count(*) FROM cons GROUP BY 1, 2"):
        if sigla_poco.get(id_poco):
            uf_campo[id_para_k[id_campo]][sigla_poco[id_poco]] += n
    uf = {k: min(c.items(), key=lambda x: (-x[1], x[0]))[0] for k, c in uf_campo.items()}

    registros, nk_de = {}, {}
    for k, membros in grupos.items():
        nk = f"{k[0]}|{k[1]}"
        sigla = uf.get(k)
        nm_estado, regiao = estados.get(sigla, (NA, NA))
        atual = de_para.resolver(k, eventos, {"renomeacao"})
        sucessor = de_para.resolver(k, eventos, {"renomeacao", "unificacao"})
        nome_de = lambda kk: exib[kk][0] if kk in exib else next(e["destino_nome"] for e in eventos if e["destino"] == kk)
        wkt = contorno.get(k) or contorno.get(atual)
        c = centro(wkt)
        registros[nk] = {"nm_campo": exib[k][0], "nm_campo_atual": nome_de(atual), "nm_campo_sucessor": nome_de(sucessor),
                         "nm_bacia": exib[k][1], "nm_estado": nm_estado, "sg_estado": sigla or "NA", "nm_regiao": regiao,
                         "desc_contorno_wkt": wkt,
                         "nr_latitude_centro": round(c[0], 7) if c else None, "nr_longitude_centro": round(c[1], 7) if c else None,
                         "dt_ultima_troca_operador": ultima_troca.get(k, (None,) * 3)[0],
                         "dt_ultima_venda": ultima_troca.get(k, (None,) * 3)[1],
                         "dt_ultima_reorganizacao": ultima_troca.get(k, (None,) * 3)[2]}
        for m in membros:
            nk_de[m[0]] = nk
            depara.append(("dim_campo", m[0], f"{m[1]} ({m[2]})", nk))
    sk = scd2(dw, "dim_campo", "campo", registros,
              ["nm_campo", "nm_campo_atual", "nm_campo_sucessor", "nm_bacia", "nm_estado", "sg_estado", "nm_regiao", "desc_contorno_wkt",
               "nr_latitude_centro", "nr_longitude_centro"], ["dt_ultima_troca_operador", "dt_ultima_venda", "dt_ultima_reorganizacao"], agora)
    return {id_: sk[nk] for id_, nk in nk_de.items()}, nk_de


# ---------------------------------------------------------------- poço (T13, T16)
def pocos(st, dw, agora, depara: list) -> dict[int, int]:
    estados = _estados(st)
    sigla_poco = _sigla_dos_pocos(st, estados)
    presal = {r[0] for r in _q(st, "SELECT id_poco FROM pocos_presal")}
    info = {}
    for id_, nome, origem, est, primeira, ultima in _q(st, """
            SELECT p.id_poco, p.nome_anp, mode() WITHIN GROUP (ORDER BY c.arquivo_origem),
                   mode() WITHIN GROUP (ORDER BY c.id_estado),
                   min(c.periodo) FILTER (WHERE coalesce(c.petroleo_bbl_dia, 0) + coalesce(c.gas_total_mm3_dia, 0) > 0),
                   max(c.periodo) FILTER (WHERE coalesce(c.petroleo_bbl_dia, 0) + coalesce(c.gas_total_mm3_dia, 0) > 0)
            FROM cons c JOIN poco p USING (id_poco) GROUP BY 1, 2"""):
        info[id_] = (nome, origem, est, primeira, ultima)
    coord = {id_: ponto(wkt) for id_, wkt in _q(st, """SELECT id_poco, geometria_wkt FROM coordenada_poco cp
                                                      WHERE id_carga = (SELECT max(id_carga) FROM coordenada_poco x WHERE x.id_poco = cp.id_poco)""")}
    registros, nk_de = {}, {}
    for id_, (nome, origem, est, primeira, ultima) in info.items():
        sigla = sigla_poco[id_]  # T13a pelo sufixo; T13b estado conhecido
        nm_estado, regiao = estados.get(sigla, (NA, NA))
        latlon = coord.get(id_)
        registros[nome] = {"nm_poco": nome, "nm_estado": nm_estado, "sg_estado": sigla or "NA", "nm_regiao": regiao,
                           "nm_ambiente": "Pré-sal" if id_ in presal else {"terra": "Terra", "mar": "Mar"}[origem],
                           "nr_latitude": round(latlon[0], 7) if latlon else None, "nr_longitude": round(latlon[1], 7) if latlon else None,
                           "dt_primeira_producao": primeira, "dt_ultima_producao": ultima}
        nk_de[id_] = nome
        depara.append(("dim_poco", id_, nome, nome))
    sk = scd2(dw, "dim_poco", "poco", registros,
              ["nm_poco", "nm_estado", "sg_estado", "nm_regiao", "nm_ambiente", "nr_latitude", "nr_longitude"],
              ["dt_primeira_producao", "dt_ultima_producao"], agora)
    return {id_: sk[nk] for id_, nk in nk_de.items()}, nk_de


# ---------------------------------------------------------------- instalação (T13c, T14)
def instalacoes(st, dw, agora, depara: list) -> dict[int, int]:
    grupos = defaultdict(list)
    for id_, nome, n, tipo in _q(st, """SELECT i.id_instalacao, i.nome, count(*),
                                              (array_agg(c.tipo_instalacao ORDER BY c.periodo DESC) FILTER (WHERE c.tipo_instalacao IS NOT NULL))[1]
                                       FROM cons c JOIN instalacao i USING (id_instalacao) GROUP BY 1, 2"""):
        grupos[chave(nome)].append((id_, nome, n, tipo))
    registros, nk_de = {}, {}
    for nk, membros in grupos.items():
        membros.sort(key=lambda m: -m[2])
        registros[nk] = {"nm_instalacao": mais_frequente(Counter({m[1]: m[2] for m in membros})),
                         "nm_tipo_instalacao": next((m[3] for m in membros if m[3]), NA)}
        for m in membros:
            nk_de[m[0]] = nk
            depara.append(("dim_instalacao", m[0], m[1], nk))
    sk = scd2(dw, "dim_instalacao", "instalacao", registros, ["nm_instalacao", "nm_tipo_instalacao"], [], agora)
    return {id_: sk[nk] for id_, nk in nk_de.items()}, nk_de


# ---------------------------------------------------------------- corrente (T14, T19)
OLEO = ["grau_api", "dest_leve_corte", "dest_leve_pct", "dest_medio_corte", "dest_medio_pct", "dest_pesado_corte", "dest_pesado_pct"]


def correntes(st, dw, agora, depara: list) -> tuple[dict[int, int], None]:
    """id_caracterizacao da stage -> sk_corrente da versão do seu período de carga (só a análise do óleo, T19).

    Mesma assinatura das outras dimensões; aqui `agora` não é usado, porque a validade de cada versão vem das datas
    dos períodos de carga, e não do momento da carga."""
    linhas = _q(st, f"""SELECT cp.id_caracterizacao, co.id_corrente, co.nome, cp.periodo_carga, {', '.join('cp.' + c for c in OLEO)}
                        FROM caracterizacao_petroleo cp JOIN corrente co USING (id_corrente)
                        WHERE cp.id_caracterizacao IN (SELECT DISTINCT id_caracterizacao FROM cons)""")
    nomes = defaultdict(Counter)
    analise = {}
    for _id_car, _id_cor, nome, periodo, *oleo in linhas:
        k = chave(nome)
        nomes[k][nome] += 1
        atual = analise.get((k, periodo))
        if atual is None or sum(v is not None for v in oleo) > sum(v is not None for v in atual):
            analise[(k, periodo)] = oleo
    existentes = {(nk, dt): sk for sk, nk, dt in dw.execute(
        "SELECT sk_corrente, nk_corrente, dt_periodo_carga FROM dim_corrente WHERE sk_corrente <> 0").fetchall()}
    for (k, periodo), oleo in sorted(analise.items(), key=lambda x: (x[0][0], x[0][1])):
        if (k, periodo) not in existentes:
            versao = dw.execute("SELECT coalesce(max(etl_versao), 0) + 1 FROM dim_corrente WHERE nk_corrente = %s", [k]).fetchone()[0]
            existentes[(k, periodo)] = dw.execute(
                f"""INSERT INTO dim_corrente (nk_corrente, nm_corrente, dt_periodo_carga, nr_grau_api, nm_dest_leve_corte, nr_dest_leve_pct,
                    nm_dest_medio_corte, nr_dest_medio_pct, nm_dest_pesado_corte, nr_dest_pesado_pct, etl_dt_inicio, etl_dt_fim, etl_versao)
                    VALUES (%s, %s, %s, {', '.join(['%s'] * len(OLEO))}, %s, %s, %s) RETURNING sk_corrente""",
                [k, mais_frequente(nomes[k]), periodo, *oleo, INICIO, FIM, versao]).fetchone()[0]
    # validade pelas datas dos períodos de carga: cada versão vale até o período seguinte
    dw.execute("""UPDATE dim_corrente d SET etl_dt_inicio = CASE WHEN x.etl_versao = 1 THEN %s ELSE x.dt_periodo_carga END,
                                            etl_dt_fim = coalesce(x.proximo, %s)
                  FROM (SELECT sk_corrente, etl_versao, dt_periodo_carga,
                               lead(dt_periodo_carga) OVER (PARTITION BY nk_corrente ORDER BY dt_periodo_carga) AS proximo
                        FROM dim_corrente WHERE sk_corrente <> 0) x
                  WHERE d.sk_corrente = x.sk_corrente""", [INICIO, FIM])
    mapa, vistos = {}, set()
    for id_car, id_cor, nome, periodo, *_ in linhas:
        mapa[id_car] = existentes[(chave(nome), periodo)]
        if id_cor not in vistos:  # uma linha de-para por corrente da stage
            vistos.add(id_cor)
            depara.append(("dim_corrente", id_cor, nome, chave(nome)))
    return mapa, None


def dias_do_mes(periodo: date) -> int:
    return calendar.monthrange(periodo.year, periodo.month)[1]
