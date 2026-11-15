"""Cadastros da stage: encontra ou cria cada entidade pela grafia exata da fonte (C01).

Os IDs ficam em memória para não consultar o banco a cada linha. Atributos de uma
entidade que já existe só são preenchidos quando estão vazios: nada é sobrescrito.
"""

import unicodedata

# Tabela fixa do IBGE: sigla e região de cada estado (chave = nome sem acento, em maiúsculas).
IBGE = {
    "ACRE": ("AC", "Norte"), "ALAGOAS": ("AL", "Nordeste"), "AMAPA": ("AP", "Norte"), "AMAZONAS": ("AM", "Norte"),
    "BAHIA": ("BA", "Nordeste"), "CEARA": ("CE", "Nordeste"), "DISTRITO FEDERAL": ("DF", "Centro-Oeste"),
    "ESPIRITO SANTO": ("ES", "Sudeste"), "GOIAS": ("GO", "Centro-Oeste"), "MARANHAO": ("MA", "Nordeste"),
    "MATO GROSSO": ("MT", "Centro-Oeste"), "MATO GROSSO DO SUL": ("MS", "Centro-Oeste"), "MINAS GERAIS": ("MG", "Sudeste"),
    "PARA": ("PA", "Norte"), "PARAIBA": ("PB", "Nordeste"), "PARANA": ("PR", "Sul"), "PERNAMBUCO": ("PE", "Nordeste"),
    "PIAUI": ("PI", "Nordeste"), "RIO DE JANEIRO": ("RJ", "Sudeste"), "RIO GRANDE DO NORTE": ("RN", "Nordeste"),
    "RIO GRANDE DO SUL": ("RS", "Sul"), "RONDONIA": ("RO", "Norte"), "RORAIMA": ("RR", "Norte"),
    "SANTA CATARINA": ("SC", "Sul"), "SAO PAULO": ("SP", "Sudeste"), "SERGIPE": ("SE", "Nordeste"), "TOCANTINS": ("TO", "Norte"),
}

CARAC_COLUNAS = [
    "periodo_carga", "grau_api", "dest_leve_corte", "dest_leve_pct", "dest_medio_corte", "dest_medio_pct",
    "dest_pesado_corte", "dest_pesado_pct", "pct_metano", "pct_etano", "pct_propano", "pct_isobutano", "pct_butano",
    "pct_isopentano", "pct_n_pentano", "pct_hexanos", "pct_heptanos", "pct_octanos", "pct_nonanos", "pct_decanos",
    "pct_undecanos", "pct_oxigenio", "pct_nitrogenio", "pct_gas_carbonico", "densidade_glp_gas",
    "densidade_glp_liquido", "pcs_kj_m3",
]


def _sem_acento(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().upper().strip()


class Cadastros:
    def __init__(self, conn):
        self.conn = conn
        self.novos = {}  # tabela -> quantidade criada nesta execução
        self._carregar()

    def _carregar(self):
        q = lambda sql: self.conn.execute(sql).fetchall()
        self.estado = {nome: i for i, nome in q("SELECT id_estado, nome FROM estado")}
        self.bacia = {nome: i for i, nome in q("SELECT id_bacia, nome FROM bacia")}
        self.campo = {(nome, b): i for i, nome, b in q("SELECT id_campo, nome, id_bacia FROM campo")}
        self.poco = {nome: i for i, nome in q("SELECT id_poco, nome_anp FROM poco")}
        self.instalacao = {nome: i for i, nome in q("SELECT id_instalacao, nome FROM instalacao")}
        self.corrente = {nome: i for i, nome in q("SELECT id_corrente, nome FROM corrente")}
        self.grupo = {nome: i for i, nome in q("SELECT id_grupo, nome FROM grupo_economico")}
        self.empresa = {nome: [i, rs, cnpj, g] for i, nome, rs, cnpj, g in
                        q("SELECT id_empresa, nome_fantasia, razao_social, cnpj, id_grupo FROM empresa")}
        self.contrato = {num: [i, nome, rod, fase, amb, b] for i, num, nome, rod, fase, amb, b in
                         q("SELECT id_contrato, numero, nome, rodada, fase, ambiente, id_bacia FROM contrato")}
        cols = ", ".join(CARAC_COLUNAS)
        self.caracterizacao = {(r[1], *r[2:]): r[0] for r in
                               q(f"SELECT id_caracterizacao, id_corrente, {cols} FROM caracterizacao_petroleo")}

    def _inserir(self, tabela: str, pk: str, valores: dict) -> int:
        cols = ", ".join(valores)
        marcas = ", ".join(["%s"] * len(valores))
        novo_id = self.conn.execute(f"INSERT INTO {tabela} ({cols}) VALUES ({marcas}) RETURNING {pk}",
                                    list(valores.values())).fetchone()[0]
        self.novos[tabela] = self.novos.get(tabela, 0) + 1
        return novo_id

    # --- entidades simples (só o nome) ---------------------------------------
    def id_estado(self, nome):
        if nome is None:
            return None
        if nome not in self.estado:
            sigla, regiao = IBGE.get(_sem_acento(nome), (None, None))
            self.estado[nome] = self._inserir("estado", "id_estado", {"nome": nome, "sigla": sigla, "regiao": regiao})
        return self.estado[nome]

    def _simples(self, cache, tabela, pk, coluna, nome):
        if nome is None:
            return None
        if nome not in cache:
            cache[nome] = self._inserir(tabela, pk, {coluna: nome})
        return cache[nome]

    def id_bacia(self, nome):
        return self._simples(self.bacia, "bacia", "id_bacia", "nome", nome)

    def id_poco(self, nome):
        return self._simples(self.poco, "poco", "id_poco", "nome_anp", nome)

    def id_instalacao(self, nome):
        return self._simples(self.instalacao, "instalacao", "id_instalacao", "nome", nome)

    def id_corrente(self, nome):
        return self._simples(self.corrente, "corrente", "id_corrente", "nome", nome)

    def id_campo(self, nome, nome_bacia):
        id_bacia = self.id_bacia(nome_bacia)
        chave = (nome, id_bacia)
        if chave not in self.campo:
            self.campo[chave] = self._inserir("campo", "id_campo", {"nome": nome, "id_bacia": id_bacia})
        return self.campo[chave]

    # --- entidades com atributos (preenchidos só se estiverem vazios) --------
    def id_grupo(self, nome, pais=None):
        if nome is None:
            return None
        if nome not in self.grupo:
            self.grupo[nome] = self._inserir("grupo_economico", "id_grupo", {"nome": nome, "pais": pais})
        return self.grupo[nome]

    def id_empresa(self, nome, razao_social=None, cnpj=None, id_grupo=None):
        if nome is None:
            return None
        if nome not in self.empresa:
            novo = self._inserir("empresa", "id_empresa",
                                 {"nome_fantasia": nome, "razao_social": razao_social, "cnpj": cnpj, "id_grupo": id_grupo})
            self.empresa[nome] = [novo, razao_social, cnpj, id_grupo]
        else:
            reg = self.empresa[nome]
            faltando = {c: v for c, v, atual in (("razao_social", razao_social, reg[1]), ("cnpj", cnpj, reg[2]),
                                                  ("id_grupo", id_grupo, reg[3])) if v is not None and atual is None}
            if faltando:
                sets = ", ".join(f"{c} = %s" for c in faltando)
                self.conn.execute(f"UPDATE empresa SET {sets} WHERE id_empresa = %s", [*faltando.values(), reg[0]])
                for c, v in faltando.items():
                    reg[{"razao_social": 1, "cnpj": 2, "id_grupo": 3}[c]] = v
        return self.empresa[nome][0]

    def id_contrato(self, numero, nome=None, rodada=None, fase=None, ambiente=None, id_bacia=None):
        if numero is None:
            return None
        if numero not in self.contrato:
            novo = self._inserir("contrato", "id_contrato", {"numero": numero, "nome": nome, "rodada": rodada,
                                                             "fase": fase, "ambiente": ambiente, "id_bacia": id_bacia})
            self.contrato[numero] = [novo, nome, rodada, fase, ambiente, id_bacia]
        else:
            reg = self.contrato[numero]
            pos = {"nome": 1, "rodada": 2, "fase": 3, "ambiente": 4, "id_bacia": 5}
            faltando = {c: v for c, v in (("nome", nome), ("rodada", rodada), ("fase", fase), ("ambiente", ambiente),
                                          ("id_bacia", id_bacia)) if v is not None and reg[pos[c]] is None}
            if faltando:
                sets = ", ".join(f"{c} = %s" for c in faltando)
                self.conn.execute(f"UPDATE contrato SET {sets} WHERE id_contrato = %s", [*faltando.values(), reg[0]])
                for c, v in faltando.items():
                    reg[pos[c]] = v
        return self.contrato[numero][0]

    def id_caracterizacao(self, c: dict | None):
        """Cada combinação distinta de valores é uma linha (não há chave única corrente + período, T19)."""
        if c is None:
            return None
        id_corrente = self.id_corrente(c["corrente"])  # pode ser NULL: há análises só do gás, sem corrente
        chave = (id_corrente, *(c[col] for col in CARAC_COLUNAS))
        if chave not in self.caracterizacao:
            self.caracterizacao[chave] = self._inserir(
                "caracterizacao_petroleo", "id_caracterizacao", {"id_corrente": id_corrente, **{col: c[col] for col in CARAC_COLUNAS}})
        return self.caracterizacao[chave]
