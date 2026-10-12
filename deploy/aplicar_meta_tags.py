"""
Grava no index.html do Streamlit instalado o título e as etiquetas de prévia de compartilhamento
(WhatsApp, Telegram etc.). O Streamlit não permite alterar o <head> pelo código do app, e os
robôs de prévia não executam JavaScript, então as etiquetas precisam estar no HTML servido.

Só acrescenta o que ainda não existe, então pode ser repetido sem duplicar nada.

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
    if "</head>" not in html:
        sys.exit("Não achei </head> no index.html; nada foi alterado.")

    novo = html.replace("<title>Streamlit</title>", "<title>Gestor de Equipe</title>", 1)
    faltantes = []
    candidatas = [
        ('name="description"', f'<meta name="description" content="{DESCRICAO}" />'),
        ('name="theme-color"', '<meta name="theme-color" content="#2e7d32" />'),
        ('property="og:type"', '<meta property="og:type" content="website" />'),
        ('property="og:title"', '<meta property="og:title" content="Gestor de Equipe" />'),
        ('property="og:description"', f'<meta property="og:description" content="{DESCRICAO}" />'),
        ('property="og:image"', f'<meta property="og:image" content="{dominio}/app/static/previa.png" />'),
        ('property="og:image:width"', '<meta property="og:image:width" content="512" />'),
        ('property="og:image:height"', '<meta property="og:image:height" content="512" />'),
    ]
    for chave, tag in candidatas:
        if chave not in novo:
            faltantes.append(tag)
    if faltantes:
        novo = novo.replace("</head>", "".join(faltantes) + "</head>", 1)
    if novo == html:
        print("Nada a fazer; etiquetas já aplicadas:", caminho)
        return
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(novo)
    print(f"Etiquetas acrescentadas ({len(faltantes)}):", caminho)


main()
