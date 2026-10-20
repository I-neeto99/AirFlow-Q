# AirFlow-Q

**Monitor de Qualidade do Ar com Alerta de Saúde Pública**

Pipeline de integração e persistência de dados que consome uma API pública de
qualidade do ar, converte as concentrações de poluentes no Índice de Qualidade
do Ar oficial brasileiro, classifica o risco à saúde e persiste o resultado em
banco de dados Oracle.

O nome reúne as duas pontas do projeto: o fluxo de dados atmosféricos que
atravessa o pipeline, e a qualidade (*quality*) do ar que ele mede.

Desenvolvido como Checkpoint 5 da disciplina Computational Thinking using
Python, do curso de Análise e Desenvolvimento de Sistemas da FIAP.

---

## O problema

A poluição atmosférica não afeta todo mundo da mesma forma. Pessoas com asma e
outras doenças respiratórias crônicas, cardiopatas, idosos e crianças pequenas
são os grupos que sentem primeiro, e com mais intensidade, a piora da qualidade
do ar. Para essas pessoas, saber com antecedência que o ar vai estar ruim é a
diferença entre ajustar a rotina e ter uma crise.

Os dados existem e são públicos. O problema é o formato: eles são publicados
como concentrações horárias em microgramas por metro cúbico, separadas por
poluente. Um valor como "PM2.5 de 47,5 µg/m³" não comunica nada a quem precisa
tomar uma decisão. Para virar informação útil, esse número precisa ser agregado
no tempo, convertido em um índice comparável entre poluentes diferentes e
traduzido em uma recomendação prática.

O AirFlow-Q faz exatamente esse caminho: parte do dado bruto da atmosfera e
chega em uma frase que a pessoa consegue usar.

---

## Visão geral da solução

```
    API pública            Processamento              Banco de dados
   (Open-Meteo)             em memória                 (Oracle SQL)

   requisições GET   -->   3 transformações   -->   INSERT transacional
   com requests            com Python puro          com oracledb
```

| Etapa | Responsabilidade | Biblioteca |
|---|---|---|
| Extração | Buscar as medições horárias de poluentes de 10 capitais | `requests` |
| Transformação | Agregar, calcular o índice e classificar o risco | padrão |
| Carga | Gravar os resultados com controle de transação | `oracledb` |

Cada cidade gera uma requisição HTTP independente. Essa escolha é deliberada:
se a coleta de uma cidade falhar, as demais continuam, e o pipeline conclui com
os dados que conseguiu obter em vez de abortar por inteiro.

---

## A API consumida

**URL base:** `https://air-quality-api.open-meteo.com/v1/air-quality`

A Open-Meteo Air Quality API disponibiliza previsões de concentração de
poluentes atmosféricos a partir do modelo CAMS, do serviço europeu Copernicus.

| Característica | Valor |
|---|---|
| Autenticação | Nenhuma. Não exige cadastro nem chave de acesso |
| Custo | Gratuita para uso não comercial |
| Formato | JSON |
| Granularidade | Horária |
| Poluentes utilizados | PM2.5, PM10, ozônio e dióxido de nitrogênio |
| Horizonte | 5 dias de previsão |

### Por que esta API

1. **Ausência de autenticação complexa**, conforme exigido pelo enunciado.
2. **Granularidade horária**, que permite aplicar agregações estatísticas reais
   sobre os dados em vez de apenas reformatar valores já consolidados.
3. **Múltiplos poluentes por requisição**, o que viabiliza o cálculo de um
   índice composto com um poluente crítico identificado.
4. **Relevância do dado**, por se tratar de informação de saúde pública com
   norma técnica brasileira associada.

### Estrutura da resposta

```json
{
  "latitude": -23.55,
  "longitude": -46.63,
  "hourly": {
    "time": ["2026-10-19T00:00", "2026-10-19T01:00", "..."],
    "pm2_5": [12.6, 13.1, "..."],
    "pm10": [15.0, 16.2, "..."],
    "ozone": [48.0, 45.3, "..."],
    "nitrogen_dioxide": [21.4, 19.8, "..."]
  }
}
```

### Tratamento de erros

O consumo da API trata explicitamente os cenários abaixo, sem permitir que
nenhuma exceção interrompa a execução:

| Situação | Comportamento |
|---|---|
| HTTP 200 | Processa a resposta |
| HTTP 404 | Informa endpoint não encontrado e segue para a próxima cidade |
| HTTP 429 | Informa excesso de requisições |
| HTTP 5xx | Informa falha no servidor da API |
| Outros status | Informa resposta inesperada |
| Timeout | Informa o limite de tempo excedido |
| Falha de conexão | Informa indisponibilidade de rede |
| JSON inválido | Informa resposta fora do formato esperado |

---

## Regras de negócio e transformações

O pipeline aplica três operações de processamento sobre os dados em memória,
antes de qualquer gravação.

### Transformação 1 — Agregação estatística e padronização

As séries horárias retornadas pela API são agrupadas por dia e reduzidas a
indicadores diários por poluente. Nesta etapa também ocorre a limpeza dos
dados: as datas no formato ISO 8601 são convertidas para o tipo `date` do
Python, medições ausentes são descartadas dos cálculos, e dias sem nenhuma
medição válida de material particulado são removidos, por não permitirem um
índice representativo.

### Transformação 2 — Cálculo do Índice de Qualidade do Ar

As concentrações são convertidas em um índice numérico de 0 a 400 por
interpolação linear dentro das faixas da Resolução CONAMA nº 491/2018:

```
I = I_min + (I_max - I_min) × (C - C_min) / (C_max - C_min)
```

Faixas de concentração, em µg/m³:

| Índice | MP2,5 (24h) | MP10 (24h) | O3 (8h) | NO2 (1h) |
|---|---|---|---|---|
| 0 – 40 | 0 – 25 | 0 – 50 | 0 – 100 | 0 – 200 |
| 41 – 80 | 25 – 50 | 50 – 100 | 100 – 130 | 200 – 240 |
| 81 – 120 | 50 – 75 | 100 – 150 | 130 – 160 | 240 – 320 |
| 121 – 200 | 75 – 125 | 150 – 250 | 160 – 200 | 320 – 1130 |
| 201 – 400 | 125 – 300 | 250 – 600 | 200 – 800 | 1130 – 3750 |

O índice do dia é o **pior** entre os quatro poluentes, e o poluente que o
originou é registrado como poluente crítico. Esse critério também vem da norma:
a qualidade do ar é determinada pelo contaminante em pior situação, não por uma
média entre eles.

### Transformação 3 — Classificação e recomendação de saúde

| Índice | Classificação | Recomendação |
|---|---|---|
| 0 – 40 | BOA | Nenhuma restrição para atividades ao ar livre |
| 41 – 80 | MODERADA | Grupos sensíveis podem apresentar tosse seca e cansaço |
| 81 – 120 | RUIM | Grupos sensíveis devem evitar exercício ao ar livre |
| 121 – 200 | MUITO RUIM | Toda a população deve permanecer em ambiente fechado |
| 201 – 400 | PÉSSIMA | Risco sério de crises respiratórias e cardiovasculares |

---

## Nota metodológica sobre o ozônio

A CONAMA define cada poluente sobre um período de referência diferente: média
de 24 horas para material particulado, média de 8 horas para ozônio e máxima de
1 hora para dióxido de nitrogênio.

A primeira versão deste pipeline usava o pico horário de ozônio do dia como
entrada do índice. A análise dos resultados mostrou que isso produzia um viés
sistemático: o ozônio aparecia como poluente crítico em 45 dos 50 registros
coletados, e cidades com PM2.5 abaixo de 5 µg/m³, ou seja, com ar
particuladamente limpo, eram classificadas como RUIM.

A causa era uma incompatibilidade de métrica. O pico de uma hora é sempre
substancialmente maior que a média de oito horas, de modo que comparar o pico
contra uma faixa definida para a média superestima o índice.

A versão atual calcula a maior média móvel de 8 horas consecutivas do dia, que
é a métrica prevista na norma. O efeito da correção, sobre os mesmos dados:

| Registro | Antes | Depois | Crítico |
|---|---|---|---|
| Belo Horizonte, PM2.5 de 4,7 µg/m³ | 82 — RUIM | 61 — MODERADA | O3 |
| São Paulo, 19/10 | 104 — RUIM | 74 — MODERADA | O3 |
| São Paulo, 22/10 | 91 — RUIM | 59 — MODERADA | O3 |
| Manaus, 20/10 | 157 — MUITO RUIM | 116 — RUIM | O3 |
| Manaus, 19/10 | 140 — MUITO RUIM | 140 — MUITO RUIM | PM2.5 |
| Manaus, 21/10 | 77 — MODERADA | 77 — MODERADA | PM2.5 |
| São Paulo, 23/10 | 40 — BOA | 40 — BOA | PM2.5 |

Alertas de saúde emitidos no período caíram de 8 para 4. Os registros em que o
material particulado era o poluente crítico permaneceram idênticos, o que
confirma que a correção atingiu apenas o cálculo do ozônio.

O ozônio continua sendo o poluente crítico na maioria das cidades, agora em
faixas BOA e MODERADA. Esse é um resultado esperado: em centros urbanos com
material particulado controlado, o ozônio troposférico costuma ser o poluente
limitante.

---

## Resultados obtidos

Execução sobre 10 capitais, com 5 dias de previsão, totalizando 50 registros.

O pipeline identificou, sem qualquer parametrização específica, o episódio de
material particulado em Manaus durante o período de queimadas na Amazônia:

```
CIDADE        DATA          PM2.5    PM10    IQA   CRITICO   CLASSIFICACAO
Manaus        19/10/2026     86.9    89.6    140     PM2.5    MUITO RUIM
```

Nesse registro o poluente crítico é o PM2.5, e não o ozônio, o que é coerente
com a origem do fenômeno. Nas demais capitais, o material particulado
permaneceu em níveis baixos no mesmo período.

---

## Estrutura do banco de dados

### Script de criação

```sql
CREATE TABLE TB_QUALIDADE_AR (
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
);

CREATE SEQUENCE SEQ_QUALIDADE_AR START WITH 1 INCREMENT BY 1 NOCACHE;
```

### Dicionário de dados

| Coluna | Tipo | Descrição | Restrição |
|---|---|---|---|
| ID_MEDICAO | NUMBER(10) | Identificador do registro, gerado por sequence | PK, NOT NULL |
| CIDADE | VARCHAR2(60) | Nome da capital monitorada | NOT NULL, UK |
| UF | VARCHAR2(2) | Sigla da unidade federativa | NOT NULL |
| DATA_MEDICAO | DATE | Dia a que as medições se referem | NOT NULL, UK |
| PM25_MEDIO | NUMBER(8,2) | Média diária de material particulado 2,5 µm, em µg/m³ | — |
| PM25_MAXIMO | NUMBER(8,2) | Máxima horária de PM2.5 no dia, em µg/m³ | — |
| PM10_MEDIO | NUMBER(8,2) | Média diária de material particulado 10 µm, em µg/m³ | — |
| PM10_MAXIMO | NUMBER(8,2) | Máxima horária de PM10 no dia, em µg/m³ | — |
| O3_MAXIMO | NUMBER(8,2) | Maior média móvel de 8 horas de ozônio, em µg/m³ | — |
| NO2_MAXIMO | NUMBER(8,2) | Máxima horária de dióxido de nitrogênio, em µg/m³ | — |
| INDICE_IQA | NUMBER(5) | Índice de Qualidade do Ar do dia, de 0 a 400 | — |
| POLUENTE_CRITICO | VARCHAR2(10) | Poluente que determinou o índice | — |
| CLASSIFICACAO | VARCHAR2(20) | BOA, MODERADA, RUIM, MUITO RUIM ou PÉSSIMA | NOT NULL |
| RECOMENDACAO | VARCHAR2(200) | Orientação de saúde associada à classificação | — |
| DT_CARGA | DATE | Momento da gravação do registro | NOT NULL, default SYSDATE |

### Controle transacional e reexecução

A gravação ocorre em uma única transação. Antes dos `INSERT`, o pipeline remove
as linhas correspondentes às mesmas chaves de cidade e data que serão
gravadas. O `commit()` só é executado se todas as operações forem bem
sucedidas; qualquer erro dispara `rollback()`, deixando a tabela no estado
anterior.

Esse desenho torna o pipeline idempotente: reexecutar o programa atualiza os
dados existentes em vez de duplicá-los. A tabela e a sequence também são
criadas apenas se ainda não existirem, de modo que a primeira execução e as
seguintes usam o mesmo comando.

---

## Como executar

### 1. Instalar as dependências

```bash
python -m pip install requests oracledb
```

A biblioteca `oracledb` opera em modo thin por padrão, o que dispensa a
instalação do Oracle Instant Client.

### 2. Executar

```bash
python pipeline_qualidade_ar.py
```

A conexão com o banco da FIAP exige estar na rede da instituição ou com a VPN
ativa.

### 4. Conferir os dados gravados

```sql
SELECT CIDADE, DATA_MEDICAO, INDICE_IQA, POLUENTE_CRITICO, CLASSIFICACAO
  FROM TB_QUALIDADE_AR
 ORDER BY INDICE_IQA DESC;
```

---

## Estrutura do projeto

| Arquivo | Descrição |
|---|---|
| `pipeline_qualidade_ar.py` | Código-fonte completo do pipeline |
| `README.md` | Esta documentação |
| `.env.exemplo` | Modelo de configuração das credenciais |
| `.gitignore` | Impede o versionamento do `.env` e de artefatos do Python |

O código está organizado em quatro camadas, separadas por função: extração,
transformação, persistência e apresentação. As funções de transformação não
dependem de rede nem de banco de dados, o que permite testá-las isoladamente.

---

## Limitações conhecidas

- Os dados da Open-Meteo são previsões de modelo, não leituras de estações de
  monitoramento em solo. São adequados para antecipação e tendência, mas não
  substituem a medição oficial de uma rede como a da CETESB.
- A norma brasileira define o material particulado sobre a média de 24 horas.
  O pipeline usa a média do dia civil, que é a aproximação disponível a partir
  da série horária fornecida pela API.
- A cobertura está limitada a 10 capitais, definidas em uma constante no
  início do script. Ampliar a lista não exige qualquer outra alteração no
  código.
- O horizonte de previsão é de 5 dias, limite adequado à confiabilidade do
  modelo de origem.

---

## Autores

| Nome | RM |
|---|---|
| Italo Neto | 572912 |
| Tárik Moussa Alma | 571411 |
| Fabricio Aquiles Sales da Silva | 570985 |

---

## Referências

- BRASIL. Conselho Nacional do Meio Ambiente. **Resolução CONAMA nº 491, de 19
  de novembro de 2018.** Dispõe sobre padrões de qualidade do ar.
- OPEN-METEO. **Air Quality API Documentation.** https://open-meteo.com/en/docs/air-quality-api
- ORACLE. **python-oracledb Documentation.** https://python-oracledb.readthedocs.io
