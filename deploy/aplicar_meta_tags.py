"""
Grava no index.html do Streamlit instalado o título e as etiquetas de prévia de compartilhamento
(WhatsApp, Telegram etc.). O Streamlit não permite alterar o <head> pelo código do app, e os
robôs de prévia não executam JavaScript, então as etiquetas precisam estar no HTML servido.

Uso (com o Python do ambiente virtual do app; repetir após atualizar o Streamlit):
    .venv/bin/python deploy/aplicar_meta_tags.py https://gestorequipe.duckdns.org
"""
import os
import sys

import streamlit

DESCRICAO = "Gestão da equipe de Empreendedorismo e Inovação: tarefas, contribuições e diário de campo"


def main():
    dominio = (sys.argv[1] if len(sys.argv) > 1 else "https://gestorequipe.duckdns.org").rstrip("/")
    caminho = os.path.join(os.path.dirname(streamlit.__file__), "static", "index.html")
    with open(caminho, encoding="utf-8") as f:
        html = f.read()
    if 'property="og:title"' in html:
        print("Etiquetas já aplicadas:", caminho)
        return
    etiquetas = (
        '<title>Gestor de Equipe</title>'
        f'<meta name="description" content="{DESCRICAO}" />'
        '<meta name="theme-color" content="#2e7d32" />'
        '<meta property="og:type" content="website" />'
        '<meta property="og:title" content="Gestor de Equipe" />'
        f'<meta property="og:description" content="{DESCRICAO}" />'
        f'<meta property="og:image" content="{dominio}/app/static/previa.png" />'
        '<meta property="og:image:width" content="512" />'
        '<meta property="og:image:height" content="512" />'
    )
    if "<title>Streamlit</title>" not in html:
        sys.exit("Não achei <title>Streamlit</title> no index.html; nada foi alterado.")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(html.replace("<title>Streamlit</title>", etiquetas, 1))
    print("Etiquetas aplicadas:", caminho)


main()
