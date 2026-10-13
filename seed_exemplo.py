"""Preenche o banco com dados de EXEMPLO para você ver o painel e os relatórios.

Uso:
    python seed_exemplo.py            # só funciona se o banco estiver vazio
    python seed_exemplo.py --limpar   # apaga data/ inteira e recria com exemplos

Integrantes de exemplo: Ana, Bruno, Carla, Diego (PIN 1234; Ana é a líder).
Código da equipe de exemplo: exemplo26.
Para voltar ao zero, apague a pasta data/.
"""
import os
import shutil
import sys
from datetime import date, timedelta

os.environ["RODANDO_STREAMLIT"] = "1"  # importar app.py não abre o Streamlit
import app  # noqa: E402


def main():
    if "--limpar" in sys.argv and app.DATA_DIR.exists():
        shutil.rmtree(app.DATA_DIR)
        app.DATA_DIR.mkdir()
        app.UPLOAD_DIR.mkdir()
    app.init_db()
    if not app.q("SELECT id FROM membros").empty:
        print("O banco já tem membros. Use --limpar para recomeçar com os exemplos.")
        return

    hoje = date.today()
    d = lambda dias: (hoje - timedelta(days=dias)).isoformat()

    for i, nome in enumerate(["Ana Souza", "Bruno Lima", "Carla Dias", "Diego Rocha"]):
        app.ex("INSERT INTO membros(nome, pin_hash, lider) VALUES (?,?,?)",
               (nome, app.hash_pin("1234"), int(i == 0)))
    ids = {r["nome"]: int(r["id"]) for _, r in app.q("SELECT id, nome FROM membros").iterrows()}
    ana, bruno, carla, diego = (ids[n] for n in ["Ana Souza", "Bruno Lima", "Carla Dias", "Diego Rocha"])

    app.ex("""UPDATE equipe SET nome=?, polo=?, comunidade=?, justificativa=?, contato=?, contrato=?, codigo=?
              WHERE id=1""",
           ("Equipe Horizonte (EXEMPLO)", "Araguaína", "Feira do bairro (exemplo)",
            "Comunidade próxima de todos, com acesso fácil e diversidade de feirantes.",
            "Visita presencial aos sábados e conversa com a associação de feirantes.",
            "1. Reunião semanal às quartas, 20h, por videochamada.\n"
            "2. Comunicação pelo grupo; resposta em até 24h.\n"
            "3. Tarefas divididas na reunião e registradas no sistema.\n"
            "4. Cada um registra suas contribuições com evidência.",
            "exemplo26"))

    contribs = [
        (ana, d(28), 1, "Coordenação/gestão", "Criou o grupo e organizou o contrato de equipe.", 2.0, "https://exemplo.com/contrato"),
        (bruno, d(27), 1, "Redação/documento", "Redigiu a versão final do contrato.", 1.5, None),
        (carla, d(21), 2, "Visita/contato com a comunidade", "Primeira visita à feira e conversa com 3 feirantes.", 3.0, "https://exemplo.com/fotos"),
        (diego, d(21), 2, "Visita/contato com a comunidade", "Acompanhou a visita e registrou fotos.", 3.0, None),
        (ana, d(20), 2, "Redação/documento", "Escreveu o Registro da Imersão.", 2.5, None),
        (bruno, d(14), 3, "Pesquisa", "Levantou dados sobre feiras livres na cidade.", 2.0, "https://exemplo.com/dados"),
        (carla, d(13), 3, "Reunião da equipe", "Reunião de diagnóstico e definição do problema.", 1.5, None),
        (ana, d(13), 3, "Coordenação/gestão", "Conduziu a reunião e consolidou o diagnóstico.", 1.5, None),
        (bruno, d(7), 4, "Design/prototipação", "Rascunhou o protótipo da solução em papel.", 3.0, None),
        (carla, d(6), 4, "Apresentação/pitch", "Montou os slides da proposta de valor.", 2.0, None),
        (ana, d(3), 4, "Reunião da equipe", "Reunião para escolher a solução.", 1.0, None),
    ]  # Diego tem só 2 registros antigos, para o painel mostrar o alerta de inatividade
    for m, data, sem, tipo, desc, h, link in contribs:
        app.ex("""INSERT INTO contribuicoes(membro_id, data, semana, tipo, descricao, horas, link, criado_em)
                  VALUES (?,?,?,?,?,?,?,?)""", (m, data, sem, tipo, desc, h, link, data))

    app.ex("""INSERT INTO diario(data, tipo, local, participantes, pessoas_ouvidas, relato, aprendizados, autor_id)
              VALUES (?,?,?,?,?,?,?,?)""",
           (d(21), "Visita", "Feira do bairro", "Carla Dias, Diego Rocha", "3 feirantes e 2 clientes",
            "Conversamos com feirantes sobre o movimento e as dificuldades do dia a dia.",
            "Reclamam da falta de divulgação e de formas de pagamento digital.", carla))
    app.ex("""INSERT INTO diario(data, tipo, local, participantes, pessoas_ouvidas, relato, aprendizados, autor_id)
              VALUES (?,?,?,?,?,?,?,?)""",
           (d(15), "Entrevista", "Chamada de vídeo", "Ana Souza, Bruno Lima", "Presidente da associação",
            "Entrevista sobre a organização da feira e o público atendido.",
            "A associação tem interesse em apoio para divulgação.", ana))

    for sem, status, resp in [(1, "Concluída", ana), (2, "Concluída", carla), (3, "Concluída", bruno),
                              (4, "Em andamento", ana)]:
        app.ex("UPDATE tarefas SET status=?, responsavel_id=? WHERE semana=?", (status, resp, sem))

    respostas = {  # Diego tem poucas contribuições: os colegas marcam que participou pouco
        (ana, bruno): "participou", (ana, carla): "participou", (ana, diego): "pouco",
        (bruno, ana): "participou", (bruno, carla): "participou", (bruno, diego): "pouco",
        (carla, ana): "participou", (carla, bruno): "participou", (carla, diego): "nao",
        (diego, ana): "participou", (diego, bruno): "participou", (diego, carla): "participou",
    }
    for (avaliador, avaliado), resposta in respostas.items():
        app.ex("""INSERT INTO participacoes(rodada, avaliador_id, avaliado_id, resposta, comentario)
                  VALUES (?,?,?,?,?)""", (app.RODADAS[0], avaliador, avaliado, resposta, ""))
    print("Dados de exemplo criados. Entre com qualquer integrante (ex.: Ana Souza) e PIN 1234.")


main()
