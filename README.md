# Gestor de Equipe

Sistema web simples para uma equipe de estudantes organizar um projeto de empreendedorismo e inovação social: tarefas por semana, contribuição de cada integrante com evidência, diário de campo da comunidade, avaliação entre pares e relatório individual em PDF.

Feito em Python com [Streamlit](https://streamlit.io). Os dados ficam em um banco SQLite local, sem serviços externos.

## O que faz

- **Painel:** horas e registros por integrante, tarefas por status, próximos prazos, barra de progresso da semana e aviso de quem está há mais de 14 dias sem registrar nada.
- **Equipe e comunidade:** contrato de equipe, comunidade escolhida e ferramentas do líder (código de entrada, redefinir PIN, passar a liderança, remover ou excluir integrante).
- **Cronograma:** 10 semanas com prazo, responsável e status de cada tarefa.
- **Minhas contribuições:** registro com data, tipo, horas, descrição e evidência (link ou arquivo; imagens aparecem em prévia).
- **Diário de campo:** visitas, entrevistas e observações na comunidade.
- **Avaliação entre pares:** notas de 1 a 5 em quatro critérios, anônimas; cada um vê só a média que recebeu.
- **Relatório em PDF:** contribuições com evidência e médias recebidas, com cabeçalho institucional.

O guia de uso para a equipe está em [GUIA-EQUIPE.md](GUIA-EQUIPE.md).

## Como entrar

- **Primeiro acesso (banco vazio):** quem abrir primeiro cria a equipe, vira o líder e define o **código da equipe**.
- **Demais integrantes:** aba "Sou novo no grupo", com nome, código da equipe e um PIN de 4 dígitos.
- **Depois:** escolher o nome na lista e digitar o PIN. O login fica lembrado por 30 dias.

O PIN evita acesso por engano, mas não é segurança forte. Não registre informações sensíveis de moradores.

## Rodar no computador

Requer Python 3.10 ou superior.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux e macOS
pip install -r requirements.txt
python app.py
```

O `python app.py` abre o Streamlit sozinho no navegador. Também funciona com `streamlit run app.py`.

Para ver o sistema com dados de exemplo (equipe fictícia, PIN `1234`, código `exemplo26`):

```bash
python seed_exemplo.py            # só funciona com o banco vazio
python seed_exemplo.py --limpar   # apaga a pasta data/ e recria os exemplos
```

Para recomeçar do zero, apague a pasta `data/`.

## Estrutura

```
app.py               aplicação (telas, banco, login)
relatorio_pdf.py     geração do relatório em PDF
seed_exemplo.py      dados de exemplo
imagens/             logo, banner e cabeçalho do relatório
static/              manifest e ícones do app instalável, imagem de prévia
deploy/              script que grava as etiquetas de prévia de compartilhamento
.streamlit/          tema e configuração do Streamlit
data/                banco SQLite e anexos (criada na execução; não é versionada)
```

## Colocar em um servidor

O sistema roda como um serviço comum de Streamlit atrás de um proxy HTTPS. Em linhas gerais:

1. Clonar o repositório, criar o ambiente virtual e instalar `requirements.txt`.
2. Rodar como serviço (`systemd`, por exemplo) com `streamlit run app.py --server.address=127.0.0.1 --server.port=<porta> --server.headless=true`.
3. Colocar um proxy (Nginx) com certificado HTTPS na frente, repassando WebSocket. Para anexos maiores, aumentar `client_max_body_size`.
4. Opcional: gravar as etiquetas de prévia de compartilhamento (WhatsApp e similares) no `index.html` do Streamlit, repetindo após atualizar o Streamlit:

```bash
.venv/bin/python deploy/aplicar_meta_tags.py https://seu-dominio
```

Os dados ficam na pasta `data/` do servidor. Faça cópia dela periodicamente.

## Adaptar para outra equipe

- Textos e prazos das 10 semanas: lista `CRONOGRAMA` no início do `app.py`.
- Rodadas de avaliação e critérios: `RODADAS` e `CRITERIOS`.
- Identidade visual: troque os arquivos de `imagens/` e `static/` e a cor em `.streamlit/config.toml`.

## Licença

[MIT](LICENSE).
