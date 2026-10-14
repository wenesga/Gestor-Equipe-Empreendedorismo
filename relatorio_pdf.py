"""Relatório individual em PDF: contribuições com evidência e o que os colegas marcaram sobre a participação."""

import zlib
from datetime import date
from pathlib import Path

from fpdf import FPDF
from PIL import Image

ARQUIVO_CABECALHO = Path(__file__).parent / "imagens" / "cabecalho.png"

VERDE = (46, 125, 50)
VERDE_CLARO = (232, 245, 233)
TEXTO = (33, 37, 41)
CINZA = (96, 108, 118)
CINZA_CLARO = (246, 248, 250)
LINHA = (222, 226, 230)
AZUL_LINK = (21, 101, 192)
AMARELO = (249, 168, 37)
VERMELHO = (198, 40, 40)
CORES_TIPO = [(46, 125, 50), (21, 101, 192), (239, 108, 0), (123, 31, 162), (0, 131, 143), (194, 24, 91)]
MARGEM = 16


def _t(texto):
    """As fontes embutidas do PDF só têm Latin-1: troca o que não existe nela por equivalentes."""
    texto = str(texto if texto is not None else "")
    for a, b in {"—": "-", "–": "-", "…": "...", "“": '"', "”": '"', "‘": "'", "’": "'",
                 "•": "-", "→": "->", "·": "-"}.items():
        texto = texto.replace(a, b)
    return texto.encode("latin-1", "replace").decode("latin-1")


def _texto(valor):
    return valor if isinstance(valor, str) else ""


def _cor_tipo(tipo):
    return CORES_TIPO[zlib.crc32(str(tipo).encode("utf-8")) % len(CORES_TIPO)]


class _PDF(FPDF):
    def header(self):
        """
        Timbre institucional só no topo da primeira página. pdf.image() não move o cursor, então o Y
        inicial do conteúdo sai da proporção real do arquivo (lida com PIL). Sem o arquivo, o
        relatório sai sem timbre.
        """
        if self.page_no() != 1 or not ARQUIVO_CABECALHO.exists():
            return
        largura = self.w - self.l_margin - self.r_margin
        self.image(str(ARQUIVO_CABECALHO), x=self.l_margin, y=10, w=largura)
        with Image.open(ARQUIVO_CABECALHO) as img:
            altura = largura * img.height / img.width
        self.set_y(10 + altura + 6)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(*LINHA)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(2)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*CINZA)
        self.cell(0, 5, _t("Gestor de Equipe - Empreendedorismo e Inovação"), align="L")
        self.set_x(self.l_margin)
        self.cell(0, 5, f"Página {self.page_no()} de {{nb}}", align="R")


def _secao(pdf, titulo):
    """Título de seção com uma barra verde à esquerda."""
    pdf.ln(5)
    if pdf.get_y() > pdf.h - 40:
        pdf.add_page()
    y = pdf.get_y()
    pdf.set_fill_color(*VERDE)
    pdf.rect(pdf.l_margin, y + 0.8, 1.6, 6.4, style="F")
    pdf.set_xy(pdf.l_margin + 4, y)
    pdf.set_font("Helvetica", "B", 12.5)
    pdf.set_text_color(*TEXTO)
    pdf.cell(0, 8, _t(titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1.5)


def _cartao_resumo(pdf, x, y, w, h, valor, rotulo):
    pdf.set_fill_color(*VERDE_CLARO)
    pdf.rect(x, y, w, h, style="F", round_corners=True, corner_radius=2.5)
    pdf.set_xy(x, y + 3.5)
    pdf.set_font("Helvetica", "B", 19)
    pdf.set_text_color(*VERDE)
    pdf.cell(w, 9, _t(valor), align="C")
    pdf.set_xy(x, y + 13.5)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*CINZA)
    pdf.cell(w, 5, _t(rotulo), align="C")


def _grafico_horas(pdf, horas_por_semana):
    """Barras verticais de horas por semana (1 a 10), desenhadas direto no PDF."""
    largura = pdf.w - pdf.l_margin - pdf.r_margin
    coluna = largura / 10
    altura_max = 24
    maximo = max(horas_por_semana.values(), default=0) or 1
    y_base = pdf.get_y() + altura_max + 7
    pdf.set_draw_color(*LINHA)
    pdf.line(pdf.l_margin, y_base, pdf.w - pdf.r_margin, y_base)
    for semana in range(1, 11):
        h = horas_por_semana.get(semana, 0)
        x = pdf.l_margin + (semana - 1) * coluna
        barra = max(0.8, altura_max * h / maximo) if h else 0.8
        pdf.set_fill_color(*(VERDE if h else LINHA))
        pdf.rect(x + coluna * 0.22, y_base - barra, coluna * 0.56, barra, style="F",
                 round_corners=True, corner_radius=0.6)
        pdf.set_font("Helvetica", "B" if h else "", 7.5)
        pdf.set_text_color(*(TEXTO if h else CINZA))
        if h:
            pdf.set_xy(x, y_base - barra - 4.5)
            pdf.cell(coluna, 4, f"{h:g}", align="C")
        pdf.set_xy(x, y_base + 1)
        pdf.set_font("Helvetica", "", 7.5)
        pdf.set_text_color(*CINZA)
        pdf.cell(coluna, 4, f"S{semana}", align="C")
    pdf.set_y(y_base + 6)


def _cartao_contribuicao(pdf, r):
    """Um cartão por contribuição: faixa colorida do tipo, cabeçalho, descrição e evidência."""
    largura = pdf.w - pdf.l_margin - pdf.r_margin
    recuo = 6
    larg_texto = largura - recuo - 3
    pdf.set_font("Helvetica", "", 9.5)
    descricao = _t(r["descricao"])
    linhas = pdf.multi_cell(larg_texto, 4.9, descricao, split_only=True)
    altura = 12 + len(linhas) * 4.9 + 8
    if pdf.get_y() + altura > pdf.h - pdf.b_margin:
        pdf.add_page()
    x, y = pdf.l_margin, pdf.get_y()
    pdf.set_fill_color(*CINZA_CLARO)
    pdf.rect(x, y, largura, altura, style="F", round_corners=True, corner_radius=2)
    pdf.set_fill_color(*_cor_tipo(r["tipo"]))
    pdf.rect(x, y, 1.8, altura, style="F")

    data = _texto(r["data"])
    data_br = f"{data[8:10]}/{data[5:7]}/{data[:4]}" if len(data) >= 10 else ""
    pdf.set_xy(x + recuo, y + 2)
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(*_cor_tipo(r["tipo"]))
    pdf.cell(larg_texto - 22, 5, _t(f"{r['tipo']}"))
    pdf.set_font("Helvetica", "B", 9.5)
    pdf.set_text_color(*TEXTO)
    pdf.cell(22, 5, _t(f"{r['horas']:g} h"), align="R")
    pdf.set_xy(x + recuo, y + 7)
    pdf.set_font("Helvetica", "", 8)
    pdf.set_text_color(*CINZA)
    pdf.cell(larg_texto, 4, _t(f"{data_br}   -   Semana {r['semana']}"))

    pdf.set_xy(x + recuo, y + 12)
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*TEXTO)
    pdf.multi_cell(larg_texto, 4.9, descricao, new_x="LEFT", new_y="NEXT")

    link, arquivo = _texto(r["link"]), _texto(r["arquivo"])
    pdf.set_xy(x + recuo, y + altura - 6)
    pdf.set_font("Helvetica", "", 8)
    if link:
        pdf.set_text_color(*AZUL_LINK)
        pdf.cell(larg_texto, 4, _t("Evidência: " + link), link=link if link.startswith("http") else "")
    elif arquivo:
        pdf.set_text_color(*CINZA)
        pdf.cell(larg_texto, 4, _t("Evidência: arquivo anexado (" + arquivo.split("_", 1)[-1] + ")"))
    else:
        pdf.set_text_color(*CINZA)
        pdf.set_font("Helvetica", "I", 8)
        pdf.cell(larg_texto, 4, _t("Sem evidência anexada"))
    pdf.set_y(y + altura + 3)


def _tabela_participacao(pdf, medias):
    largura = pdf.w - pdf.l_margin - pdf.r_margin
    primeira = 62
    outras = (largura - primeira) / 3
    cabecalho = [("Participou", VERDE), ("Participou pouco", AMARELO), ("Não participou", VERMELHO)]
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*VERDE)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(primeira, 8, "  Rodada", fill=True)
    for titulo, _ in cabecalho:
        pdf.cell(outras, 8, _t(titulo), fill=True, align="C")
    pdf.ln(8)
    for i, (_, r) in enumerate(medias.iterrows()):
        pdf.set_fill_color(*(CINZA_CLARO if i % 2 == 0 else (255, 255, 255)))
        pdf.set_font("Helvetica", "", 9.5)
        pdf.set_text_color(*TEXTO)
        pdf.cell(primeira, 8, _t("  " + str(r["Rodada"])), fill=True)
        for (titulo, cor), chave in zip(cabecalho, ["Participou", "Participou pouco", "Não participou"]):
            valor = int(r[chave])
            pdf.set_font("Helvetica", "B" if valor else "", 9.5)
            pdf.set_text_color(*(cor if valor else CINZA))
            pdf.cell(outras, 8, str(valor), fill=True, align="C")
        pdf.ln(8)
    pdf.ln(1)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*CINZA)
    pdf.cell(0, 5, _t("Cada número é a quantidade de colegas que marcou essa opção. As respostas são anônimas."),
             new_x="LMARGIN", new_y="NEXT")


def gerar_pdf(nome, equipe, comunidade, contribuicoes, medias):
    """
    contribuicoes: DataFrame com data, semana, tipo, descricao, horas, link, arquivo.
    medias: DataFrame com a rodada e a contagem de colegas por resposta (participou, pouco, não).
    """
    pdf = _PDF(format="A4")
    pdf.set_margins(MARGEM, 16, MARGEM)
    pdf.set_auto_page_break(True, margin=20)
    pdf.alias_nb_pages()
    pdf.add_page()

    # título
    pdf.set_font("Helvetica", "B", 8.5)
    pdf.set_text_color(*VERDE)
    pdf.cell(0, 5, "RELATÓRIO INDIVIDUAL", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*TEXTO)
    pdf.cell(0, 11, _t(nome), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9.5)
    pdf.set_text_color(*CINZA)
    partes = [p for p in [equipe, comunidade and f"Comunidade: {comunidade}"] if p]
    if partes:
        pdf.cell(0, 5.5, _t("   -   ".join(partes)), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 5.5, f"Gerado em {date.today():%d/%m/%Y}", new_x="LMARGIN", new_y="NEXT")

    # cartões de resumo
    total_horas = float(contribuicoes["horas"].sum()) if len(contribuicoes) else 0.0
    semanas = int(contribuicoes["semana"].nunique()) if len(contribuicoes) else 0
    participou = int(medias["Participou"].sum()) if len(medias) else 0
    respostas = int(medias[["Participou", "Participou pouco", "Não participou"]].sum().sum()) if len(medias) else 0
    pdf.ln(4)
    y = pdf.get_y()
    largura = pdf.w - pdf.l_margin - pdf.r_margin
    gap = 4
    w = (largura - 3 * gap) / 4
    cartoes = [
        (str(len(contribuicoes)), "contribuições"),
        (f"{total_horas:g} h", "horas registradas"),
        (f"{semanas} de 10", "semanas com atividade"),
        (f"{participou} de {respostas}" if respostas else "-", "marcaram que participou"),
    ]
    for i, (valor, rotulo) in enumerate(cartoes):
        _cartao_resumo(pdf, pdf.l_margin + i * (w + gap), y, w, 21, valor, rotulo)
    pdf.set_y(y + 22)

    # horas por semana
    _secao(pdf, "Horas por semana")
    horas = {}
    for _, r in contribuicoes.iterrows():
        horas[int(r["semana"])] = horas.get(int(r["semana"]), 0) + float(r["horas"])
    _grafico_horas(pdf, horas)

    # contribuições
    _secao(pdf, "Contribuições")
    if contribuicoes.empty:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*CINZA)
        pdf.cell(0, 6, "Nenhuma contribuição registrada.", new_x="LMARGIN", new_y="NEXT")
    for _, r in contribuicoes.iterrows():
        _cartao_contribuicao(pdf, r)

    # participação segundo os colegas
    _secao(pdf, "Participação segundo os colegas")
    if medias.empty:
        pdf.set_font("Helvetica", "I", 10)
        pdf.set_text_color(*CINZA)
        pdf.cell(0, 6, "Ainda sem respostas dos colegas.", new_x="LMARGIN", new_y="NEXT")
    else:
        _tabela_participacao(pdf, medias)
    return bytes(pdf.output())
