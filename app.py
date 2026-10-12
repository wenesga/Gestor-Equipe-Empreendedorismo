"""Gestor de Equipe - Empreendedorismo e Inovação (LCOMP-EI-2026-2).

Registra contribuições com evidência, diário de campo, cronograma das 10
semanas e avaliação entre pares, para comprovar a participação individual.
Persistência: SQLite (data/equipe.db) + pasta data/uploads.
"""
import hashlib
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
RODADAS = ["Checkpoint 1 (sem. 3)", "Checkpoint 2 (sem. 5-6)", "Avaliação final (sem. 10)"]
CRITERIOS = {
    "presenca": "Presença e pontualidade",
    "entrega": "Cumprimento das tarefas",
    "comunicacao": "Comunicação com a equipe",
    "colaboracao": "Colaboração e iniciativa",
}
DIAS_ALERTA = 14
COOKIE_SESSAO = "gestor_sessao"
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
        CREATE TABLE IF NOT EXISTS avaliacoes(
            id INTEGER PRIMARY KEY, rodada TEXT NOT NULL,
            avaliador_id INTEGER NOT NULL REFERENCES membros(id),
            avaliado_id INTEGER NOT NULL REFERENCES membros(id),
            presenca INTEGER, entrega INTEGER, comunicacao INTEGER, colaboracao INTEGER,
            comentario TEXT, UNIQUE(rodada, avaliador_id, avaliado_id));
        """)
        con.execute("INSERT OR IGNORE INTO equipe(id) VALUES (1)")
        if "codigo" not in [r[1] for r in con.execute("PRAGMA table_info(equipe)")]:
            con.execute("ALTER TABLE equipe ADD COLUMN codigo TEXT")
        if con.execute("SELECT COUNT(*) FROM tarefas").fetchone()[0] == 0:
            con.executemany(
                "INSERT INTO tarefas(semana, prazo, titulo) VALUES (?,?,?)", CRONOGRAMA)


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


def semana_atual():
    hoje = date.today().isoformat()
    atual = 1
    for s, prazo, _ in CRONOGRAMA:
        if hoje >= prazo:
            atual = s
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
    if not token:
        return
    r = q("""SELECT s.membro_id FROM sessoes s JOIN membros m ON m.id = s.membro_id
             WHERE s.token_hash = ? AND s.expira_em > ? AND m.ativo = 1""",
          (hash_pin(token), datetime.now().isoformat()))
    if not r.empty:
        st.session_state["uid"] = int(r["membro_id"].iloc[0])


def encerrar_sessao():
    token = st.context.cookies.get(COOKIE_SESSAO)
    if token:
        ex("DELETE FROM sessoes WHERE token_hash = ?", (hash_pin(token),))
    for chave in ("uid", "pagina"):
        st.session_state.pop(chave, None)
    st.session_state["limpar_cookie"] = True


def _entrar_como(nome):
    iniciar_sessao(q("SELECT id FROM membros WHERE nome = ?", (nome,))["id"].iloc[0])
    st.rerun()


def _salvar_membro(nome, pin, lider):
    """Cria o integrante ou, se o nome estava desativado, reativa com o novo PIN."""
    ex("""INSERT INTO membros(nome, pin_hash, lider) VALUES (?,?,?)
          ON CONFLICT(nome) DO UPDATE SET pin_hash=excluded.pin_hash, ativo=1, lider=excluded.lider""",
       (nome, hash_pin(pin), int(lider)))


def tela_inicial():
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
            if st.form_submit_button("Criar equipe"):
                if not nome or not codigo:
                    st.error("Informe seu nome e o código da equipe.")
                elif not _pin_valido(pin1) or pin1 != pin2:
                    st.error("Use um PIN de 4 dígitos e repita igual.")
                else:
                    ex("UPDATE equipe SET codigo = ? WHERE id = 1", (codigo,))
                    _salvar_membro(nome, pin1, True)
                    _entrar_como(nome)
        return
    aba_entrar, aba_novo = st.tabs(["Entrar", "Sou novo no grupo"])
    with aba_entrar:
        with st.form("login"):
            nome = st.selectbox("Quem é você?", membros["nome"])
            pin = st.text_input("PIN", type="password", max_chars=4)
            if st.form_submit_button("Entrar"):
                m = membros[membros["nome"] == nome].iloc[0]
                if hash_pin(pin) == m["pin_hash"]:
                    iniciar_sessao(m["id"])
                    st.rerun()
                else:
                    st.error("PIN incorreto.")
    with aba_novo:
        if len(membros) >= MAX_MEMBROS:
            st.info(f"A equipe já tem {MAX_MEMBROS} integrantes. Peça ao líder para liberar uma vaga.")
            return
        with st.form("cadastro"):
            nome = " ".join(st.text_input("Seu nome completo").split())
            codigo = st.text_input("Código da equipe").strip()
            pin1 = st.text_input("Crie um PIN de 4 dígitos", type="password", max_chars=4)
            pin2 = st.text_input("Repita o PIN", type="password", max_chars=4)
            if st.form_submit_button("Entrar no grupo"):
                esperado = (q("SELECT codigo FROM equipe WHERE id = 1")["codigo"].iloc[0] or "").lower()
                if not nome:
                    st.error("Informe seu nome.")
                elif codigo.lower() != esperado:
                    st.error("Código da equipe incorreto. Peça ao líder.")
                elif not _pin_valido(pin1) or pin1 != pin2:
                    st.error("Use um PIN de 4 dígitos e repita igual.")
                elif nome.lower() in {n.lower() for n in membros["nome"]}:
                    st.error("Já existe alguém com esse nome. Use a aba Entrar.")
                else:
                    _salvar_membro(nome, pin1, False)
                    _entrar_como(nome)


def registros_do_membro(mid):
    """Conta tudo que referencia o integrante (contribuições, diário, avaliações e tarefas)."""
    with db() as con:
        return con.execute(
            """SELECT (SELECT COUNT(*) FROM contribuicoes WHERE membro_id = :m)
                    + (SELECT COUNT(*) FROM diario WHERE autor_id = :m)
                    + (SELECT COUNT(*) FROM avaliacoes WHERE avaliador_id = :m OR avaliado_id = :m)
                    + (SELECT COUNT(*) FROM tarefas WHERE responsavel_id = :m)""",
            {"m": mid}).fetchone()[0]


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
    st.header("Painel")
    st.write(f"Semana atual do calendário: **{semana_atual()}** de 10")
    membros = q("SELECT id, nome FROM membros WHERE ativo = 1")
    c = q("""SELECT m.nome, COUNT(c.id) AS registros, COALESCE(SUM(c.horas),0) AS horas,
                    MAX(c.data) AS ultimo
             FROM membros m LEFT JOIN contribuicoes c ON c.membro_id = m.id
             WHERE m.ativo = 1 GROUP BY m.id ORDER BY m.nome""")
    st.subheader("Contribuições por integrante")
    st.dataframe(c.rename(columns={"nome": "Integrante", "registros": "Registros",
                                   "horas": "Horas", "ultimo": "Último registro"}),
                 hide_index=True, width="stretch")
    if not c.empty:
        grafico_horas(c)
    limite = (date.today() - pd.Timedelta(days=DIAS_ALERTA)).isoformat()
    parados = c[(c["ultimo"].isna()) | (c["ultimo"] < limite)]
    for _, r in parados.iterrows():
        st.warning(f"{r['nome']} está há mais de {DIAS_ALERTA} dias sem registrar contribuição.")
    t = q("SELECT status, COUNT(*) AS n FROM tarefas GROUP BY status")
    st.subheader("Tarefas")
    cols = st.columns(3)
    for col, s in zip(cols, STATUS):
        n = int(t.loc[t["status"] == s, "n"].sum())
        col.metric(s, n)
    prox = q("""SELECT t.semana, t.prazo, t.titulo, m.nome AS responsavel, t.status
                FROM tarefas t LEFT JOIN membros m ON m.id = t.responsavel_id
                WHERE t.status != 'Concluída' AND t.prazo >= ? ORDER BY t.prazo LIMIT 5""",
             (date.today().isoformat(),))
    st.subheader("Próximos prazos")
    st.dataframe(prox, hide_index=True, width="stretch")


def pg_equipe(u):
    st.header("Equipe e comunidade")
    e = q("SELECT * FROM equipe WHERE id = 1").iloc[0]
    with st.form("equipe"):
        nome = st.text_input("Nome da equipe", e["nome"] or "")
        polo = st.text_input("Polo", e["polo"] or "")
        com = st.text_input("Comunidade escolhida", e["comunidade"] or "")
        just = st.text_area("Justificativa da escolha", e["justificativa"] or "")
        cont = st.text_area("Como a equipe fará contato com a comunidade", e["contato"] or "")
        contrato = st.text_area(
            "Contrato de Equipe (organização, comunicação, divisão de tarefas, participação)",
            e["contrato"] or "", height=250)
        if st.form_submit_button("Salvar"):
            ex("""UPDATE equipe SET nome=?, polo=?, comunidade=?, justificativa=?, contato=?,
                  contrato=? WHERE id=1""", (nome, polo, com, just, cont, contrato))
            st.success("Salvo.")
    st.subheader("Integrantes")
    m = q("SELECT nome, CASE lider WHEN 1 THEN 'Líder' ELSE '' END AS papel FROM membros "
          "WHERE ativo = 1 ORDER BY nome")
    st.dataframe(m, hide_index=True, width="stretch")
    if u["lider"]:
        with st.expander("Ferramentas do líder"):
            atual = q("SELECT codigo FROM equipe WHERE id = 1")["codigo"].iloc[0] or ""
            with st.form("codigo"):
                novo_codigo = st.text_input("Código da equipe (passe aos colegas)", atual).strip()
                if st.form_submit_button("Salvar código") and novo_codigo:
                    ex("UPDATE equipe SET codigo = ? WHERE id = 1", (novo_codigo,))
                    st.success("Código atualizado.")
            outros = q("SELECT id, nome FROM membros WHERE ativo = 1 AND id != ? ORDER BY nome",
                       (int(u["id"]),))
            if not outros.empty:
                st.divider()
                st.markdown("**Gerenciar um integrante**")
                alvo = st.selectbox("1. Escolha o integrante", outros["id"],
                                    format_func=lambda i: outros[outros["id"] == i]["nome"].iloc[0])
                nome_alvo = outros[outros["id"] == alvo]["nome"].iloc[0]
                primeiro = nome_alvo.split()[0]
                st.markdown(f"2. Ações para **{nome_alvo}**:")
                novo_pin = st.text_input(f"Novo PIN para {primeiro} (4 dígitos)", max_chars=4,
                                         type="password")
                c1, c2, c3 = st.columns(3)
                if c1.button(f"Redefinir PIN de {primeiro}"):
                    if _pin_valido(novo_pin):
                        ex("UPDATE membros SET pin_hash = ? WHERE id = ?", (hash_pin(novo_pin), int(alvo)))
                        st.success(f"PIN de {nome_alvo} redefinido.")
                    else:
                        st.error("Informe um PIN de 4 dígitos.")
                if c2.button(f"Passar a liderança para {primeiro}"):
                    with db() as con:
                        con.execute("UPDATE membros SET lider = (id = ?) WHERE ativo = 1", (int(alvo),))
                    st.rerun()
                if c3.button(f"Remover {primeiro} da equipe"):
                    ex("UPDATE membros SET ativo = 0 WHERE id = ?", (int(alvo),))
                    st.rerun()
                st.caption("Remover desativa o acesso, mas mantém os registros que a pessoa já fez.")
                with st.expander(f"Excluir {primeiro} definitivamente (só quem não tem nenhum registro)"):
                    usados = registros_do_membro(int(alvo))
                    if usados:
                        st.info(f"{nome_alvo} tem {usados} registro(s) no sistema. "
                                "Use \"Remover da equipe\" para preservar o histórico.")
                    elif st.button(f"Excluir {primeiro} definitivamente", key="excluir_def"):
                        ex("DELETE FROM membros WHERE id = ?", (int(alvo),))
                        st.rerun()


def pg_cronograma(u):
    st.header("Cronograma e tarefas")
    membros = q("SELECT id, nome FROM membros WHERE ativo = 1 ORDER BY nome")
    nomes = dict(zip(membros["id"], membros["nome"]))
    t = q("SELECT * FROM tarefas ORDER BY semana, prazo, id")
    for sem in sorted(t["semana"].unique()):
        with st.expander(f"Semana {sem} · {t[t['semana'] == sem]['prazo'].iloc[0]}",
                         expanded=(sem == semana_atual())):
            for _, r in t[t["semana"] == sem].iterrows():
                c1, c2, c3 = st.columns([4, 2, 2])
                c1.write(r["titulo"])
                ids = [None] + list(nomes)
                atual = r["responsavel_id"]
                idx = ids.index(int(atual)) if pd.notna(atual) else 0
                resp = c2.selectbox("Responsável", ids, index=idx, key=f"r{r['id']}",
                                    format_func=lambda i: nomes.get(i, "—"),
                                    label_visibility="collapsed")
                stt = c3.selectbox("Status", STATUS, index=STATUS.index(r["status"]),
                                   key=f"s{r['id']}", label_visibility="collapsed")
                if resp != (int(atual) if pd.notna(atual) else None) or stt != r["status"]:
                    ex("UPDATE tarefas SET responsavel_id=?, status=? WHERE id=?",
                       (resp, stt, int(r["id"])))
                    st.rerun()
            with st.form(f"nt{sem}", clear_on_submit=True):
                novo = st.text_input("Nova tarefa nesta semana")
                if st.form_submit_button("Adicionar") and novo.strip():
                    ex("INSERT INTO tarefas(semana, prazo, titulo) VALUES (?,?,?)",
                       (int(sem), t[t["semana"] == sem]["prazo"].iloc[0], novo.strip()))
                    st.rerun()


def pg_contribuicoes(u):
    st.header("Minhas contribuições")
    st.caption("Registre o que você fez, com evidência. É isso que comprova sua participação.")
    with st.form("contrib", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        d = c1.date_input("Data", date.today())
        sem = c2.number_input("Semana", 1, 10, semana_atual())
        horas = c3.number_input("Horas", 0.0, 24.0, 1.0, 0.5)
        tipo = st.selectbox("Tipo de atividade", TIPOS_CONTRIB)
        desc = st.text_area("O que você fez?")
        link = st.text_input("Link da evidência (Drive, documento, foto...)")
        up = st.file_uploader("Ou anexe um arquivo")
        if st.form_submit_button("Registrar"):
            if not desc.strip():
                st.error("Descreva a contribuição.")
            else:
                ex("""INSERT INTO contribuicoes(membro_id, data, semana, tipo, descricao, horas,
                      link, arquivo, criado_em) VALUES (?,?,?,?,?,?,?,?,?)""",
                   (int(u["id"]), d.isoformat(), int(sem), tipo, desc.strip(), horas,
                    link.strip() or None, salvar_arquivo(up), datetime.now().isoformat()))
                st.success("Registrado.")
    ver_todos = st.toggle("Ver de toda a equipe", value=False)
    sql = """SELECT c.id, m.nome, c.data, c.semana, c.tipo, c.descricao, c.horas, c.link, c.arquivo
             FROM contribuicoes c JOIN membros m ON m.id = c.membro_id"""
    df = q(sql + ("" if ver_todos else " WHERE c.membro_id = ?") + " ORDER BY c.data DESC, c.id DESC",
           () if ver_todos else (int(u["id"]),))
    st.dataframe(df.drop(columns=["id"]), hide_index=True, width="stretch")
    meus = df[df["nome"] == u["nome"]]
    if not meus.empty:
        with st.expander("Excluir um registro meu"):
            rid = st.selectbox("Registro", meus["id"],
                               format_func=lambda i: f"{meus[meus['id'] == i]['data'].iloc[0]} · "
                               f"{meus[meus['id'] == i]['descricao'].iloc[0][:50]}")
            if st.button("Excluir"):
                ex("DELETE FROM contribuicoes WHERE id = ? AND membro_id = ?", (int(rid), int(u["id"])))
                st.rerun()


def pg_diario(u):
    st.header("Diário de campo da comunidade")
    nomes = list(q("SELECT nome FROM membros WHERE ativo = 1 ORDER BY nome")["nome"])
    with st.form("diario", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        d = c1.date_input("Data", date.today())
        tipo = c2.selectbox("Tipo", TIPOS_CAMPO)
        local = c3.text_input("Local / canal")
        part = st.multiselect("Integrantes presentes", nomes, default=[u["nome"]])
        ouvidas = st.text_input("Pessoas ouvidas (nome ou perfil)")
        relato = st.text_area("O que aconteceu / o que foi dito", height=150)
        aprend = st.text_area("Aprendizados, dores e necessidades percebidas")
        link = st.text_input("Link de evidência (foto, áudio, documento)")
        up = st.file_uploader("Ou anexe um arquivo", key="up_d")
        if st.form_submit_button("Registrar") and relato.strip():
            ex("""INSERT INTO diario(data, tipo, local, participantes, pessoas_ouvidas, relato,
                  aprendizados, link, arquivo, autor_id) VALUES (?,?,?,?,?,?,?,?,?,?)""",
               (d.isoformat(), tipo, local, ", ".join(part), ouvidas, relato.strip(), aprend,
                link.strip() or None, salvar_arquivo(up), int(u["id"])))
            st.success("Registrado.")
    df = q("""SELECT d.data, d.tipo, d.local, d.participantes, d.pessoas_ouvidas, d.relato,
                     d.aprendizados, d.link, d.arquivo, m.nome AS autor
              FROM diario d LEFT JOIN membros m ON m.id = d.autor_id ORDER BY d.data DESC, d.id DESC""")
    st.dataframe(df, hide_index=True, width="stretch")


def pg_pares(u):
    st.header("Avaliação entre pares")
    st.caption("Suas notas são anônimas: a equipe só vê a média recebida por cada pessoa.")
    rodada = st.selectbox("Rodada", RODADAS)
    outros = q("SELECT id, nome FROM membros WHERE ativo = 1 AND id != ? ORDER BY nome",
               (int(u["id"]),))
    for _, o in outros.iterrows():
        ant = q("SELECT * FROM avaliacoes WHERE rodada=? AND avaliador_id=? AND avaliado_id=?",
                (rodada, int(u["id"]), int(o["id"])))
        v = ant.iloc[0] if not ant.empty else None
        with st.expander(o["nome"] + ("  ✔" if v is not None else "")):
            with st.form(f"av{o['id']}_{rodada}"):
                notas = {k: st.slider(lbl, 1, 5, int(v[k]) if v is not None else 3)
                         for k, lbl in CRITERIOS.items()}
                com = st.text_area("Comentário (opcional)", (v["comentario"] or "") if v is not None else "")
                if st.form_submit_button("Salvar avaliação"):
                    ex("""INSERT INTO avaliacoes(rodada, avaliador_id, avaliado_id, presenca, entrega,
                          comunicacao, colaboracao, comentario) VALUES (?,?,?,?,?,?,?,?)
                          ON CONFLICT(rodada, avaliador_id, avaliado_id) DO UPDATE SET
                          presenca=excluded.presenca, entrega=excluded.entrega,
                          comunicacao=excluded.comunicacao, colaboracao=excluded.colaboracao,
                          comentario=excluded.comentario""",
                       (rodada, int(u["id"]), int(o["id"]), notas["presenca"], notas["entrega"],
                        notas["comunicacao"], notas["colaboracao"], com))
                    st.success("Salvo.")
    st.subheader("Médias recebidas")
    med = q("""SELECT m.nome AS Integrante, COUNT(a.id) AS Avaliações,
                      ROUND(AVG(a.presenca),2) AS Presença, ROUND(AVG(a.entrega),2) AS Entrega,
                      ROUND(AVG(a.comunicacao),2) AS Comunicação,
                      ROUND(AVG(a.colaboracao),2) AS Colaboração
               FROM membros m LEFT JOIN avaliacoes a ON a.avaliado_id = m.id AND a.rodada = ?
               WHERE m.ativo = 1 GROUP BY m.id ORDER BY m.nome""", (rodada,))
    st.dataframe(med, hide_index=True, width="stretch")


def relatorio_membro(mid, nome):
    """Monta o PDF individual com as contribuições e as médias de avaliação recebidas."""
    c = q("SELECT data, semana, tipo, descricao, horas, link, arquivo FROM contribuicoes "
          "WHERE membro_id = ? ORDER BY data", (mid,))
    med = q("""SELECT rodada AS Rodada, ROUND(AVG(presenca),2) AS Presença,
                      ROUND(AVG(entrega),2) AS Tarefas, ROUND(AVG(comunicacao),2) AS Comunicação,
                      ROUND(AVG(colaboracao),2) AS Colaboração
               FROM avaliacoes WHERE avaliado_id = ? GROUP BY rodada""", (mid,))
    e = q("SELECT nome, comunidade FROM equipe WHERE id = 1").iloc[0]
    return gerar_pdf(nome, e["nome"], e["comunidade"], c, med)


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
    "Painel": pg_painel,
    "Equipe e comunidade": pg_equipe,
    "Cronograma": pg_cronograma,
    "Minhas contribuições": pg_contribuicoes,
    "Diário de campo": pg_diario,
    "Avaliação entre pares": pg_pares,
    "Relatório em PDF": pg_exportar,
}


def aplicar_estilo():
    """Abas com cara de aba: borda, cantos arredondados e a ativa em destaque."""
    st.markdown("""
    <style>
    div[role="tablist"] {
        gap: 4px;
        border-bottom: 1px solid rgba(128, 128, 128, 0.35);
    }
    div[role="tablist"] .react-aria-SelectionIndicator {
        display: none;
    }
    div[data-testid="stTab"] {
        background-color: rgba(128, 128, 128, 0.10);
        border: 1px solid rgba(128, 128, 128, 0.30);
        border-bottom: none;
        border-radius: 10px 10px 0 0;
        padding: 8px 16px;
        margin-bottom: 0;
    }
    div[data-testid="stTab"]:hover {
        background-color: rgba(46, 125, 50, 0.10);
    }
    div[data-testid="stTab"][aria-selected="true"] {
        background-color: rgba(46, 125, 50, 0.14);
        border-color: rgba(46, 125, 50, 0.55);
        border-top: 3px solid #2e7d32;
        font-weight: 600;
    }
    section[data-testid="stSidebar"] .stButton button {
        min-height: 2.8rem;
    }
    section[data-testid="stSidebar"] .stButton button p {
        font-size: 1.1rem;
    }
    </style>
    """, unsafe_allow_html=True)


def main():
    st.set_page_config(page_title="Gestor de Equipe", page_icon="🤝", layout="wide")
    init_db()
    aplicar_estilo()
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
    with st.sidebar:
        st.write(f"**{u['nome']}**" + (" (líder)" if u["lider"] else ""))
        st.divider()
        pagina = st.session_state.setdefault("pagina", next(iter(PAGINAS)))
        for nome in PAGINAS:
            if st.button(nome, key=f"menu_{nome}", width="stretch",
                         type="primary" if nome == pagina else "tertiary"):
                st.session_state["pagina"] = nome
                st.rerun()
        st.divider()
        if st.button("Sair"):
            encerrar_sessao()
            st.rerun()
    PAGINAS[pagina](u)


# Rodar com "python app.py" (ou o play do VS Code) abre o Streamlit sozinho.
if __name__ == '__main__' and not os.environ.get("RODANDO_STREAMLIT"):
    os.environ["RODANDO_STREAMLIT"] = "1"
    subprocess.run([sys.executable, "-m", "streamlit", "run", __file__])
elif __name__ == '__main__':
    main()
