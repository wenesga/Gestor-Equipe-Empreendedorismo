"""Relatório individual em PDF: contribuições com evidência e o que os colegas marcaram sobre a participação."""

from datetime import date
from pathlib import Path

from fpdf import FPDF
from PIL import Image

ARQUIVO_CABECALHO = Path(__file__).parent / "imagens" / "cabecalho.png"
AZUL = (31, 78, 154)
CINZA = (90, 98, 112)
LINHA = (225, 229, 236)


def _t(texto):
    """As fontes embutidas do PDF só têm Latin-1: troca o que não existe nela por equivalentes."""
    texto = str(texto if texto is not None else "")
    for a, b in {"—": "-", "–": "-", "…": "...", "“": '"', "”": '"', "‘": "'", "’": "'",
                 "•": "-", "→": "->", "·": "-"}.items():
        texto = texto.replace(a, b)
    return texto.encode("latin-1", "replace").decode("latin-1")


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


def _secao(pdf, titulo):
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 8, _t(titulo), new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*LINHA)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)
    pdf.set_text_color(30, 30, 30)


def gerar_pdf(nome, equipe, comunidade, contribuicoes, medias):
    """
    contribuicoes: DataFrame com data, semana, tipo, descricao, horas, link, arquivo.
    medias: DataFrame com a rodada e a contagem de colegas por resposta (participou, pouco, não).
    """
    pdf = _PDF(format="A4")
    pdf.set_margins(18, 16, 18)
    pdf.set_auto_page_break(True, margin=16)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 18)
    pdf.set_text_color(*AZUL)
    pdf.cell(0, 10, "Relatório individual", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 8, _t(nome), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*CINZA)
    partes = [p for p in [equipe, comunidade and f"Comunidade: {comunidade}"] if p]
    if partes:
        pdf.cell(0, 6, _t(" - ".join(partes)), new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"Gerado em {date.today():%d/%m/%Y}", new_x="LMARGIN", new_y="NEXT")

    _secao(pdf, "Resumo")
    horas = float(contribuicoes["horas"].sum()) if len(contribuicoes) else 0.0
    semanas = contribuicoes["semana"].nunique() if len(contribuicoes) else 0
    pdf.set_font("Helvetica", "", 10.5)
    pdf.set_text_color(30, 30, 30)
    for rotulo, valor in [("Registros", len(contribuicoes)), ("Horas totais", f"{horas:.1f}"),
                          ("Semanas com contribuição", semanas)]:
        pdf.set_font("Helvetica", "B", 10.5)
        pdf.cell(55, 6.5, _t(rotulo))
        pdf.set_font("Helvetica", "", 10.5)
        pdf.cell(0, 6.5, _t(valor), new_x="LMARGIN", new_y="NEXT")

    _secao(pdf, "Contribuições")
    if contribuicoes.empty:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 6, "Nenhuma contribuição registrada.", new_x="LMARGIN", new_y="NEXT")
    for _, r in contribuicoes.iterrows():
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_text_color(*AZUL)
        pdf.cell(0, 6, _t(f"{r['data'][8:10]}/{r['data'][5:7]}/{r['data'][:4]}  -  Semana {r['semana']}"
                          f"  -  {r['tipo']}  -  {r['horas']:g} h"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(30, 30, 30)
        pdf.multi_cell(0, 5.2, _t(r["descricao"]), new_x="LMARGIN", new_y="NEXT")
        link = r["link"] if isinstance(r["link"], str) else ""
        arquivo = r["arquivo"] if isinstance(r["arquivo"], str) else ""
        evidencia = link or (f"arquivo anexo ({arquivo})" if arquivo else "")
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*CINZA)
        pdf.multi_cell(0, 4.8, _t("Evidência: " + (evidencia or "não informada")),
                       new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2.5)

    _secao(pdf, "Participação segundo os colegas")
    if medias.empty:
        pdf.set_font("Helvetica", "I", 10)
        pdf.cell(0, 6, "Ainda sem respostas dos colegas.", new_x="LMARGIN", new_y="NEXT")
    else:
        colunas = list(medias.columns)
        larguras = [58] + [(pdf.w - pdf.l_margin - pdf.r_margin - 58) / (len(colunas) - 1)] * (len(colunas) - 1)
        pdf.set_font("Helvetica", "B", 9.5)
        pdf.set_fill_color(240, 243, 248)
        pdf.set_text_color(30, 30, 30)
        for c, w in zip(colunas, larguras):
            pdf.cell(w, 7, _t(c), border=0, fill=True)
        pdf.ln()
        pdf.set_font("Helvetica", "", 9.5)
        for _, r in medias.iterrows():
            for c, w in zip(colunas, larguras):
                v = r[c]
                pdf.cell(w, 7, _t(v), border="B")
            pdf.ln()
    return bytes(pdf.output())
