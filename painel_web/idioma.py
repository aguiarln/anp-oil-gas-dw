"""Idioma do painel (português ou inglês): o seletor da barra lateral e a tradução dos textos.

O português é o padrão e a chave da tradução: t("texto em português") devolve o texto em inglês quando o idioma
escolhido é EN. Os textos com valores usam campos nomeados: t("Petróleo em {ano}", ano=2023). Os nomes publicados
pela ANP (campos, bacias, empresas, ambientes) não são traduzidos. O idioma fica no link (?lang=en).
"""
import streamlit as st

IDIOMAS = {"pt": "PT", "en": "EN"}


def atual() -> str:
    return st.session_state.get("idioma", "pt")


def seletor():
    """Botão PT | EN no topo da barra lateral; o idioma escolhido vai para o link, para ser compartilhado."""
    if "idioma" not in st.session_state:
        st.session_state["idioma"] = "en" if st.query_params.get("lang") == "en" else "pt"
    st.sidebar.segmented_control("🌐 Idioma · Language", list(IDIOMAS), format_func=IDIOMAS.get, key="idioma",
                                 required=True)
    st.query_params["lang"] = atual()


def chave(nome: str) -> str:
    """Chave de um seletor com opções traduzidas, uma por idioma: com a mesma chave, o Streamlit continuaria mostrando
    o rótulo do idioma anterior. O valor escolhido fica em st.session_state[nome], que vale para os dois idiomas."""
    return f"{nome}_{atual()}"


def t(texto: str, **campos) -> str:
    s = EN.get(texto, texto) if atual() == "en" else texto
    return s.format(**campos) if campos else s


EN = {
    # navegação e barra lateral
    "Campos maduros de petróleo e gás": "Mature oil and gas fields",
    "1. Campos candidatos": "1. Candidate fields",
    "2. Ficha do campo": "2. Field sheet",
    "3. Vendedores e sócios": "3. Sellers and partners",
    "4. Trocas de operador": "4. Operator changes",
    "Produção, declínio, maturidade, receita e trocas de operador dos campos do Brasil":
        "Production, decline, maturity, revenue and operator changes of Brazil's fields",
    "Região": "Region",
    "Estado": "State",
    "Brasil": "Brazil",
    "Todos": "All",
    "Ano de referência": "Reference year",
    "Ano dos indicadores das telas 1 a 3; por padrão, o último com dados.":
        "Year of the indicators on screens 1 to 3; by default, the latest with data.",
    "Poço parado: meses sem produção": "Idle well: months without production",
    "Um poço é considerado parado se já produziu e está sem produção há pelo menos esses meses.":
        "A well is idle if it has produced before and has had no production for at least this many months.",
    "📖 Siglas e unidades": "📖 Acronyms and units",
    "Fonte: dados públicos da ANP (2005–2023), Data Warehouse `dw_anp`.":
        "Source: ANP public data (2005–2023), Data Warehouse `dw_anp`.",
    # siglas e unidades (rótulos)
    "bbl/dia": "bbl/day",
    "RGO": "GOR",
    "Petróleo": "Oil",
    "Poço parado": "Idle well",
    "Variação anual": "Annual change",
    "Preço": "Price",
    "Receita estimada": "Estimated revenue",
    # rótulos comuns
    "Campo": "Field",
    "Bacia": "Basin",
    "Ambiente": "Environment",
    "Operadora": "Operator",
    "Empresa": "Company",
    "Contrato": "Contract",
    "Papel": "Role",
    "Participação": "Share",
    "operadora": "operator",
    "sócia": "partner",
    "Poço": "Well",
    "Poços parados": "Idle wells",
    "Poços produtores": "Producing wells",
    "Petróleo (bbl/dia)": "Oil (bbl/day)",
    "RGO (m³/m³)": "GOR (m³/m³)",
    "Todas": "All",
    "Receita estimada {ano}": "Estimated revenue {ano}",
    # tela 1
    "Campos candidatos": "Candidate fields",
    "ano {ano}": "year {ano}",
    "Quais campos merecem atenção? Compare produção, declínio, maturidade e receita, e abra a ficha do campo.":
        "Which fields deserve attention? Compare production, decline, maturity and revenue, and open the field sheet.",
    "Faixa de produção de petróleo (bbl/dia)": "Oil production range (bbl/day)",
    "Campos maduros de pequena e média produção são os candidatos típicos à venda para operadoras independentes.":
        "Mature fields with small and medium production are the typical candidates for sale to independent operators.",
    "Campos na seleção": "Fields selected",
    "Petróleo em {ano} (bbl/dia)": "Oil in {ano} (bbl/day)",
    "Campos em declínio": "Fields in decline",
    "{n} de {total}": "{n} of {total}",
    "Caem menos que a bacia": "Decline less than the basin",
    "Campos cuja variação anual é melhor que a da sua bacia: os melhores candidatos.":
        "Fields whose annual change beats their basin's: the best candidates.",
    "Indicadores por campo": "Indicators by field",
    "Diferença p/ bacia (p.p.)": "Difference to basin (p.p.)",
    "Variação anual do campo menos a da bacia, em pontos percentuais.":
        "Annual change of the field minus the basin's, in percentage points.",
    "Receita (R$ mi)": "Revenue (R$ mi)",
    "Última venda": "Last sale",
    "Última troca de operador em que o grupo econômico mudou.":
        "Last operator change in which the economic group changed.",
    "Abrir a ficha do campo": "Open the field sheet",
    "Escolha um campo da seleção": "Choose a field from the selection",
    "Abrir ficha": "Open sheet",
    "Mapa dos campos selecionados": "Map of the selected fields",
    "Cor mais escura = mais produção (bbl/dia, escala logarítmica). "
    "{sem} campo(s) da seleção sem contorno publicado pela ANP.":
        "Darker color = more production (bbl/day, log scale). "
        "{sem} selected field(s) without an outline published by ANP.",
    # tela 2
    "bacia {bacia}": "basin {bacia}",
    "dados até {mes}": "data up to {mes}",
    "operadora atual: **{op}**": "current operator: **{op}**",
    "última venda em {mes}": "last sale in {mes}",
    "reorganização no mesmo grupo em {mes}": "reorganization within the same group in {mes}",
    "nome atual: {nome}": "current name: {nome}",
    "unificado em: {nome}": "merged into: {nome}",
    "Petróleo em {mes}": "Oil in {mes}",
    "{valor} bbl/dia": "{valor} bbl/day",
    "Variação {ano} × {anterior}": "Change {ano} × {anterior}",
    "bacia: {valor}": "basin: {valor}",
    "BSW (12 meses)": "BSW (12 months)",
    "Produtores / parados": "Producing / idle",
    "Produtores em {mes}. {parado} ({meses} meses).": "Producing in {mes}. {parado} ({meses} months).",
    "petróleo (bbl/dia)": "oil (bbl/day)",
    "Produção de petróleo por ano e operadora (a troca aparece na mudança de cor)":
        "Oil production by year and operator (a change shows as a change of color)",
    "Produção por ano": "Production by year",
    "Ano": "Year",
    "Óleo": "Crude oil",
    "Condensado": "Condensate",
    "Gás assoc.": "Assoc. gas",
    "Gás não assoc.": "Non-assoc. gas",
    "Gás total": "Total gas",
    "Água": "Water",
    "Var. petróleo": "Oil chg.",
    "Var. gás": "Gas chg.",
    "Médias diárias de cada ano: óleo, condensado, petróleo e água em bbl/dia; gás em mil m³/dia.":
        "Daily averages for each year: oil, condensate, petroleum and water in bbl/d; gas in thousand m³/d.",
    "Maturidade (BSW)": "Maturity (BSW)",
    "Receita e preço": "Revenue and price",
    "BSW mensal: quanto mais água, mais maduro o campo": "Monthly BSW: the more water, the more mature the field",
    "receita (R$ mi)": "revenue (R$ mi)",
    "preço médio (R$/m³)": "average price (R$/m³)",
    "R$ milhões": "R$ millions",
    " preço mínimo → referência": " minimum price → reference price",
    "Receita estimada por ano e preço médio do petróleo": "Estimated revenue by year and average oil price",
    "Mapa: contorno do campo e poços": "Map: field outline and wells",
    "produtor": "producing",
    "parado há {meses}+ meses": "idle for {meses}+ months",
    "sem produção recente": "no recent production",
    "parado": "idle",
    "{poco}\n{situacao}, último mês com produção: {ultimo}": "{poco}\n{situacao}, last month with production: {ultimo}",
    "A ANP não publica o contorno deste campo; o mapa mostra só os poços.":
        "ANP does not publish this field's outline; the map shows only the wells.",
    "Sócios dos contratos": "Contract partners",
    "Foto da relação de concessionários da ANP de {data}.": "Snapshot of ANP's list of concession holders of {data}.",
    "Último mês com produção": "Last month with production",
    "Último mês": "Last month",
    "Antes de parar (bbl/dia)": "Before stopping (bbl/day)",
    "Petróleo médio do poço nos 12 meses até o último mês com produção: o "
    "tamanho da oportunidade de voltar a produzir nele.":
        "The well's average oil over the 12 months up to its last month with production: "
        "the size of the opportunity to bring it back.",
    # tela 3
    "Vendedores e sócios": "Sellers and partners",
    "Quem opera os campos hoje? As operadoras com muitos campos pequenos e os campos ainda com a Petrobras "
    "são os vendedores mais prováveis.":
        "Who operates the fields today? Operators with many small fields and the fields still with Petrobras "
        "are the most likely sellers.",
    "Campo pequeno: produção de até (bbl/dia)": "Small field: production up to (bbl/day)",
    "Campos com produção de petróleo no último ano abaixo desse valor contam como pequenos.":
        "Fields whose oil production in the last year is below this value count as small.",
    "Operadoras com produção": "Operators with production",
    "Campos ainda com a Petrobras": "Fields still with Petrobras",
    "Operadoras com 5+ campos pequenos": "Operators with 5+ small fields",
    "campos operados": "fields operated",
    "outros campos": "other fields",
    "campos pequenos (até {limite} bbl/dia)": "small fields (up to {limite} bbl/day)",
    "Operadoras com mais campos (as 15 maiores)": "Operators with the most fields (top 15)",
    "Operadoras": "Operators",
    "Grupo econômico": "Economic group",
    "País": "Country",
    "Campos": "Fields",
    "Pequenos": "Small",
    "Petróleo {mes} (bbl/dia)": "Oil {mes} (bbl/day)",
    "Campos e sócios de uma operadora": "Fields and partners of an operator",
    "Sócios dos contratos desses campos na foto da ANP de {data}: "
    "com quem negociar, e se a compra seria do contrato inteiro ou de uma parte.":
        "Partners in these fields' contracts in ANP's snapshot of {data}: "
        "who to negotiate with, and whether the purchase would be the whole contract or a share.",
    # tela 4
    "Trocas de operador": "Operator changes",
    "Os campos vendidos melhoraram com os novos operadores? Comparação da produção média nos 12 meses antes e "
    "depois da última venda de cada campo. Venda é a troca em que o grupo econômico da operadora muda; as "
    "reorganizações dentro do mesmo grupo (subsidiárias, mudanças de nome) aparecem escolhendo o tipo de troca.":
        "Did the fields sold improve with the new operators? Average production in the 12 months before and after "
        "each field's last sale. A sale is a change in which the operator's economic group changes; reorganizations "
        "within the same group (subsidiaries, name changes) appear when choosing the type of change.",
    "Tipo de troca": "Type of change",
    "Vendas": "Sales",
    "Reorganizações": "Reorganizations",
    "Todas as trocas": "All changes",
    "Venda: o grupo econômico da operadora muda. Reorganização: troca dentro do mesmo grupo, "
    "como 3R Macau → 3R Potiguar ou uma mudança de nome revisada pela ANP.":
        "Sale: the operator's economic group changes. Reorganization: a change within the same group, "
        "such as 3R Macau → 3R Potiguar or a name change revised by ANP.",
    "Nenhuma troca desse tipo com os filtros escolhidos.": "No change of this type with the chosen filters.",
    "Ano da troca": "Year of change",
    "Só campos que saíram da Petrobras": "Only fields that left Petrobras",
    "Só com 12 meses depois da troca": "Only with 12 months after the change",
    "Trocas recentes ainda não têm 12 meses de dados depois da troca.":
        "Recent changes do not have 12 months of data after the change yet.",
    "Trocas analisadas": "Changes analyzed",
    "Campos que melhoraram": "Fields that improved",
    "Variação mediana da produção": "Median production change",
    "Produção média (bbl/dia) dos 12 meses depois ÷ 12 meses antes da troca.":
        "Average production (bbl/day) in the 12 months after ÷ 12 months before the change.",
    "Variação mediana do BSW (p.p.)": "Median BSW change (p.p.)",
    "melhorou": "improved",
    "piorou": "worsened",
    "12 meses antes (bbl/dia)": "12 months before (bbl/day)",
    "12 meses depois (bbl/dia)": "12 months after (bbl/day)",
    "Antes × depois: acima da diagonal, o campo melhorou": "Before × after: above the diagonal, the field improved",
    "Campos com troca de operador": "Fields with an operator change",
    "Troca": "Change",
    "Antes": "Before",
    "Depois": "After",
    "Antes (bbl/dia)": "Before (bbl/day)",
    "Depois (bbl/dia)": "After (bbl/day)",
    "Variação": "Change",
    "BSW antes": "BSW before",
    "BSW depois": "BSW after",
}

SIGLAS_EN = {
    "bbl": "barrel of oil (1 bbl = 0.159 m³)",
    "bbl/dia": "barrels per day: the period's volume divided by the days in the period",
    "BSW": "Basic Sediment and Water: share of water and sediment in the produced liquid. The more water, the more "
           "mature the field",
    "RGO": "Gas-Oil Ratio: m³ of associated gas per m³ of oil produced; rising, it signals an aging reservoir",
    "m³": "cubic meter; thousand m³ = 1,000 m³ (natural gas unit)",
    "Petróleo": "oil + condensate, as published by ANP",
    "Poço parado": "a well that has produced before and has had no production for at least the chosen number of months",
    "Variação anual": "oil production in the last year compared with the year before; negative = decline",
    "Preço": "ANP minimum oil price up to 2017 and reference price from 2018; the two series are not comparable",
    "Receita estimada": "oil produced (m³) × the field's oil price in the month, in current reais",
    "ANP": "Brazilian National Agency of Petroleum, Natural Gas and Biofuels",
    "WKT": "Well-Known Text: the format in which ANP publishes field outlines",
}
