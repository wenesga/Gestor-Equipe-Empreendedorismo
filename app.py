"""Gestor de Equipe - Empreendedorismo e Inovação (LCOMP-EI-2026-2).

Registra contribuições com evidência, diário de campo, cronograma das 10
semanas e relatório individual, para comprovar a participação individual.
Persistência: SQLite (data/equipe.db) + pasta data/uploads.
"""
import base64
import hashlib
import html
import json
import unicodedata
import os
import secrets
import sqlite3
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from relatorio_pdf import gerar_pdf

DATA_DIR = Path(__file__).parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
DB_PATH = DATA_DIR / "equipe.db"
DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

CRONOGRAMA = [
    (1, "2026-10-03", "Formar equipe, selecionar comunidade, contrato de equipe"),
    (2, "2026-10-10", "Ir à comunidade, ouvir, observar (Registro da Imersão)"),
    (3, "2026-10-17", "Diagnosticar e definir problema + Checkpoint individual 1"),
    (4, "2026-10-24", "Gerar ideias, selecionar solução, proposta de valor"),
    (5, "2026-10-31", "Testar a solução na comunidade e começar a coletar feedback"),
    (6, "2026-11-07", "Concluir testes e feedback na comunidade + Checkpoint individual 2"),
    (7, "2026-11-14", "Revisar solução, construir modelo de negócio/impacto"),
    (8, "2026-11-21", "Planejar e implantar a solução"),
    (9, "2026-11-28", "Planejar e implantar a solução"),
    (10, "2026-12-05", "Devolutiva, portfólio, pitch, reflexão + avaliação individual final"),
]
STATUS = ["Pendente", "Em andamento", "Concluída"]
TIPOS_CONTRIB = ["Pesquisa", "Visita/contato com a comunidade", "Redação/documento",
                 "Design/prototipação", "Reunião da equipe", "Apresentação/pitch",
                 "Coordenação/gestão", "Outro"]
TIPOS_CAMPO = ["Visita", "Entrevista", "Observação", "Conversa informal", "Devolutiva"]
DIAS_ALERTA = 14
COOKIE_SESSAO = "gestor_sessao"
EXT_IMAGEM = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
PASTA_IMAGENS = Path(__file__).parent / "imagens"
ARQUIVO_LOGO = PASTA_IMAGENS / "logo_icone.png"
ARQUIVO_BANNER = PASTA_IMAGENS / "banner.png"
DIAS_SESSAO = 30
MAX_MEMBROS = 6


# ---------- banco ----------
def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def init_db():
    with db() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS semanas(
            semana INTEGER PRIMARY KEY, inicio TEXT NOT NULL, prazo TEXT);
        CREATE TABLE IF NOT EXISTS membros(
            id INTEGER PRIMARY KEY, nome TEXT UNIQUE NOT NULL, pin_hash TEXT NOT NULL,
            lider INTEGER DEFAULT 0, ativo INTEGER DEFAULT 1);
        CREATE TABLE IF NOT EXISTS equipe(
            id INTEGER PRIMARY KEY CHECK (id = 1), nome TEXT, polo TEXT, comunidade TEXT,
            justificativa TEXT, contato TEXT, contrato TEXT);
        CREATE TABLE IF NOT EXISTS tarefas(
            id INTEGER PRIMARY KEY, semana INTEGER, prazo TEXT, titulo TEXT NOT NULL,
            responsavel_id INTEGER REFERENCES membros(id), status TEXT DEFAULT 'Pendente');
        CREATE TABLE IF NOT EXISTS contribuicoes(
            id INTEGER PRIMARY KEY, membro_id INTEGER NOT NULL REFERENCES membros(id),
            data TEXT NOT NULL, semana INTEGER, tipo TEXT, descricao TEXT NOT NULL,
            horas REAL DEFAULT 0, link TEXT, arquivo TEXT, criado_em TEXT);
        CREATE TABLE IF NOT EXISTS diario(
            id INTEGER PRIMARY KEY, data TEXT NOT NULL, tipo TEXT, local TEXT,
            participantes TEXT, pessoas_ouvidas TEXT, relato TEXT NOT NULL,
            aprendizados TEXT, link TEXT, arquivo TEXT, autor_id INTEGER REFERENCES membros(id));
        CREATE TABLE IF NOT EXISTS sessoes(
            token_hash TEXT PRIMARY KEY, membro_id INTEGER NOT NULL REFERENCES membros(id),
            expira_em TEXT NOT NULL);
        """)
        con.execute("INSERT OR IGNORE INTO equipe(id) VALUES (1)")
        if "codigo" not in [r[1] for r in con.execute("PRAGMA table_info(equipe)")]:
            con.execute("ALTER TABLE equipe ADD COLUMN codigo TEXT")
        if con.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO tarefas(semana, prazo, titulo) VALUES (?,?,?)", CRONOGRAMA)
        if "prazo" not in [r[1] for r in con.execute("PRAGMA table_info(semanas)")]:
            con.execute("ALTER TABLE semanas ADD COLUMN prazo TEXT")
        if con.execute("SELECT COUNT(*) FROM semanas").fetchone()[0] == 0:
            con.executemany("INSERT INTO semanas(semana, inicio) VALUES (?,?)",
                            [(sem, inicio) for sem, inicio, _ in CRONOGRAMA])


def q(sql, params=()):
    with db() as con:
        return pd.read_sql_query(sql, con, params=params)


def ex(sql, params=()):
    with db() as con:
        con.execute(sql, params)


def hash_pin(pin):
    return hashlib.sha256(("ei2026:" + pin).encode()).hexdigest()


def salvar_arquivo(up):
    if up is None:
        return None
    nome = f"{datetime.now():%Y%m%d%H%M%S}_{Path(up.name).name}"
    (UPLOAD_DIR / nome).write_bytes(up.getbuffer())
    return nome


def br(valor):
    """'2026-10-09' -> '09/10/2026'; devolve vazio se não houver data."""
    if not isinstance(valor, str) or len(valor) < 10:
        return ""
    return f"{valor[8:10]}/{valor[5:7]}/{valor[:4]}"


def _txt(valor):
    """Texto de uma célula do banco, ou vazio quando for nulo."""
    return valor if isinstance(valor, str) else ""


def mostrar_evidencia(link, arquivo, chave):
    """Link clicável e/ou botão para baixar o arquivo anexado."""
    link, arquivo = _txt(link), _txt(arquivo)
    if link:
        st.markdown(f"**Evidência:** [{link}]({link})")
    if arquivo and (UPLOAD_DIR / arquivo).exists():
        if Path(arquivo).suffix.lower() in EXT_IMAGEM:
            st.image(str(UPLOAD_DIR / arquivo), width=420)
        st.download_button(f"Baixar anexo ({arquivo.split('_', 1)[-1]})",
                           (UPLOAD_DIR / arquivo).read_bytes(), arquivo, key=f"anexo_{chave}")
    if not link and not arquivo:
        st.caption("Sem evidência anexada.")


@st.cache_resource
def banner_base64():
    """Banner em base64 para usar como fundo em HTML; vazio se o arquivo não existir."""
    if not ARQUIVO_BANNER.exists():
        return ""
    return base64.b64encode(ARQUIVO_BANNER.read_bytes()).decode()


def mostrar_banner():
    """Banner do topo do Painel, com o título por cima do espaço vazio do lado esquerdo."""
    dados = banner_base64()
    if not dados:
        return
    st.markdown(
        f"""
        <div class="banner-arte" style="background-image: url(data:image/png;base64,{dados})">
            <p class="banner-titulo">Gestor de Equipe</p>
            <p class="banner-subtitulo">Empreendedorismo e Inovação</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def datas_semanas():
    """Data de início de cada semana (editável no Cronograma); cai no cronograma original se faltar."""
    padrao = {sem: inicio for sem, inicio, _ in CRONOGRAMA}
    try:
        salvas = q("SELECT semana, inicio FROM semanas")
        padrao.update({int(r["semana"]): r["inicio"] for _, r in salvas.iterrows()})
    except Exception:
        pass
    return padrao


def prazos_semanas():
    """Prazo de entrega de cada semana (vazio quando ainda não foi definido)."""
    try:
        salvos = q("SELECT semana, prazo FROM semanas")
    except Exception:
        return {}
    return {int(r["semana"]): r["prazo"] for _, r in salvos.iterrows() if isinstance(r["prazo"], str)}


def prazos_efetivos():
    """Prazo de cada semana: o definido à mão ou, se não houver, o início da semana seguinte."""
    datas = datas_semanas()
    definidos = prazos_semanas()
    efetivos = {}
    for sem in sorted(datas):
        if sem in definidos:
            efetivos[sem] = definidos[sem]
        elif sem + 1 in datas:
            efetivos[sem] = datas[sem + 1]
        else:
            efetivos[sem] = (date.fromisoformat(datas[sem]) + timedelta(days=7)).isoformat()
    return efetivos


def nome_curto(nome):
    """'Kleyton Pereira Bueno Ramalho' -> 'Kleyton' (só o primeiro nome, onde falta espaço)."""
    partes = str(nome).split()
    return partes[0] if partes else str(nome)


def semana_atual():
    hoje = date.today().isoformat()
    atual = 1
    for sem, inicio in sorted(datas_semanas().items()):
        if hoje >= inicio:
            atual = sem
    return atual


# ---------- autenticação ----------
def _pin_valido(p):
    return p.isdigit() and len(p) == 4


def _script_cookie(valor, dias):
    """Grava (ou apaga, com dias=0) o cookie de sessão no navegador, a partir da página pai."""
    st.iframe(
        f"""
        <script>
        (function() {{
            const doc = window.parent.document;
            const seguro = window.parent.location.protocol === 'https:' ? '; Secure' : '';
            doc.cookie = '{COOKIE_SESSAO}={valor}; path=/; max-age={dias * 86400}; SameSite=Lax' + seguro;
        }})();
        </script>
        """,
        height=1,
        width=1,
    )


def iniciar_sessao(membro_id):
    """Abre a sessão e guarda um token no banco; o cookie é gravado na próxima renderização."""
    token = secrets.token_urlsafe(32)
    expira = (datetime.now() + timedelta(days=DIAS_SESSAO)).isoformat()
    ex("INSERT INTO sessoes(token_hash, membro_id, expira_em) VALUES (?,?,?)",
       (hash_pin(token), int(membro_id), expira))
    st.session_state["uid"] = int(membro_id)
    st.session_state["cookie_novo"] = token


def retomar_sessao():
    """Reabre o login a partir do cookie, se o token ainda for válido e o integrante estiver ativo."""
    token = st.context.cookies.get(COOKIE_SESSAO)
    if not isinstance(token, str) or not token:
        return
    r = q("""SELECT s.membro_id FROM sessoes s JOIN membros m ON m.id = s.membro_id
             WHERE s.token_hash = ? AND s.expira_em > ? AND m.ativo = 1""",
          (hash_pin(token), datetime.now().isoformat()))
    if not r.empty:
        st.session_state["uid"] = int(r["membro_id"].iloc[0])


def encerrar_sessao():
    token = st.context.cookies.get(COOKIE_SESSAO)
    if isinstance(token, str) and token:
        ex("DELETE FROM sessoes WHERE token_hash = ?", (hash_pin(token),))
    for chave in ("uid", "pagina"):
        st.session_state.pop(chave, None)
    st.query_params.clear()
    st.session_state["limpar_cookie"] = True


def _entrar_como(nome):
    iniciar_sessao(q("SELECT id FROM membros WHERE nome = ?", (nome,))["id"].iloc[0])
    st.rerun()


def _salvar_membro(nome, pin, lider):
    """Cria o integrante ou, se o nome estava desativado, reativa com o novo PIN."""
    ex("""INSERT INTO membros(nome, pin_hash, lider) VALUES (?,?,?)
          ON CONFLICT(nome) DO UPDATE SET pin_hash=excluded.pin_hash, ativo=1, lider=excluded.lider""",
       (nome, hash_pin(pin), int(lider)))


ICO_EDITAR = ":material/edit:"
ICO_EXCLUIR = ":material/delete:"


def sucesso(msg):
    """Guarda o aviso para aparecer como notificação depois da atualização da tela (que fecha o diálogo)."""
    st.session_state["_aviso"] = msg
    st.rerun()


def mostrar_aviso():
    msg = st.session_state.pop("_aviso", None)
    if msg:
        st.toast(msg, icon=":material/check_circle:")


def cabecalho(titulo, acao=None, icone=None, chave=None):
    """Título da página à esquerda e, se houver, a ação principal à direita (sempre no mesmo lugar)."""
    esq, dir_ = st.columns([4, 1.4], vertical_alignment="center")
    esq.header(titulo)
    if acao:
        return dir_.button(acao, key=chave, type="primary", icon=icone, width="stretch")
    return False


def botoes_dialogo(rotulo="Salvar"):
    """Rodapé padrão dos diálogos: Cancelar e a ação principal, à direita."""
    _, c1, c2 = st.columns([2, 1, 1])
    cancelar = c1.button("Cancelar", key="dlg_cancelar", width="stretch")
    ok = c2.button(rotulo, key="dlg_ok", type="primary", width="stretch")
    if cancelar:
        st.rerun()
    return ok


@st.dialog("Confirmar")
def confirmar_acao(texto, rotulo, sql, params, aviso, perigoso=True):
    """Confirmação antes de uma ação sem volta (excluir, remover) ou de grande efeito."""
    st.write(texto)
    _, c1, c2 = st.columns([2, 1, 1])
    if c1.button("Cancelar", key="dlg_cancelar", width="stretch"):
        st.rerun()
    if c2.button(rotulo, key="dlg_perigo" if perigoso else "dlg_ok", type="primary", width="stretch"):
        ex(sql, params)
        sucesso(aviso)


def selo(texto, cor):
    return (f'<span style="padding: 2px 8px; border-radius: 10px; font-size: 0.8rem; white-space: nowrap; '
            f'background-color: {cor};">{html.escape(texto)}</span>')


def tabela(df, html_cols=(), largas=(), numericas=(), destaque=None):
    """Tabela de leitura simples (cabeçalho, linhas, colunas numéricas à direita), sem cara de planilha."""
    celula = "padding: 8px 10px; border-bottom: 1px solid rgba(128,128,128,0.25); vertical-align: top;"
    cab = "".join(
        f'<th style="text-align: {"right" if c in numericas else "left"}; padding: 8px 10px; '
        f'border-bottom: 1px solid rgba(128,128,128,0.4); opacity: 0.7; font-weight: 500;">'
        f"{html.escape(str(c))}</th>" for c in df.columns)
    linhas = []
    for _, r in df.iterrows():
        fundo = "background-color: rgba(46, 125, 50, 0.35); font-weight: 600;" if destaque and destaque(r) else ""
        cels = "".join(
            f'<td style="{celula}{"" if c in largas else " white-space: nowrap;"}'
            f'{" text-align: right;" if c in numericas else ""}">'
            f"{r[c] if c in html_cols else html.escape(str(r[c]))}</td>" for c in df.columns)
        linhas.append(f'<tr style="{fundo}">{cels}</tr>')
    st.markdown(
        f'<table style="width: 100%; border-collapse: collapse; font-size: 0.92rem;">'
        f"<thead><tr>{cab}</tr></thead><tbody>{''.join(linhas)}</tbody></table>",
        unsafe_allow_html=True)


def injetar_teclado_numerico():
    """Campos de PIN abrem o teclado numérico no celular (o Streamlit não expõe o atributo inputmode)."""
    st.iframe(
        """
        <script>
        (function() {
            const win = window.parent;
            if (win.__tecladoNumericoAtivo) return;
            win.__tecladoNumericoAtivo = true;
            function ajustar() {
                win.document.querySelectorAll('input[type="password"]').forEach(function (el) {
                    el.setAttribute('inputmode', 'numeric');
                    el.setAttribute('pattern', '[0-9]*');
                });
            }
            new MutationObserver(ajustar).observe(win.document.body, { childList: true, subtree: true });
            ajustar();
        })();
        </script>
        """,
        height=1,
        width=1,
    )


def tela_inicial():
    with st.container(key="sidebar_cabecalho"):
        if ARQUIVO_LOGO.exists():
            st.image(str(ARQUIVO_LOGO), width=96)
        st.title("Gestor de Equipe")
        st.caption("Empreendedorismo e Inovação · LCOMP-EI-2026-2")
    membros = q("SELECT * FROM membros WHERE ativo = 1 ORDER BY nome")
    if membros.empty:
        st.subheader("Primeiro acesso: criar a equipe")
        st.write("Quem criar a equipe vira o líder. Depois, cada integrante entra sozinho "
                 "com o código da equipe.")
        with st.form("primeiro"):
            nome = " ".join(st.text_input("Seu nome completo").split())
            pin1 = st.text_input("Crie um PIN de 4 dígitos", type="password", max_chars=4)
            pin2 = st.text_input("Repita o PIN", type="password", max_chars=4)
            codigo = st.text_input("Código da equipe (os colegas vão digitar para entrar)").strip()
            if st.form_submit_button("Criar equipe", type="primary"):
                if not nome or not codigo:
                    st.error("Informe seu nome e o código da equipe.")
                elif not _pin_valido(pin1) or pin1 != pin2:
                    st.error("Use um PIN de 4 dígitos e repita igual.")
                else:
                    ex("UPDATE equipe SET codigo = ? WHERE id = 1", (codigo,))
                    _salvar_membro(nome, pin1, True)
                    _entrar_como(nome)
        return
    cadastro = st.session_state.get("tela_cadastro", False)
    if not cadastro:
        with st.form("login"):
            nome = st.selectbox("Quem é você?", membros["nome"])
            pin = st.text_input("PIN", type="password", max_chars=4)
            if st.form_submit_button("Entrar", type="primary"):
                m = membros[membros["nome"] == nome].iloc[0]
                if hash_pin(pin) == m["pin_hash"]:
                    iniciar_sessao(m["id"])
                    st.rerun()
                else:
                    st.error("PIN incorreto.")
        if st.button("Sou novo no grupo", type="tertiary"):
            st.session_state["tela_cadastro"] = True
            st.rerun()
        return
    if len(membros) >= MAX_MEMBROS:
        st.info(f"A equipe já tem {MAX_MEMBROS} integrantes. Peça ao líder para liberar uma vaga.")
    else:
        with st.form("cadastro"):
            nome = " ".join(st.text_input("Seu nome completo").split())
            codigo = st.text_input("Código da equipe").strip()
            pin1 = st.text_input("Crie um PIN de 4 dígitos", type="password", max_chars=4)
            pin2 = st.text_input("Repita o PIN", type="password", max_chars=4)
            if st.form_submit_button("Entrar no grupo", type="primary"):
                esperado = (q("SELECT codigo FROM equipe WHERE id = 1")["codigo"].iloc[0] or "").lower()
                if not nome:
                    st.error("Informe seu nome.")
                elif codigo.lower() != esperado:
                    st.error("Código da equipe incorreto. Peça ao líder.")
                elif not _pin_valido(pin1) or pin1 != pin2:
                    st.error("Use um PIN de 4 dígitos e repita igual.")
                elif nome.lower() in {n.lower() for n in membros["nome"]}:
                    st.error("Já existe alguém com esse nome. Volte e use Entrar.")
                else:
                    _salvar_membro(nome, pin1, False)
                    _entrar_como(nome)
    if st.button("Já tenho cadastro", type="tertiary"):
        st.session_state["tela_cadastro"] = False
        st.rerun()


def registros_do_membro(mid):
    """Conta tudo que referencia o integrante (contribuições, diário e tarefas)."""
    with db() as con:
        return con.execute(
            """SELECT (SELECT COUNT(*) FROM contribuicoes WHERE membro_id = :m)
                    + (SELECT COUNT(*) FROM diario WHERE autor_id = :m)
                    + (SELECT COUNT(*) FROM tarefas WHERE responsavel_id = :m)""",
            {"m": mid}).fetchone()[0]


def slug(nome):
    """'Minhas contribuições' -> 'minhas-contribuicoes', para usar no endereço da página."""
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return "-".join(base.split())


def usuario():
    m = q("SELECT * FROM membros WHERE id = ?", (st.session_state["uid"],))
    return m.iloc[0]


def liberar_scroll_grafico():
    """
    Permite rolar a página com o mouse sobre um gráfico Altair/Vega-Lite.

    O wrapper .stVegaLiteChart intercepta o scroll mesmo sem zoom/pan. O listener de captura roda
    antes do interno e repassa a rolagem para a área principal (.stMain).
    """
    st.iframe(
        """
        <script>
        (function() {
            const win = window.parent;
            if (win.__liberaScrollGraficoAtivo) return;
            win.__liberaScrollGraficoAtivo = true;
            win.document.addEventListener('wheel', function (e) {
                if (!(e.target.closest && e.target.closest('.stVegaLiteChart'))) return;
                const area = win.document.querySelector('.stMain');
                if (!area) return;
                area.scrollTop += e.deltaY;
                e.preventDefault();
            }, { capture: true, passive: false });
        })();
        </script>
        """,
        height=1,
        width=1,
    )


def grafico_horas(c):
    """Barras horizontais finas de horas por integrante, com valor ao lado e sem interação."""
    df = c.rename(columns={"nome": "Integrante", "horas": "Horas"})
    base = alt.Chart(df).encode(
        y=alt.Y("Integrante:N", sort="-x", title=None,
                axis=alt.Axis(domain=False, ticks=False, labelPadding=8, labelFontSize=13)),
        x=alt.X("Horas:Q", title=None, axis=None, scale=alt.Scale(domainMin=0)),
    )
    barras = base.mark_bar(size=14, cornerRadiusEnd=7, color="#3376cb")
    rotulos = base.mark_text(align="left", dx=6, fontSize=12, color="#8a94a6").encode(
        text=alt.Text("Horas:Q", format=".1f"))
    grafico = (barras + rotulos).properties(height=max(90, 34 * len(df))).configure_view(
        stroke=None).configure(background="transparent")
    st.altair_chart(grafico, width="stretch")
    liberar_scroll_grafico()

# ---------- páginas ----------
def pg_painel(u):
    mostrar_banner()
    st.header("Painel")
    atual = semana_atual()
    total = len(CRONOGRAMA)
    falta = total - atual
    resto = ("última semana" if falta == 0 else
             f"falta {falta} semana" if falta == 1 else f"faltam {falta} semanas")
    st.progress(atual / total, text=f"Semana {atual} de {total} · {resto}")
    c = q("""SELECT m.nome, COUNT(c.id) AS registros, COALESCE(SUM(c.horas),0) AS horas,
                    MAX(c.data) AS ultimo
             FROM membros m LEFT JOIN contribuicoes c ON c.membro_id = m.id
             WHERE m.ativo = 1 GROUP BY m.id ORDER BY m.nome""")
    st.subheader("Contribuições por integrante")
    limite = (date.today() - pd.Timedelta(days=DIAS_ALERTA)).isoformat()
    parado = c["ultimo"].isna() | (c["ultimo"] < limite)
    tabela(pd.DataFrame({
        "Integrante": c["nome"],
        "Registros": c["registros"],
        "Horas": c["horas"].map(lambda h: f"{h:g}"),
        "Último registro": c["ultimo"].map(br),
        "Situação": [selo(f"Sem registro há mais de {DIAS_ALERTA} dias", "rgba(198, 40, 40, 0.25)") if p
                     else selo("Em dia", "rgba(46, 125, 50, 0.25)") for p in parado],
    }), html_cols=("Situação",), numericas=("Registros", "Horas"))
    if not c.empty:
        grafico_horas(c)
    t = q("SELECT status, COUNT(*) AS n FROM tarefas GROUP BY status")
    st.subheader("Tarefas")
    cols = st.columns(3)
    for col, s in zip(cols, STATUS):
        n = int(t.loc[t["status"] == s, "n"].sum())
        col.metric(s, n)
    pend = q("""SELECT t.semana AS Semana, s.inicio AS Início, t.titulo AS Tarefa,
                       COALESCE(m.nome, '-') AS Responsável, t.status AS Status
                FROM tarefas t JOIN semanas s ON s.semana = t.semana
                LEFT JOIN membros m ON m.id = t.responsavel_id
                WHERE t.status != 'Concluída' ORDER BY s.inicio, t.id""")
    st.subheader("Pendências")
    if pend.empty:
        st.caption("Nenhuma pendência.")
    else:
        efetivos = prazos_efetivos()
        pend.insert(2, "Prazo", pend["Semana"].map(lambda sem: br(efetivos.get(int(sem), ""))[:5]))
        pend["Início"] = pend["Início"].map(lambda d: br(d)[:5])
        pend["Responsável"] = pend["Responsável"].map(nome_curto)
        pend = pend.rename(columns={"Semana": "Sem."})
        tabela(pend, largas=("Tarefa",), destaque=lambda r: r["Sem."] == atual)
        st.caption("Em verde: a semana em vigor.")


def pg_equipe(u):
    st.header("Equipe")
    e = q("SELECT * FROM equipe WHERE id = 1").iloc[0]
    with st.form("equipe"):
        nome = st.text_input("Nome da equipe", e["nome"] or "")
        if st.form_submit_button("Salvar", type="primary"):
            ex("UPDATE equipe SET nome=? WHERE id=1", (nome.strip(),))
            sucesso("Nome da equipe salvo.")
    st.subheader("Integrantes")
    m = q("SELECT id, nome, lider FROM membros WHERE ativo = 1 ORDER BY nome")
    colunas = [6, 2.5, 0.8]
    h1, h2, _ = st.columns(colunas)
    h1.caption("Integrante")
    h2.caption("Papel")
    for _, r in m.iterrows():
        c1, c2, c3 = st.columns(colunas, vertical_alignment="center")
        c1.write(r["nome"])
        c2.write("Líder" if r["lider"] else "Integrante")
        if not u["lider"] or r["id"] == u["id"]:
            continue
        mid, nome_alvo = int(r["id"]), r["nome"]
        with c3.popover(":material/more_horiz:", help="Ações", width="stretch"):
            if st.button("Redefinir PIN", key=f"pin_{mid}", type="tertiary", width="stretch"):
                dlg_redefinir_pin(mid, nome_alvo)
            if st.button("Passar a liderança", key=f"lid_{mid}", type="tertiary", width="stretch"):
                confirmar_acao(f"Passar a liderança da equipe para **{nome_alvo}**? "
                               "Você deixa de ser líder.", "Passar liderança",
                               "UPDATE membros SET lider = (id = ?) WHERE ativo = 1", (mid,),
                               f"{nome_alvo} agora é o líder.", perigoso=False)
            if st.button("Remover da equipe", key=f"rem_{mid}", type="tertiary", width="stretch"):
                confirmar_acao(f"Remover **{nome_alvo}** da equipe? O acesso é desativado, "
                               "mas os registros que a pessoa já fez continuam.", "Remover",
                               "UPDATE membros SET ativo = 0 WHERE id = ?", (mid,),
                               f"{nome_alvo} foi removido da equipe.")
            if registros_do_membro(mid) == 0 and st.button(
                    "Excluir definitivamente", key=f"del_{mid}", type="tertiary", width="stretch"):
                confirmar_acao(f"Excluir **{nome_alvo}** definitivamente? Esta ação não pode ser desfeita.",
                               "Excluir", "DELETE FROM membros WHERE id = ?", (mid,),
                               f"{nome_alvo} foi excluído.")
    if u["lider"]:
        st.subheader("Código da equipe")
        atual = q("SELECT codigo FROM equipe WHERE id = 1")["codigo"].iloc[0] or ""
        with st.form("codigo"):
            novo_codigo = st.text_input("Código que os colegas digitam para entrar", atual).strip()
            if st.form_submit_button("Salvar código", type="primary") and novo_codigo:
                ex("UPDATE equipe SET codigo = ? WHERE id = 1", (novo_codigo,))
                sucesso("Código atualizado.")


@st.dialog("Redefinir PIN")
def dlg_redefinir_pin(mid, nome):
    st.write(f"Novo PIN para **{nome}**.")
    pin = st.text_input("Novo PIN (4 dígitos)", type="password", max_chars=4)
    erro = st.container()
    if botoes_dialogo("Redefinir"):
        if not _pin_valido(pin):
            erro.error("Informe um PIN de 4 dígitos.")
        else:
            ex("UPDATE membros SET pin_hash = ? WHERE id = ?", (hash_pin(pin), int(mid)))
            sucesso(f"PIN de {nome} redefinido.")


@st.dialog("Editar tarefa")
def dlg_tarefa(tid, titulo):
    novo = st.text_input("Texto da tarefa", titulo)
    erro = st.container()
    if botoes_dialogo():
        if not novo.strip():
            erro.error("Escreva o texto da tarefa.")
        else:
            ex("UPDATE tarefas SET titulo = ? WHERE id = ?", (novo.strip(), int(tid)))
            sucesso("Tarefa salva.")


@st.dialog("Nova tarefa")
def dlg_nova_tarefa(sem, prazo_semana, nomes):
    novo = st.text_input("Texto da tarefa")
    resp = st.selectbox("Responsável", [None] + list(nomes),
                        format_func=lambda i: nome_curto(nomes.get(i, "—")))
    erro = st.container()
    if botoes_dialogo("Adicionar"):
        if not novo.strip():
            erro.error("Escreva o texto da tarefa.")
        else:
            ex("INSERT INTO tarefas(semana, prazo, titulo, responsavel_id) VALUES (?,?,?,?)",
               (int(sem), prazo_semana, novo.strip(), int(resp) if resp else None))
            sucesso("Tarefa adicionada.")


@st.dialog("Alterar datas")
def dlg_datas(sem):
    datas, prazos, efetivos = datas_semanas(), prazos_semanas(), prazos_efetivos()
    st.caption(f"Semana {sem}")
    nova = st.date_input("Começa em", date.fromisoformat(datas[sem]), format="DD/MM/YYYY")
    novo_prazo = st.date_input("Prazo de entrega", date.fromisoformat(efetivos[sem]), format="DD/MM/YYYY")
    mover = st.checkbox("Mover as semanas seguintes junto", value=True)
    if botoes_dialogo():
        dias = (nova - date.fromisoformat(datas[sem])).days
        alvo = [n for n in datas if n >= sem] if mover else [sem]
        with db() as con:
            for n in alvo:
                novo_inicio = (date.fromisoformat(datas[n]) + timedelta(days=dias)).isoformat()
                novo_pz = (date.fromisoformat(prazos[n]) + timedelta(days=dias)).isoformat() if n in prazos else None
                con.execute("UPDATE semanas SET inicio = ?, prazo = ? WHERE semana = ?",
                            (novo_inicio, novo_pz, n))
            if novo_prazo.isoformat() != efetivos[sem]:
                con.execute("UPDATE semanas SET prazo = ? WHERE semana = ?", (novo_prazo.isoformat(), sem))
            con.execute("UPDATE tarefas SET prazo = (SELECT inicio FROM semanas "
                        "WHERE semanas.semana = tarefas.semana)")
        sucesso("Datas salvas.")


def pg_cronograma(u):
    st.header("Cronograma e tarefas")
    membros = q("SELECT id, nome FROM membros WHERE ativo = 1 ORDER BY nome")
    nomes = dict(zip(membros["id"], membros["nome"]))
    t = q("SELECT * FROM tarefas ORDER BY semana, prazo, id")
    datas = datas_semanas()
    efetivos = prazos_efetivos()
    colunas = [6, 2.2, 2.2, 0.8, 0.8]
    for sem, _, _ in CRONOGRAMA:
        prazo_semana = datas[sem]
        with st.expander(f"Semana {sem} · {br(prazo_semana)}", expanded=(sem == semana_atual())):
            col_data, _, _, col_acao, _ = st.columns(colunas, vertical_alignment="center")
            col_data.caption(f"Começa em {br(prazo_semana)} · Prazo {br(efetivos[sem])}")
            if col_acao.button(":material/edit_calendar:", key=f"datas_{sem}", type="tertiary",
                               help="Alterar datas da semana", width="stretch"):
                dlg_datas(sem)
            tarefas = t[t["semana"] == sem]
            if tarefas.empty:
                st.caption("Nenhuma tarefa nesta semana.")
            else:
                h1, h2, h3, _, _ = st.columns(colunas)
                h1.caption("Tarefa")
                h2.caption("Responsável")
                h3.caption("Status")
            for _, r in tarefas.iterrows():
                c1, c2, c3, c4, c5 = st.columns(colunas, vertical_alignment="center")
                c1.write(r["titulo"])
                ids = [None] + list(nomes)
                atual = r["responsavel_id"]
                idx = ids.index(int(atual)) if pd.notna(atual) else 0
                resp = c2.selectbox("Responsável", ids, index=idx, key=f"r{r['id']}",
                                    format_func=lambda i: nome_curto(nomes.get(i, "—")),
                                    label_visibility="collapsed")
                stt = c3.selectbox("Status", STATUS, index=STATUS.index(r["status"]),
                                   key=f"s{r['id']}", label_visibility="collapsed")
                if c4.button(ICO_EDITAR, key=f"edita_{r['id']}", type="tertiary", help="Editar",
                             width="stretch"):
                    dlg_tarefa(int(r["id"]), r["titulo"])
                if c5.button(ICO_EXCLUIR, key=f"exclui_{r['id']}", type="tertiary", help="Excluir",
                             width="stretch"):
                    confirmar_acao(f"Excluir a tarefa **{r['titulo']}**? Esta ação não pode ser desfeita.",
                                   "Excluir", "DELETE FROM tarefas WHERE id = ?", (int(r["id"]),),
                                   "Tarefa excluída.")
                if resp != (int(atual) if pd.notna(atual) else None) or stt != r["status"]:
                    ex("UPDATE tarefas SET responsavel_id=?, status=? WHERE id=?",
                       (resp, stt, int(r["id"])))
                    st.rerun()
            if st.button("Adicionar tarefa", key=f"nova_{sem}", icon=":material/add:"):
                dlg_nova_tarefa(sem, prazo_semana, nomes)


@st.dialog("Novo registro", width="large")
def dlg_nova_contribuicao(u):
    c1, c2, c3 = st.columns(3)
    d = c1.date_input("Data", date.today(), format="DD/MM/YYYY")
    sem = c2.number_input("Semana", 1, 10, semana_atual())
    horas = c3.number_input("Horas", 0.0, 24.0, 1.0, 0.5)
    tipo = st.selectbox("Tipo de atividade", TIPOS_CONTRIB)
    desc = st.text_area("O que você fez?")
    link = st.text_input("Link da evidência (Drive, documento, foto...)")
    up = st.file_uploader("Ou anexe um arquivo")
    erro = st.container()
    if botoes_dialogo("Registrar"):
        if not desc.strip():
            erro.error("Descreva a contribuição.")
        else:
            ex("""INSERT INTO contribuicoes(membro_id, data, semana, tipo, descricao, horas,
                  link, arquivo, criado_em) VALUES (?,?,?,?,?,?,?,?,?)""",
               (int(u["id"]), d.isoformat(), int(sem), tipo, desc.strip(), horas,
                link.strip() or None, salvar_arquivo(up), datetime.now().isoformat()))
            sucesso("Contribuição registrada.")


@st.dialog("Editar registro", width="large")
def dlg_edita_contribuicao(r, uid):
    c1, c2, c3 = st.columns(3)
    nd = c1.date_input("Data", date.fromisoformat(r["data"]), format="DD/MM/YYYY")
    ns = c2.number_input("Semana", 1, 10, int(r["semana"]))
    nh = c3.number_input("Horas", 0.0, 24.0, float(r["horas"]), 0.5)
    nt = st.selectbox("Tipo de atividade", TIPOS_CONTRIB,
                      index=TIPOS_CONTRIB.index(r["tipo"]) if r["tipo"] in TIPOS_CONTRIB else 0)
    ndesc = st.text_area("O que você fez?", r["descricao"])
    nlink = st.text_input("Link da evidência", _txt(r["link"]))
    erro = st.container()
    if botoes_dialogo():
        if not ndesc.strip():
            erro.error("Descreva a contribuição.")
        else:
            ex("""UPDATE contribuicoes SET data=?, semana=?, tipo=?, descricao=?, horas=?, link=?
                  WHERE id=? AND membro_id=?""",
               (nd.isoformat(), int(ns), nt, ndesc.strip(), nh, nlink.strip() or None,
                int(r["id"]), int(uid)))
            sucesso("Registro salvo.")


def pg_contribuicoes(u):
    if cabecalho("Minhas contribuições", "Novo registro", ":material/add:", "novo_contrib"):
        dlg_nova_contribuicao(u)
    st.caption("Registre o que você fez, com evidência. É isso que comprova sua participação.")
    visao = st.segmented_control("Exibir", ["Minhas", "Da equipe"], default="Minhas",
                                 key="visao_contrib", label_visibility="collapsed")
    ver_todos = visao == "Da equipe"
    sql = """SELECT c.id, m.nome, c.data, c.semana, c.tipo, c.descricao, c.horas, c.link, c.arquivo
             FROM contribuicoes c JOIN membros m ON m.id = c.membro_id"""
    df = q(sql + ("" if ver_todos else " WHERE c.membro_id = ?") + " ORDER BY c.data DESC, c.id DESC",
           () if ver_todos else (int(u["id"]),))
    if df.empty:
        st.info("Nenhuma contribuição registrada ainda.")
    for _, r in df.iterrows():
        with st.container(border=True):
            topo, b1, b2 = st.columns([10, 1, 1], vertical_alignment="center")
            quem = f" · {r['nome']}" if ver_todos else ""
            topo.markdown(f"**{br(r['data'])}** · Semana {r['semana']} · {r['tipo']} · "
                          f"{r['horas']:g} h{quem}")
            if r["nome"] == u["nome"]:
                if b1.button(ICO_EDITAR, key=f"ec_{r['id']}", type="tertiary", help="Editar",
                             width="stretch"):
                    dlg_edita_contribuicao(r.to_dict(), int(u["id"]))
                if b2.button(ICO_EXCLUIR, key=f"xc_{r['id']}", type="tertiary", help="Excluir",
                             width="stretch"):
                    confirmar_acao("Excluir este registro? Esta ação não pode ser desfeita.", "Excluir",
                                   "DELETE FROM contribuicoes WHERE id = ? AND membro_id = ?",
                                   (int(r["id"]), int(u["id"])), "Registro excluído.")
            st.write(r["descricao"])
            mostrar_evidencia(r["link"], r["arquivo"], f"c{r['id']}")


@st.dialog("Novo registro", width="large")
def dlg_novo_diario(u, nomes):
    c1, c2, c3 = st.columns(3)
    d = c1.date_input("Data", date.today(), format="DD/MM/YYYY")
    tipo = c2.selectbox("Tipo", TIPOS_CAMPO)
    local = c3.text_input("Local / canal")
    part = st.multiselect("Integrantes presentes", nomes)
    ouvidas = st.text_input("Pessoas ouvidas (nome ou perfil)")
    relato = st.text_area("O que aconteceu / o que foi dito", height=150)
    aprend = st.text_area("Aprendizados, dores e necessidades percebidas")
    link = st.text_input("Link de evidência (foto, áudio, documento)")
    up = st.file_uploader("Ou anexe um arquivo", key="up_d")
    erro = st.container()
    if botoes_dialogo("Registrar"):
        if not relato.strip():
            erro.error("Descreva o que aconteceu.")
        else:
            ex("""INSERT INTO diario(data, tipo, local, participantes, pessoas_ouvidas, relato,
                  aprendizados, link, arquivo, autor_id) VALUES (?,?,?,?,?,?,?,?,?,?)""",
               (d.isoformat(), tipo, local, ", ".join(part), ouvidas, relato.strip(), aprend,
                link.strip() or None, salvar_arquivo(up), int(u["id"])))
            sucesso("Registro adicionado ao diário.")


@st.dialog("Editar registro", width="large")
def dlg_edita_diario(r, nomes):
    c1, c2, c3 = st.columns(3)
    nd = c1.date_input("Data", date.fromisoformat(r["data"]), format="DD/MM/YYYY")
    nt = c2.selectbox("Tipo", TIPOS_CAMPO, index=TIPOS_CAMPO.index(r["tipo"]) if r["tipo"] in TIPOS_CAMPO else 0)
    nl = c3.text_input("Local / canal", _txt(r["local"]))
    atuais = [p.strip() for p in _txt(r["participantes"]).split(",") if p.strip()]
    npart = st.multiselect("Integrantes presentes", list(dict.fromkeys(list(nomes) + atuais)), default=atuais)
    nouv = st.text_input("Pessoas ouvidas", _txt(r["pessoas_ouvidas"]))
    nrel = st.text_area("O que aconteceu / o que foi dito", _txt(r["relato"]), height=150)
    napr = st.text_area("Aprendizados, dores e necessidades percebidas", _txt(r["aprendizados"]))
    nlink = st.text_input("Link de evidência", _txt(r["link"]))
    erro = st.container()
    if botoes_dialogo():
        if not nrel.strip():
            erro.error("Descreva o que aconteceu.")
        else:
            ex("""UPDATE diario SET data=?, tipo=?, local=?, participantes=?, pessoas_ouvidas=?,
                  relato=?, aprendizados=?, link=? WHERE id=?""",
               (nd.isoformat(), nt, nl, ", ".join(npart), nouv, nrel.strip(), napr,
                nlink.strip() or None, int(r["id"])))
            sucesso("Registro salvo.")


def pg_diario(u):
    nomes = list(q("SELECT nome FROM membros WHERE ativo = 1 ORDER BY nome")["nome"])
    if cabecalho("Diário de campo da comunidade", "Novo registro", ":material/add:", "novo_diario"):
        dlg_novo_diario(u, nomes)
    df = q("""SELECT d.id, d.data, d.tipo, d.local, d.participantes, d.pessoas_ouvidas, d.relato,
                     d.aprendizados, d.link, d.arquivo, m.nome AS autor
              FROM diario d LEFT JOIN membros m ON m.id = d.autor_id ORDER BY d.data DESC, d.id DESC""")
    if df.empty:
        st.info("Nenhum registro no diário ainda.")
    for _, r in df.iterrows():
        with st.container(border=True):
            topo, b1, b2 = st.columns([10, 1, 1], vertical_alignment="center")
            local = f" · {r['local']}" if _txt(r["local"]) else ""
            topo.markdown(f"**{br(r['data'])}** · {r['tipo']}{local}")
            if b1.button(ICO_EDITAR, key=f"ed_{r['id']}", type="tertiary", help="Editar", width="stretch"):
                dlg_edita_diario(r.to_dict(), nomes)
            if b2.button(ICO_EXCLUIR, key=f"xd_{r['id']}", type="tertiary", help="Excluir", width="stretch"):
                confirmar_acao("Excluir este registro? Esta ação não pode ser desfeita.", "Excluir",
                               "DELETE FROM diario WHERE id = ?", (int(r["id"]),), "Registro excluído.")
            if _txt(r["participantes"]):
                st.markdown(f"**Presentes:** {r['participantes']}")
            if _txt(r["pessoas_ouvidas"]):
                st.markdown(f"**Pessoas ouvidas:** {r['pessoas_ouvidas']}")
            st.write(r["relato"])
            if _txt(r["aprendizados"]):
                st.markdown(f"**Aprendizados:** {r['aprendizados']}")
            mostrar_evidencia(r["link"], r["arquivo"], f"d{r['id']}")
            if _txt(r["autor"]):
                st.caption(f"Registrado por {r['autor']}")


def _janela_semana(semana):
    """Primeiro dia da semana e o primeiro dia da seguinte (para filtrar registros por data)."""
    datas = datas_semanas()
    inicio = date.fromisoformat(datas[semana])
    fim = date.fromisoformat(datas[semana + 1]) if semana + 1 in datas else inicio + timedelta(days=7)
    return inicio.isoformat(), fim.isoformat()


def _linha_evidencia(link, arquivo):
    link, arquivo = _txt(link), _txt(arquivo)
    if link:
        return f"Evidência: {link}"
    if arquivo:
        return f"Evidência: arquivo anexado ({arquivo.split('_', 1)[-1]})"
    return ""


def _texto_entrega(semana, equipe, integrantes, lider, diario_ids):
    """Monta o assunto, a mensagem e a lista de campos que ainda faltam para a entrega da semana."""
    faltam = []

    def campo(valor, nome):
        valor = _txt(valor).strip()
        if not valor:
            faltam.append(nome)
            return "[A PREENCHER]"
        return valor

    nome_equipe = campo(equipe["nome"], "Nome da equipe")
    titulo_semana = next(d for s, _, d in CRONOGRAMA if s == semana)
    cabecalho = [f"EQUIPE: {nome_equipe}", "", "INTEGRANTES:"]
    cabecalho += [f"- {n}" for n in integrantes] + ["", f"LÍDER: {lider or '[A PREENCHER]'}", ""]

    if semana == 1:
        assunto = f"P1 - {nome_equipe}: contrato de equipe e comunidade escolhida"
        corpo = cabecalho + [
            "CONTRATO DE EQUIPE", campo(equipe["contrato"], "Contrato de equipe"), "",
            "COMUNIDADE ESCOLHIDA", campo(equipe["comunidade"], "Comunidade escolhida"), "",
            "JUSTIFICATIVA DA ESCOLHA", campo(equipe["justificativa"], "Justificativa da escolha"), "",
            "COMO A EQUIPE PRETENDE FAZER CONTATO COM A COMUNIDADE",
            campo(equipe["contato"], "Como fazer contato com a comunidade"),
        ]
        return assunto, "\n".join(corpo), faltam

    if semana == 2:
        assunto = f"P2 - {nome_equipe}: Registro da Imersão"
        corpo = []
        for i, d in enumerate(diario_ids, start=1):
            corpo.append(f"{i}. {br(d['data'])} - {d['tipo']}" + (f" - {d['local']}" if _txt(d["local"]) else ""))
            if _txt(d["participantes"]):
                corpo.append(f"Integrantes presentes: {d['participantes']}")
            if _txt(d["pessoas_ouvidas"]):
                corpo.append(f"Pessoas ouvidas: {d['pessoas_ouvidas']}")
            corpo.append(f"O que aconteceu: {d['relato']}")
            if _txt(d["aprendizados"]):
                corpo.append(f"Aprendizados: {d['aprendizados']}")
            evid = _linha_evidencia(d["link"], d["arquivo"])
            if evid:
                corpo.append(evid)
            corpo.append("")
        return assunto, "\n".join(corpo).rstrip(), faltam

    # semanas 3 a 10: tarefas e contribuições registradas, para a equipe completar
    assunto = f"Semana {semana} - {nome_equipe}: {titulo_semana}"
    corpo = []
    tarefas = q("""SELECT t.titulo, t.status, m.nome AS responsavel FROM tarefas t
                   LEFT JOIN membros m ON m.id = t.responsavel_id WHERE t.semana = ? ORDER BY t.id""",
                (semana,))
    corpo.append("ATIVIDADES DA SEMANA")
    for _, t in tarefas.iterrows():
        resp = f" ({t['responsavel']})" if _txt(t["responsavel"]) else ""
        corpo.append(f"- {t['titulo']}{resp} - {t['status']}")
    contribs = q("""SELECT c.data, c.tipo, c.descricao, c.link, c.arquivo, m.nome FROM contribuicoes c
                    JOIN membros m ON m.id = c.membro_id WHERE c.semana = ? ORDER BY c.data""", (semana,))
    corpo += ["", "CONTRIBUIÇÕES REGISTRADAS"]
    if contribs.empty:
        corpo.append("- Nenhuma contribuição registrada para esta semana.")
    for _, c in contribs.iterrows():
        evid = _linha_evidencia(c["link"], c["arquivo"])
        corpo.append(f"- {br(c['data'])} - {c['nome']} - {c['tipo']}: {c['descricao']}" + (f" ({evid})" if evid else ""))
    corpo += ["", "[A PREENCHER: complete conforme o que o enunciado da semana pedir]"]
    faltam.append("Texto do enunciado da semana (complete à mão)")
    return assunto, "\n".join(corpo), faltam


def caixa_copiar(rotulo, texto, linhas):
    """Quadro de texto somente leitura com título e botão Copiar na mesma linha, como nos sistemas em geral."""
    st.iframe(
        f"""
        <!-- caixa-visivel -->
        <style>
        body {{ margin: 0; font-family: inherit; }}
        .topo {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; }}
        .rotulo {{ font-weight: 600; font-size: 14px; }}
        button {{ font: inherit; font-size: 13px; padding: 4px 12px; border-radius: 8px; cursor: pointer;
                  background: transparent; color: inherit; border: 1px solid rgba(128,128,128,0.5); }}
        button:hover {{ border-color: #2e7d32; color: #2e7d32; }}
        pre {{ margin: 0; padding: 10px 12px; border-radius: 8px; font: inherit; font-size: 14px;
               white-space: pre-wrap; word-break: break-word; box-sizing: border-box;
               background: rgba(128,128,128,0.12); border: 1px solid rgba(128,128,128,0.3); }}
        </style>
        <div class="topo"><span class="rotulo"></span><button id="copiar">Copiar</button></div>
        <pre id="texto"></pre>
        <script>
        (function() {{
            const estilo = window.parent.getComputedStyle(window.parent.document.body);
            document.body.style.color = estilo.color;
            document.body.style.fontFamily = estilo.fontFamily;
            document.querySelector('.rotulo').textContent = {json.dumps(rotulo)};
            document.getElementById('texto').textContent = {json.dumps(texto)};
            document.getElementById('copiar').addEventListener('click', function () {{
                const botao = this;
                const area = document.createElement('textarea');
                area.value = {json.dumps(texto)};
                document.body.appendChild(area);
                area.select();
                document.execCommand('copy');
                area.remove();
                botao.textContent = 'Copiado';
                setTimeout(function () {{ botao.textContent = 'Copiar'; }}, 1500);
            }});
        }})();
        </script>
        """,
        height=60 + 21 * linhas,
    )


def pg_entrega(u):
    topo = st.container()
    st.caption("Monta o texto da postagem do fórum do AVA com o que já está registrado. "
               "É só copiar e colar.")
    semana = st.segmented_control("Semana", [s for s, _, _ in CRONOGRAMA], default=semana_atual(),
                                  key="semana_entrega", label_visibility="collapsed",
                                  format_func=lambda s: f"S{s}") or semana_atual()
    st.markdown(f"**Semana {semana}** · {next(d for n, _, d in CRONOGRAMA if n == semana)}")
    equipe = q("SELECT * FROM equipe WHERE id = 1").iloc[0]
    membros = q("SELECT nome, lider FROM membros WHERE ativo = 1 ORDER BY nome")
    integrantes = list(membros["nome"])
    lideres = membros[membros["lider"] == 1]["nome"]
    lider = lideres.iloc[0] if not lideres.empty else ""

    diario = pd.DataFrame()
    escolhidos = []
    if semana == 2:
        ini, fim = _janela_semana(2)
        diario = q("""SELECT d.id, d.data, d.tipo, d.local, d.participantes, d.pessoas_ouvidas, d.relato,
                             d.aprendizados, d.link, d.arquivo FROM diario d
                      WHERE d.data >= ? AND d.data < ? ORDER BY d.data, d.id""", (ini, fim))
        todos = q("""SELECT d.id, d.data, d.tipo, d.local, d.participantes, d.pessoas_ouvidas, d.relato,
                            d.aprendizados, d.link, d.arquivo FROM diario d ORDER BY d.data, d.id""")
        if not todos.empty:
            ids = st.multiselect(
                "Registros do Diário de campo que entram na postagem", list(todos["id"]),
                default=[],
                format_func=lambda i: f"{br(todos[todos['id'] == i]['data'].iloc[0])} - "
                                      f"{todos[todos['id'] == i]['tipo'].iloc[0]}")
            escolhidos = [r for _, r in todos[todos["id"].isin(ids)].iterrows()]

    if semana == 1:
        with st.form("dados_p1"):
            contrato = st.text_area("Contrato de equipe", _txt(equipe["contrato"]), height=260)
            comunidade = st.text_input("Comunidade escolhida", _txt(equipe["comunidade"]))
            justificativa = st.text_area("Justificativa da escolha", _txt(equipe["justificativa"]))
            contato = st.text_area("Como a equipe fará contato com a comunidade", _txt(equipe["contato"]))
            if st.form_submit_button("Salvar", type="primary"):
                ex("""UPDATE equipe SET contrato=?, comunidade=?, justificativa=?, contato=? WHERE id=1""",
                   (contrato.strip(), comunidade.strip(), justificativa.strip(), contato.strip()))
                sucesso("Dados da semana 1 salvos.")
        equipe = q("SELECT * FROM equipe WHERE id = 1").iloc[0]

    assunto, mensagem, faltam = _texto_entrega(semana, equipe, integrantes, lider, escolhidos)
    if faltam:
        st.warning("Ainda falta preencher: " + "; ".join(faltam) + ". O nome da equipe fica na tela Equipe.")
    chave_a, chave_m = f"edit_assunto_{semana}", f"edit_msg_{semana}"
    chave_ed = f"editando_{semana}"
    editado = chave_a in st.session_state or chave_m in st.session_state
    editando = st.session_state.get(chave_ed, mensagem == "")

    with topo:
        esq, restaurar, principal = st.columns([4, 1.6, 1.4], vertical_alignment="center")
        esq.header("Entrega da semana")
        if editado and restaurar.button("Restaurar", key=f"orig_{semana}", type="tertiary",
                                        icon=":material/undo:", width="stretch"):
            for chave in (chave_a, chave_m, f"ti_{semana}", f"ta_{semana}"):
                st.session_state.pop(chave, None)
            st.session_state[chave_ed] = False
            st.rerun()
        if editando:
            if principal.button("Concluir", key=f"conclui_{semana}", type="primary",
                                icon=":material/check:", width="stretch"):
                st.session_state[chave_ed] = False
                st.rerun()
        elif principal.button("Editar", key=f"edita_{semana}", type="primary",
                              icon=":material/edit:", width="stretch"):
            st.session_state[chave_ed] = True
            st.rerun()

    if editando:
        st.text_input("Assunto", st.session_state.get(chave_a, assunto), key=f"ti_{semana}",
                      on_change=lambda: st.session_state.update({chave_a: st.session_state[f"ti_{semana}"]}))
        st.text_area("Mensagem", st.session_state.get(chave_m, mensagem), height=460, key=f"ta_{semana}",
                     on_change=lambda: st.session_state.update({chave_m: st.session_state[f"ta_{semana}"]}))
    else:
        texto_a = st.session_state.get(chave_a, assunto)
        texto_m = st.session_state.get(chave_m, mensagem)
        caixa_copiar("Assunto", texto_a, 2)
        caixa_copiar("Mensagem", texto_m, min(40, texto_m.count(chr(10)) + 1 + len(texto_m) // 90))
    if editado:
        st.caption("Texto editado à mão.")
    st.caption("Cole no fórum do AVA, em Adicionar tópico de discussão. Só um integrante posta em nome da equipe.")


def relatorio_membro(mid, nome):
    """Monta o PDF individual com as contribuições do integrante."""
    c = q("SELECT data, semana, tipo, descricao, horas, link, arquivo FROM contribuicoes "
          "WHERE membro_id = ? ORDER BY data", (mid,))
    e = q("SELECT nome, comunidade FROM equipe WHERE id = 1").iloc[0]
    return gerar_pdf(nome, e["nome"], e["comunidade"], c)


def pg_exportar(u):
    st.header("Relatório em PDF")
    membros = q("SELECT id, nome FROM membros WHERE ativo = 1 ORDER BY nome")
    if u["lider"]:
        escolha = st.selectbox("Integrante", membros["nome"])
    else:
        escolha = u["nome"]
        st.write(f"Integrante: **{escolha}**")
    mid = int(membros[membros["nome"] == escolha]["id"].iloc[0])
    st.download_button("Baixar relatório (PDF)", relatorio_membro(mid, escolha),
                       f"relatorio_{escolha.replace(' ', '_')}.pdf", "application/pdf")


PAGINAS = {
    "Painel": (pg_painel, ":material/dashboard:"),
    "Equipe": (pg_equipe, ":material/groups:"),
    "Cronograma": (pg_cronograma, ":material/calendar_month:"),
    "Minhas contribuições": (pg_contribuicoes, ":material/task_alt:"),
    "Diário de campo": (pg_diario, ":material/menu_book:"),
    "Entrega da semana": (pg_entrega, ":material/send:"),
    "Relatório em PDF": (pg_exportar, ":material/picture_as_pdf:"),
}


def injetar_manifest_pwa():
    """
    Aponta o <head> para o manifest e o ícone de atalho do app instalável (static/, servido pelo
    Streamlit em /app/static/). O Streamlit não permite trocar essas tags pelo código do app,
    então o script as altera direto na página.
    """
    if not (Path(__file__).parent / "static" / "manifest.json").exists():
        return
    st.iframe(
        """
        <script>
        (function() {
            const doc = window.parent.document;
            function ligar(rel, href, extra) {
                let el = doc.querySelector('link[rel="' + rel + '"]');
                if (!el) { el = doc.createElement('link'); el.rel = rel; doc.head.appendChild(el); }
                el.href = href;
                if (extra) { Object.keys(extra).forEach(k => el.setAttribute(k, extra[k])); }
            }
            ligar('manifest', 'app/static/manifest.json?v=1');
            ligar('apple-touch-icon', 'app/static/apple-touch-icon.png?v=1');
            if (!doc.querySelector('meta[name="theme-color"]')) {
                const m = doc.createElement('meta'); m.name = 'theme-color'; m.content = '#2e7d32';
                doc.head.appendChild(m);
            }
        })();
        </script>
        """,
        height=1,
        width=1,
    )


def injetar_clique_logo_inicio():
    """
    Faz a logo do topo do menu levar ao Painel ao clicar. O link do st.logo abre outra aba ou
    recarrega a página, então o script clica no primeiro item do menu, reaproveitando a navegação.
    """
    st.iframe(
        """
        <script>
        (function() {
            const win = window.parent;
            if (win.__cliqueLogoInicioAtivo) return;
            win.__cliqueLogoInicioAtivo = true;
            win.document.addEventListener('click', function (e) {
                const logo = e.target.closest && e.target.closest('[data-testid="stSidebarHeader"] img, [data-testid="stLogo"]');
                if (!logo) return;
                const primeiro = win.document.querySelector('[data-testid="stSidebarNav"] a');
                if (primeiro) primeiro.click();
            }, { capture: true });
        })();
        </script>
        """,
        height=1,
        width=1,
    )


def injetar_aviso_saida():
    """
    Mostra o aviso nativo do navegador ('Sair do site?') ao fechar, atualizar ou sair da página.

    O app é uma página única: o conteúdo muda por WebSocket, então o botão Voltar do navegador sai
    do app sem aviso. O texto do aviso é fixo (definido pelo navegador); só dá para ligar ou desligar.
    """
    st.iframe(
        """
        <script>
        (function() {
            const win = window.parent;
            if (win.__avisoSaidaAtivo) return;
            win.__avisoSaidaAtivo = true;
            win.addEventListener('beforeunload', function (e) {
                e.preventDefault();
                e.returnValue = '';
            });
        })();
        </script>
        """,
        height=1,
        width=1,
    )


def aplicar_estilo():
    st.markdown("""
    <style>
    .stMainBlockContainer {
        max-width: 870px;
        padding-left: 2rem;
        padding-right: 2rem;
        margin-left: auto;
        margin-right: auto;
        /* O Streamlit reserva 96px de padding-top por padrão para a barra flutuante. Como a barra é
           baixa e o conteúdo já tem título, o espaço cai para 60px sem encostar nos ícones da barra. */
        padding-top: 60px;
    }
    /* Esconde só o botão "Deploy"; o menu "⋮" continua para trocar o tema. */
    [data-testid="stAppDeployButton"] {
        display: none;
    }
    div[class*="st-key-sidebar_cabecalho"] {
        display: flex;
        flex-direction: column;
        align-items: center;
        text-align: center;
        gap: 2px;
    }
    div[class*="st-key-sidebar_cabecalho"] img {
        margin: 0 auto;
    }
    [data-testid="stSidebarHeader"] img, [data-testid="stLogo"] {
        cursor: pointer;
    }
    .banner-arte {
        aspect-ratio: 1792 / 592;
        background-size: cover;
        background-position: center;
        border-radius: 16px;
        margin-bottom: 16px;
        padding: 0 5%;
        display: flex;
        flex-direction: column;
        justify-content: center;
        box-shadow: 0 10px 25px -5px rgba(46, 125, 50, 0.35);
    }
    .banner-arte p.banner-titulo {
        font-size: clamp(20px, 4.2vw, 48px) !important; font-weight: 800; line-height: 1.1;
        margin: 0; max-width: 48%; color: #1b5e20;
    }
    .banner-arte p.banner-subtitulo {
        font-size: clamp(11px, 1.6vw, 20px) !important; margin: 8px 0 0; max-width: 46%;
        color: #37474f;
    }
    /* Blocos invisíveis (st.iframe de 1 px com JS e o próprio <style>) ocupam uma vaga na lista
       vertical e aparecem como um risco no topo. display:none os tira da lista; o script continua
       rodando e o CSS continua valendo. */
    .stElementContainer:has(iframe):not(:has(iframe[srcdoc*="caixa-visivel"])),
    .stElementContainer:has(style) {
        display: none;
    }
    /* Botão de ação destrutiva dos diálogos de confirmação: vermelho, como nos sistemas em geral. */
    div[class*="st-key-dlg_perigo"] button {
        background-color: #c62828;
        border-color: #c62828;
        color: #ffffff;
    }
    div[class*="st-key-dlg_perigo"] button:hover {
        background-color: #a71f1f;
        border-color: #a71f1f;
        color: #ffffff;
    }
    </style>
    """, unsafe_allow_html=True)


def _como_pagina(funcao, u):
    def pagina():
        funcao(u)
    pagina.__name__ = funcao.__name__
    return pagina


def main():
    st.set_page_config(page_title="Gestor de Equipe", page_icon=str(ARQUIVO_LOGO) if ARQUIVO_LOGO.exists() else "🤝", layout="wide")
    init_db()
    aplicar_estilo()
    injetar_manifest_pwa()
    injetar_aviso_saida()
    injetar_teclado_numerico()
    if "uid" not in st.session_state and not st.session_state.get("limpar_cookie"):
        retomar_sessao()
    if "uid" not in st.session_state:
        if st.session_state.pop("limpar_cookie", False):
            _script_cookie("", 0)
        tela_inicial()
        return
    if st.session_state.get("cookie_novo"):
        _script_cookie(st.session_state.pop("cookie_novo"), DIAS_SESSAO)
    u = usuario()
    if ARQUIVO_LOGO.exists():
        st.logo(str(ARQUIVO_LOGO), size="large")
    injetar_clique_logo_inicio()
    paginas = [st.Page(_como_pagina(funcao, u), title=nome, icon=icone, url_path=slug(nome),
                       default=(i == 0))
               for i, (nome, (funcao, icone)) in enumerate(PAGINAS.items())]
    navegacao = st.navigation(paginas)
    with st.sidebar:
        st.divider()
        st.markdown(f"**{u['nome']}**")
        st.caption("Líder da equipe" if u["lider"] else "Integrante")
        if st.button("Sair", icon=":material/logout:", type="tertiary"):
            encerrar_sessao()
            st.rerun()
    mostrar_aviso()
    navegacao.run()


# Rodar com "python app.py" (ou o play do VS Code) abre o Streamlit sozinho.
if __name__ == '__main__' and not os.environ.get("RODANDO_STREAMLIT"):
    os.environ["RODANDO_STREAMLIT"] = "1"
    subprocess.run([sys.executable, "-m", "streamlit", "run", __file__])
elif __name__ == '__main__':
    main()
