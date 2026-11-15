"""Regras do projeto (CLAUDE.md): senhas, arquivos privados fora do git, documentação e fontes.

Cada teste diz qual regra do projeto verifica.
"""

import re
import subprocess

import pytest
from dotenv import dotenv_values

from .conftest import RAIZ

pytestmark = pytest.mark.regras


def _git(*args) -> str:
    return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True, check=True).stdout


def _versionaveis() -> list[str]:
    """Arquivos rastreados + novos não ignorados: tudo o que um commit pode levar."""
    return [l for l in _git("ls-files", "--cached", "--others", "--exclude-standard").splitlines() if l]


# ---------- senhas [autor]: "Nunca escreva senhas em arquivos versionados" ----------

def test_modelo_do_env_sem_senha():
    assert dotenv_values(RAIZ / ".env.exemplo").get("PGPASSWORD") in ("", None)


def test_senha_real_nao_aparece_em_arquivo_versionavel():
    env = dotenv_values(RAIZ / ".env") if (RAIZ / ".env").exists() else {}
    senha = env.get("PGPASSWORD")
    if not senha:
        pytest.skip(".env sem senha")
    # Senha atribuída em qualquer formato (PGPASSWORD=..., password: ..., senha = ...).
    atribuicao = re.compile(rb"(?i)(pgpassword|password|senha)\s*[=:]\s*['\"]?" + re.escape(senha.encode()))
    # Se a senha for uma palavra comum (o usuário "postgres", por exemplo), ela aparece legitimamente em
    # comandos como "psql -U postgres"; nesse caso, só as atribuições contam.
    comum = senha in (env.get("PGUSER"), "postgres")
    com_senha = []
    for a in _versionaveis():
        caminho = RAIZ / a
        if not caminho.is_file():
            continue
        conteudo = caminho.read_bytes()
        if atribuicao.search(conteudo) or (not comum and senha.encode() in conteudo):
            com_senha.append(a)
    assert com_senha == []  # só os nomes dos arquivos são mostrados, nunca a senha


# ---------- arquivos privados fora do git [autor] ----------

PRIVADOS = [
    "data/raw/anp/producao-por-poco/2026-09-30/x.zip", "data/interim/anp/x.csv",  # dados brutos e derivados
    "dist/base-origem/carga.csv",                                                 # base origem gerada (vai na Release)
    "JOURNAL.md", "CLAUDE.md", ".env", ".claude/settings.json", "logs/pipeline.log",  # arquivos pessoais e locais
]


@pytest.mark.parametrize("caminho", PRIVADOS)
def test_arquivo_privado_e_ignorado_pelo_git(caminho):
    assert subprocess.run(["git", "check-ignore", "-q", caminho], cwd=RAIZ).returncode == 0, caminho


def test_nenhum_arquivo_privado_esta_versionado():
    padrao = re.compile(r"^(data/|dist/|logs/|\.claude/|JOURNAL\.md$|CLAUDE\.md$|\.env$)")
    assert [a for a in _git("ls-files").splitlines() if padrao.match(a)] == []


def test_modelo_do_env_e_versionado():
    assert subprocess.run(["git", "check-ignore", "-q", ".env.exemplo"], cwd=RAIZ).returncode == 1


# ---------- dependências ----------

def test_dependencias_com_versao_fixa():
    linhas = [l.strip() for l in (RAIZ / "requirements.txt").read_text().splitlines() if l.strip() and not l.startswith("#")]
    assert linhas and all("==" in l for l in linhas)


# ---------- documentação do ETL e dos dados ----------

def test_tratamentos_documentados():
    # [autor] cada operação do ETL 1 (C) e tratamento do ETL 2 (T) fica em docs/etl/tratamentos.md
    texto = (RAIZ / "docs" / "etl" / "tratamentos.md").read_text(encoding="utf-8")
    ids = set(re.findall(r"\| ([CT]\d\d[a-z]?) \|", texto))
    esperados = {f"C0{i}" for i in range(1, 7)} | {"C02a", "C05a"} | {f"T{i:02d}" for i in range(1, 21)}
    assert esperados <= ids


@pytest.mark.parametrize("fonte", ["producao-por-poco", "producao-por-poco-cdp", "concessionarios",
                                   "preco-minimo-petroleo", "preco-referencia-petroleo",
                                   "pocos-georreferenciados", "campos-georreferenciados"])
def test_readme_documenta_cada_fonte_com_link(fonte):
    # [autor] cada arquivo de dados tem o link de download no README
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    assert f"data/raw/anp/{fonte}/" in texto
    assert "https://www.gov.br/anp/" in texto


def test_readme_explica_a_base_origem_e_a_atualizacao():
    texto = (RAIZ / "README.md").read_text(encoding="utf-8")
    for secao in ("## O que é este projeto", "## Base origem: as 16 tabelas da stage em CSV",
                  "## Como atualizar os dados (extração manual)", "## Dados derivados"):
        assert secao in texto, secao


def test_modelo_dimensional_documentado():
    # [autor] "Deixe claro, escrito em algum documento, o porquê de usar duas fatos"
    doc = RAIZ / "docs" / "modelagem" / "modelo_dimensional.md"
    texto = doc.read_text(encoding="utf-8")
    assert "## Por que duas tabelas fato" in texto
    for trecho in ("`ft_producao`", "`ft_participacao`", "constelação de fatos", "Não é floco de neve",
                   "## 1. Pontos cardeais", "## 2. Matriz dimensão-indicador", "## 3. Grão e medidas", "## 4. Dimensões"):
        assert trecho in texto, trecho
    assert (doc.parent / "dw_diagrama_estrela.png").is_file()


ENTREGUES = [RAIZ / "docs" / "modelagem" / "modelo_dimensional.md", RAIZ / "docs" / "etl" / "tratamentos.md",
             RAIZ / "database" / "criar_bancos.sql", RAIZ / "database" / "dw" / "criar_tabelas.sql",
             *sorted((RAIZ / "database" / "st").glob("*.sql")), *sorted((RAIZ / "etl" / "python").rglob("*.py"))]


# Termos que identificam o curso, o cenário fictício da entrega e o nome antigo do repositório. Montados por partes
# para que este próprio arquivo não os contenha.
TERMOS_DO_CURSO = ["au" + "las?", "pro" + "fessor(a|es)?", "prof" + r"(?=\.)", "discip" + "lina", "pu" + "c", "ander" + "son",
                   "bi " + "master", "class" + "room", "trabalho " + "final", "acad" + "[eê]mic[oa]s?", "alu" + "no",
                   "mb" + "a", "p[oó]s-gradua" + r"\w*", "final-" + "project", "petro" + "aguiar", "st" + "ark", "jar" + "vis",
                   "levantamento dos " + "requisitos", "entreg" + "[áa]veis", "deliver" + "ables"]
# Única exceção [autor]: o crédito ao autor original do script de calendário (e o teste que o confere).
EXCECOES = {"database/dw/dim_data.sql": {"ander" + "son"}, "tests/test_dim_data.py": {"ander" + "son"}}


def test_repositorio_sem_referencia_ao_curso():
    # [autor] o repositório é focado na reprodução do pipeline com dados novos: nenhuma menção ao curso, à entrega
    # nem ao cenário fictício em arquivo versionado
    padrao = re.compile(r"(?i)\b(" + "|".join(TERMOS_DO_CURSO) + r")\b")
    achados = []
    for rel in _versionaveis():
        caminho = RAIZ / rel
        if not caminho.is_file() or caminho.suffix.lower() in {".png", ".jpg", ".jpeg", ".zip", ".pdf", ".docx"}:
            continue
        for n, linha in enumerate(caminho.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            for m in padrao.finditer(linha):
                if m[1].lower() not in EXCECOES.get(rel, set()):
                    achados.append(f"{rel}:{n}: {m[1]}")
    assert achados == []


def test_protecao_contra_referencia_ao_curso_detecta_os_termos():
    padrao = re.compile(r"(?i)\b(" + "|".join(TERMOS_DO_CURSO) + r")\b")
    assert padrao.search("como visto na " + "au" + "la 5") and padrao.search("Pro" + "f. Fulano")
    assert not padrao.search("aulacao, professorado e pucara")  # palavras que só contêm os termos


# ---------- README bilíngue [autor]: português como padrão, inglês opcional, sempre sincronizados ----------

README_PT, README_EN = RAIZ / "README.md", RAIZ / "README.en.md"
SO_EM_INGLES = {"Glossary"}  # o glossário existe só no README em inglês


def _titulos(texto: str) -> list[str]:
    return [m[1] for m in re.finditer(r"^(#{2,4}) ", texto, re.M)
            if not any(texto[m.end():].startswith(t + "\n") for t in SO_EM_INGLES)]


def _comandos(texto: str) -> list[str]:
    """Linhas dos blocos ```sh, sem os comentários (que são traduzidos)."""
    blocos = re.findall(r"```sh\n(.*?)```", texto, re.S)
    return [l.split("#")[0].strip() for b in blocos for l in b.splitlines() if l.split("#")[0].strip()]


def _links(texto: str) -> set[str]:
    return set(re.findall(r"https?://[^\s)>]+", texto))


def test_link_de_troca_de_idioma_nos_dois_readmes():
    assert "[English](README.en.md)" in README_PT.read_text(encoding="utf-8").splitlines()[2]
    assert "[Português](README.md)" in README_EN.read_text(encoding="utf-8").splitlines()[2]


def test_readmes_com_as_mesmas_secoes_comandos_e_links():
    pt, en = README_PT.read_text(encoding="utf-8"), README_EN.read_text(encoding="utf-8")
    assert _titulos(pt) == _titulos(en)    # mesma estrutura de seções, na mesma ordem
    assert _comandos(pt) == _comandos(en)  # mesmos comandos
    assert _links(pt) == _links(en)        # mesmas fontes de dados


def test_ancoras_internas_do_readme_em_ingles_existem():
    en = README_EN.read_text(encoding="utf-8")
    ancoras = {re.sub(r"[^\w\- ]", "", t.strip().lower()).replace(" ", "-")
               for t in re.findall(r"^#{1,4} (.+)$", en, re.M)}
    assert set(re.findall(r"\]\(#([^)]+)\)", en)) <= ancoras


def test_tratamentos_dizem_que_o_pdi_reproduz_so_o_etl_2():
    # [autor, 14/11/2026] escopo final: o PDI reproduz só o ETL 2; o ETL 1 é só em Python
    texto = (RAIZ / "docs" / "etl" / "tratamentos.md").read_text(encoding="utf-8")
    assert "ETL 1: brutos da ANP ──[Python]──►" in texto and "[Python | PDI]" not in texto.split("ETL 2:")[0]
