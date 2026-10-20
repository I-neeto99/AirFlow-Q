import os
import sys
import getpass
from datetime import datetime

from rich.markup import escape
from rich.console import Console
console = Console()
from rich.table import Table


import requests
import oracledb


ARQUIVO_ENV = ".env"
ORACLE_DSN_PADRAO = "oracle.fiap.com.br:1521/ORCL"

# CONFIGURACOES

URL_BASE_API = "https://air-quality-api.open-meteo.com/v1/air-quality"
POLUENTES_CONSULTADOS = "pm2_5,pm10,ozone,nitrogen_dioxide"
DIAS_DE_PREVISAO = 5
TIMEOUT_REQUISICAO = 20
FUSO_HORARIO = "America/Sao_Paulo"

NOME_TABELA = "TB_QUALIDADE_AR"
NOME_SEQUENCE = "SEQ_QUALIDADE_AR"

CIDADES_MONITORADAS = [
    {"cidade": "Sao Paulo",      "uf": "SP", "latitude": -23.5505, "longitude": -46.6333},
    {"cidade": "Rio de Janeiro", "uf": "RJ", "latitude": -22.9068, "longitude": -43.1729},
    {"cidade": "Belo Horizonte", "uf": "MG", "latitude": -19.9167, "longitude": -43.9345},
    {"cidade": "Brasilia",       "uf": "DF", "latitude": -15.7939, "longitude": -47.8828},
    {"cidade": "Curitiba",       "uf": "PR", "latitude": -25.4284, "longitude": -49.2733},
    {"cidade": "Porto Alegre",   "uf": "RS", "latitude": -30.0346, "longitude": -51.2177},
    {"cidade": "Salvador",       "uf": "BA", "latitude": -12.9777, "longitude": -38.5016},
    {"cidade": "Recife",         "uf": "PE", "latitude":  -8.0476, "longitude": -34.8770},
    {"cidade": "Fortaleza",      "uf": "CE", "latitude":  -3.7319, "longitude": -38.5267},
    {"cidade": "Manaus",         "uf": "AM", "latitude":  -3.1190, "longitude": -60.0217},
]

# Faixas da Resolucao CONAMA 491/2018, no formato
# (concentracao_min, concentracao_max, indice_min, indice_max)
FAIXAS_POR_POLUENTE = {
    "PM2.5": [(0, 25, 0, 40), (25, 50, 41, 80), (50, 75, 81, 120),
              (75, 125, 121, 200), (125, 300, 201, 400)],
    "PM10":  [(0, 50, 0, 40), (50, 100, 41, 80), (100, 150, 81, 120),
              (150, 250, 121, 200), (250, 600, 201, 400)],
    "O3":    [(0, 100, 0, 40), (100, 130, 41, 80), (130, 160, 81, 120),
              (160, 200, 121, 200), (200, 800, 201, 400)],
    "NO2":   [(0, 200, 0, 40), (200, 240, 41, 80), (240, 320, 81, 120),
              (320, 1130, 121, 200), (1130, 3750, 201, 400)],
}

FAIXAS_DE_CLASSIFICACAO = [
    (0, 40, "BOA",
     "Qualidade do ar satisfatoria. Nenhuma restricao para atividades ao ar livre."),
    (41, 80, "MODERADA",
     "Grupos sensiveis podem apresentar tosse seca e cansaco. Reduzir esforco prolongado."),
    (81, 120, "RUIM",
     "Grupos sensiveis podem ter falta de ar e chiado. Evitar exercicio ao ar livre."),
    (121, 200, "MUITO RUIM",
     "Toda a populacao pode apresentar sintomas respiratorios. Permanecer em ambiente fechado."),
    (201, 400, "PESSIMA",
     "Risco serio de crises respiratorias e cardiovasculares. Evitar qualquer exposicao."),
]

# EXTRACAO - CONSUMO DA API

def buscar_qualidade_ar(cidade):
    """Busca as medicoes de poluentes de uma cidade. Retorna o JSON ou None"""
    parametros = {
        "latitude": cidade["latitude"],
        "longitude": cidade["longitude"],
        "hourly": POLUENTES_CONSULTADOS,
        "timezone": FUSO_HORARIO,
        "forecast_days": DIAS_DE_PREVISAO,
    }

      

def buscar_qualidade_ar(cidade):
    """Busca as medicoes de poluentes de uma cidade. Retorna o JSON ou None"""
    parametros = {
        "latitude": cidade["latitude"],
        "longitude": cidade["longitude"],
        "hourly": POLUENTES_CONSULTADOS,
        "timezone": FUSO_HORARIO,
        "forecast_days": DIAS_DE_PREVISAO,
    }

    try:
        resposta = requests.get(URL_BASE_API, params=parametros,
                                timeout=TIMEOUT_REQUISICAO)

        if resposta.status_code == 200:
            console.print(f"  [green][OK 200][/green] {cidade['cidade']}/{cidade['uf']}: dados recebidos.")
            return resposta.json()

        if resposta.status_code == 404:
            console.print(f"  [red][ERRO 404][/red] {cidade['cidade']}: endpoint nao encontrado.")
        elif resposta.status_code == 429:
            console.print(f"  [yellow][ERRO 429][/yellow] {cidade['cidade']}: limite de requisicoes excedido.")
        elif resposta.status_code >= 500:
            console.print(f"  [red][ERRO {resposta.status_code}][/red] {cidade['cidade']}: falha no servidor da API.")
        else:
            console.print(f"  [red][ERRO {resposta.status_code}][/red] {cidade['cidade']}: resposta inesperada.")
        return None

    except requests.exceptions.Timeout:
        console.print(f"  [yellow][TIMEOUT][/yellow] {cidade['cidade']}: a API nao respondeu em {TIMEOUT_REQUISICAO}s.")
    except requests.exceptions.ConnectionError:
        console.print(f"  [yellow][SEM CONEXAO][/yellow] {cidade['cidade']}: nao foi possivel alcancar a API.")
    except requests.exceptions.RequestException as erro:
        console.print(f"  [red][FALHA NA REQUISICAO][/red] {cidade['cidade']}: {escape(str(erro))}")
    except ValueError:
        console.print(f"  [red][JSON INVALIDO][/red] {cidade['cidade']}: resposta fora do formato esperado.")

    return None

# TRANSFORMACAO - PROCESSAMENTO EM MEMORIA

def _media(valores):
    validos = [v for v in valores if v is not None]
    return round(sum(validos) / len(validos), 2) if validos else None


def _maximo(valores):
    validos = [v for v in valores if v is not None]
    return round(max(validos), 2) if validos else None


def _maxima_media_8h(valores):
    """
    Maior media movel de 8 horas consecutivas do dia.

    A CONAMA define a faixa do ozonio sobre a media de 8h, nao sobre o pico
    horario. Usar o pico superestimaria o indice de forma sistematica.
    """
    melhor = None

    for inicio in range(len(valores) - 7):
        janela = [v for v in valores[inicio:inicio + 8] if v is not None]
        if len(janela) < 8:
            continue
        media = sum(janela) / 8
        if melhor is None or media > melhor:
            melhor = media

    return round(melhor, 2) if melhor is not None else None


def agregar_medicoes_por_dia(json_api, cidade):
    """
    Transformacao 1: converte as series horarias da API em registros diarios,
    com media e maxima de cada poluente, e padroniza a data
    """
    bloco_horario = json_api.get("hourly", {})
    horarios = bloco_horario.get("time", [])

    if not horarios:
        console.print(f"  [red][SEM DADOS][/red] {cidade['cidade']}: a API nao retornou medicoes.")
        return []

    indices_por_dia = {}
    for posicao, horario in enumerate(horarios):
        dia = horario.split("T")[0]
        indices_por_dia.setdefault(dia, []).append(posicao)

    registros_diarios = []

    for dia, indices in sorted(indices_por_dia.items()):
        def valores_do_dia(poluente):
            serie = bloco_horario.get(poluente, [])
            return [serie[i] for i in indices if i < len(serie)]

        pm25 = valores_do_dia("pm2_5")
        pm10 = valores_do_dia("pm10")
        ozonio = valores_do_dia("ozone")
        dioxido_nitrogenio = valores_do_dia("nitrogen_dioxide")

        registro = {
            "cidade": cidade["cidade"],
            "uf": cidade["uf"],
            "data_medicao": datetime.strptime(dia, "%Y-%m-%d").date(),
            "pm25_medio": _media(pm25),
            "pm25_maximo": _maximo(pm25),
            "pm10_medio": _media(pm10),
            "pm10_maximo": _maximo(pm10),
            "o3_maximo": _maxima_media_8h(ozonio),
            "no2_maximo": _maximo(dioxido_nitrogenio),
        }

        # Sem material particulado o indice deixa de ser representativo
        if registro["pm25_medio"] is None and registro["pm10_medio"] is None:
            continue

        registros_diarios.append(registro)

    return registros_diarios


def calcular_indice_do_poluente(concentracao, faixas):
    """Converte uma concentracao em indice de 0 a 400 por interpolacao linear"""
    if concentracao is None:
        return None

    for conc_min, conc_max, indice_min, indice_max in faixas:
        if conc_min <= concentracao <= conc_max:
            proporcao = (concentracao - conc_min) / (conc_max - conc_min)
            return int(round(indice_min + (indice_max - indice_min) * proporcao))

    return 400


def calcular_iqa(registro):
    """
    Transformacao 2: calcula o indice de cada poluente e adota o pior deles
    como indice do dia, conforme a CONAMA 491/2018.

    A norma usa media de 24h para material particulado, 8h para ozonio e 1h
    para dioxido de nitrogenio. A partir da serie horaria da API, usamos a
    media diaria para PM, a maior media movel de 8h para O3 e a maxima
    diaria para NO2
    """
    indices = {
        "PM2.5": calcular_indice_do_poluente(registro["pm25_medio"], FAIXAS_POR_POLUENTE["PM2.5"]),
        "PM10": calcular_indice_do_poluente(registro["pm10_medio"], FAIXAS_POR_POLUENTE["PM10"]),
        "O3": calcular_indice_do_poluente(registro["o3_maximo"], FAIXAS_POR_POLUENTE["O3"]),
        "NO2": calcular_indice_do_poluente(registro["no2_maximo"], FAIXAS_POR_POLUENTE["NO2"]),
    }

    validos = {poluente: indice for poluente, indice in indices.items() if indice is not None}
    if not validos:
        return None, None

    poluente_critico = max(validos, key=validos.get)
    return validos[poluente_critico], poluente_critico


def classificar_qualidade(indice):
    """Transformacao 3: enquadra o indice em uma faixa e devolve a recomendacao"""
    if indice is None:
        return "INDISPONIVEL", "Nao ha dados suficientes para avaliacao."

    for limite_min, limite_max, classificacao, recomendacao in FAIXAS_DE_CLASSIFICACAO:
        if limite_min <= indice <= limite_max:
            return classificacao, recomendacao

    return "PESSIMA", FAIXAS_DE_CLASSIFICACAO[-1][3]


def processar_dados(json_api, cidade):
    """Aplica as tres transformacoes e devolve os registros prontos para carga"""
    registros = agregar_medicoes_por_dia(json_api, cidade)

    for registro in registros:
        indice, poluente_critico = calcular_iqa(registro)
        classificacao, recomendacao = classificar_qualidade(indice)

        registro["indice_iqa"] = indice
        registro["poluente_critico"] = poluente_critico
        registro["classificacao"] = classificacao
        registro["recomendacao"] = recomendacao

    return registros

# PERSISTENCIA - BANCO DE DADOS ORACLE

DDL_TABELA = f"""
CREATE TABLE {NOME_TABELA} (
    ID_MEDICAO        NUMBER(10)     NOT NULL,
    CIDADE            VARCHAR2(60)   NOT NULL,
    UF                VARCHAR2(2)    NOT NULL,
    DATA_MEDICAO      DATE           NOT NULL,
    PM25_MEDIO        NUMBER(8,2),
    PM25_MAXIMO       NUMBER(8,2),
    PM10_MEDIO        NUMBER(8,2),
    PM10_MAXIMO       NUMBER(8,2),
    O3_MAXIMO         NUMBER(8,2),
    NO2_MAXIMO        NUMBER(8,2),
    INDICE_IQA        NUMBER(5),
    POLUENTE_CRITICO  VARCHAR2(10),
    CLASSIFICACAO     VARCHAR2(20)   NOT NULL,
    RECOMENDACAO      VARCHAR2(200),
    DT_CARGA          DATE DEFAULT SYSDATE NOT NULL,
    CONSTRAINT PK_QUALIDADE_AR PRIMARY KEY (ID_MEDICAO),
    CONSTRAINT UK_QUALIDADE_AR UNIQUE (CIDADE, DATA_MEDICAO)
)
"""

DDL_SEQUENCE = f"CREATE SEQUENCE {NOME_SEQUENCE} START WITH 1 INCREMENT BY 1 NOCACHE"

SQL_DELETE = f"""
DELETE FROM {NOME_TABELA}
 WHERE CIDADE = :cidade
   AND DATA_MEDICAO = :data_medicao
"""

SQL_INSERT = f"""
INSERT INTO {NOME_TABELA} (
    ID_MEDICAO, CIDADE, UF, DATA_MEDICAO,
    PM25_MEDIO, PM25_MAXIMO, PM10_MEDIO, PM10_MAXIMO,
    O3_MAXIMO, NO2_MAXIMO,
    INDICE_IQA, POLUENTE_CRITICO, CLASSIFICACAO, RECOMENDACAO
) VALUES (
    {NOME_SEQUENCE}.NEXTVAL, :cidade, :uf, :data_medicao,
    :pm25_medio, :pm25_maximo, :pm10_medio, :pm10_maximo,
    :o3_maximo, :no2_maximo,
    :indice_iqa, :poluente_critico, :classificacao, :recomendacao
)
"""


def carregar_variaveis_de_ambiente(caminho=ARQUIVO_ENV):
    """
    Carrega as variaveis definidas no arquivo .env, quando ele existe

    Usa setdefault para que variaveis ja definidas no sistema tenham
    prioridade sobre o arquivo
    """
    arquivo_env = os.path.join(os.path.dirname(os.path.abspath(__file__)), caminho)

    if not os.path.isfile(arquivo_env):
        return False

    with open(arquivo_env, encoding="utf-8") as arquivo:
        for linha in arquivo:
            linha = linha.strip()
            if not linha or linha.startswith("#") or "=" not in linha:
                continue
            chave, valor = linha.split("=", 1)
            os.environ.setdefault(chave.strip(), valor.strip().strip("\"'"))

    return True


def obter_credenciais():
    """Le as credenciais do ambiente ou do .env e pede ao usuario o que faltar"""
    if carregar_variaveis_de_ambiente():
        print(f"  [CONFIG] Variaveis carregadas de {ARQUIVO_ENV}.")

    usuario = os.getenv("ORACLE_USER", "").strip()
    senha = os.getenv("ORACLE_PASSWORD", "").strip()
    dsn = os.getenv("ORACLE_DSN", "").strip() or ORACLE_DSN_PADRAO

    if not usuario:
        print("  [CONFIG] ORACLE_USER nao definido.")
        usuario = input("  Usuario Oracle (ex.: rm123456): ").strip()

    if not senha:
        print("  [CONFIG] ORACLE_PASSWORD nao definido.")
        senha = getpass.getpass("  Senha Oracle: ")

    return usuario, senha, dsn


def conectar_oracle():
    """Abre a conexao com o Oracle. Retorna a conexao ou None em caso de falha"""
    usuario, senha, dsn = obter_credenciais()

    try:
        conexao = oracledb.connect(user=usuario, password=senha, dsn=dsn)
        print(f"  [OK] Conectado ao Oracle em {dsn} como {usuario}.")
        return conexao
    except oracledb.DatabaseError as erro:
        (detalhe,) = erro.args
        print(f"  [FALHA NA CONEXAO] ORA-{detalhe.code}: {detalhe.message.strip()}")
        print("  Verifique as credenciais e se a VPN da FIAP esta ativa.")
        return None


def criar_estrutura(conexao):
    """Cria a tabela e a sequence, ignorando-as caso ja existam"""
    with conexao.cursor() as cursor:
        for nome_objeto, comando in [(NOME_TABELA, DDL_TABELA),
                                     (NOME_SEQUENCE, DDL_SEQUENCE)]:
            try:
                cursor.execute(comando)
                print(f"  [CRIADO] {nome_objeto}.")
            except oracledb.DatabaseError as erro:
                (detalhe,) = erro.args
                if detalhe.code != 955:
                    raise
                print(f"  [JA EXISTE] {nome_objeto}, criacao ignorada.")


def persistir_registros(conexao, registros):
    """
    Grava os registros em uma unica transacao, com commit em caso de sucesso e
    rollback em caso de falha. O delete previo torna o pipeline reexecutavel
    sem duplicar dados
    """
    if not registros:
        print("  [AVISO] Nenhum registro para gravar.")
        return 0

    chaves = [{"cidade": r["cidade"], "data_medicao": r["data_medicao"]}
              for r in registros]

    try:
        with conexao.cursor() as cursor:
            cursor.executemany(SQL_DELETE, chaves)
            removidos = cursor.rowcount

            cursor.executemany(SQL_INSERT, registros)
            inseridos = cursor.rowcount

        conexao.commit()
        print(f"  [COMMIT] {inseridos} registros gravados ({removidos} substituidos).")
        return inseridos

    except oracledb.DatabaseError as erro:
        conexao.rollback()
        (detalhe,) = erro.args
        print(f"  [ROLLBACK] Transacao desfeita. ORA-{detalhe.code}: "
              f"{detalhe.message.strip()}")
        return 0

# RELATORIO

def exibir_relatorio(registros):
    """Imprime o resumo das medicoes e os alertas de saude do periodo"""
    if not registros:
        return

    print("\n" + "=" * 78)
    print("RESUMO DA QUALIDADE DO AR")
    print("=" * 78)
    print(f"{'CIDADE':<18}{'DATA':<12}{'PM2.5':>8}{'PM10':>8}"
          f"{'IQA':>6}{'CRITICO':>10}  CLASSIFICACAO")
    print("-" * 78)

    for r in registros:
        pm25 = f"{r['pm25_medio']:.1f}" if r["pm25_medio"] is not None else "-"
        pm10 = f"{r['pm10_medio']:.1f}" if r["pm10_medio"] is not None else "-"
        iqa = r["indice_iqa"] if r["indice_iqa"] is not None else "-"

        print(f"{r['cidade']:<18}"
              f"{r['data_medicao'].strftime('%d/%m/%Y'):<12}"
              f"{pm25:>8}{pm10:>8}{iqa:>6}{r['poluente_critico'] or '-':>10}"
              f"  {r['classificacao']}")

    print("-" * 78)

    alertas = [r for r in registros
               if r["classificacao"] in ("RUIM", "MUITO RUIM", "PESSIMA")]

    if alertas:
        print(f"\nALERTAS DE SAUDE ({len(alertas)} ocorrencias):")
        for r in alertas:
            print(f"  - {r['cidade']}/{r['uf']} em "
                  f"{r['data_medicao'].strftime('%d/%m/%Y')} "
                  f"[{r['classificacao']}]: {r['recomendacao']}")
    else:
        print("\nNenhum alerta de saude no periodo analisado.")

# PIPELINE

def main():
    print("=" * 78)
    print("PIPELINE DE QUALIDADE DO AR - FIAP CHECKPOINT 5")
    print("=" * 78)

    print(f"\n[ETAPA 1/3] Consumindo a API publica ({len(CIDADES_MONITORADAS)} cidades)...")

    todos_os_registros = []
    cidades_com_falha = 0

    for cidade in CIDADES_MONITORADAS:
        json_api = buscar_qualidade_ar(cidade)
        if json_api is None:
            cidades_com_falha += 1
            continue
        todos_os_registros.extend(processar_dados(json_api, cidade))

    print(f"\n[ETAPA 2/3] Transformacoes concluidas: "
          f"{len(todos_os_registros)} registros diarios gerados.")

    if cidades_com_falha:
        print(f"  [AVISO] {cidades_com_falha} cidade(s) ignorada(s) por falha na coleta.")

    if not todos_os_registros:
        print("\nNenhum dado foi obtido. O pipeline sera encerrado.")
        return 1

    exibir_relatorio(todos_os_registros)

    print("\n[ETAPA 3/3] Persistindo no banco Oracle...")

    conexao = conectar_oracle()
    if conexao is None:
        print("\nPipeline encerrado sem gravar os dados.")
        return 1

    try:
        criar_estrutura(conexao)
        gravados = persistir_registros(conexao, todos_os_registros)
    finally:
        conexao.close()
        print("  [OK] Conexao com o banco encerrada.")

    print("\n" + "=" * 78)
    print(f"PIPELINE FINALIZADO. {gravados} registros em {NOME_TABELA}.")
    print("=" * 78)

    return 0 if gravados else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nExecucao interrompida pelo usuario.")
        sys.exit(130)
