# Identidade visual

Cores e tipografia do painel web (Streamlit) e das figuras do projeto. Os mesmos
valores estão em **`tokens.json`**, em formato de dados: o painel lê as cores de
lá (`painel_web/estilo.py`). Ao mudar algo aqui, mude também lá.

## Paleta: navy monocromático

| Cor | Hex | RGB | Papel |
| --- | --- | --- | --- |
| Navy | `#0B1F3A` | 11, 31, 58 | **Primária**: títulos, barra lateral do painel |
| Azul aço | `#1F4E79` | 31, 78, 121 | **Secundária**: subtítulos, cabeçalho das tabelas |
| Azul médio | `#3A6EA5` | 58, 110, 165 | **Apoio**: destaques, links, gráficos |
| Azul gelo | `#D6E4F0` | 214, 228, 240 | Fundo de caixas de destaque (avisos) |
| Grafite | `#2D3748` | 45, 55, 72 | Texto |
| Cinza azulado | `#E2E8F0` | 226, 232, 240 | Bordas e linhas zebradas das tabelas |
| Branco | `#FFFFFF` | 255, 255, 255 | Fundo |

**Gráficos:** as séries se diferenciam pela intensidade do azul, nesta ordem:
`#0B1F3A`, `#1F4E79`, `#3A6EA5`, `#7FA7CF`, `#D6E4F0`. Para "Outros", use o cinza
`#A0AEC0`.

Como a paleta é monocromática, um gráfico deve ter **no máximo 5 séries**. As
demais vão para "Outros".

## Tipografia

| Uso | Fonte | Observação |
| --- | --- | --- |
| Títulos | **Montserrat** | Google Fonts, gratuita |
| Texto | **Source Sans 3** | Google Fonts, gratuita |

Se Montserrat e Source Sans 3 não estiverem instaladas, use Segoe UI ou Arial.
