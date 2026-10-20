Monitor de Qualidade do Ar com Alerta de Saúde Pública
Pipeline de integração e persistência de dados em Python que consome uma API pública de qualidade do ar, converte as concentrações de poluentes no Índice de Qualidade do Ar oficial brasileiro e persiste o resultado em banco Oracle.

FIAP — Checkpoint 5 — Computational Thinking using Python

Problema
Grupos sensíveis — asmáticos, idosos, crianças e cardiopatas — são os mais afetados pela poluição atmosférica, mas os dados de poluentes são publicados em concentrações horárias de microgramas por metro cúbico, que nada comunicam à população. Esta aplicação transforma esse dado cru em uma classificação de risco e em uma recomendação de saúde objetiva.

Arquitetura
API pública  ──▶  transformações em memória  ──▶  Oracle SQL
(requests)        (3 operações)                   (oracledb)
Etapa	Biblioteca	O que faz
Extração	requests	GET na Open-Meteo Air Quality, uma requisição por cidade
Transformação	padrão	Agregação diária, cálculo do IQA e classificação de risco
Carga	oracledb	INSERT transacional com commit() e rollback()
API consumida
URL base: https://air-quality-api.open-meteo.com/v1/air-quality
Autenticação: nenhuma, gratuita e sem cadastro
Poluentes: PM2.5, PM10, ozônio e dióxido de nitrogênio
Cobertura: 10 capitais brasileiras, 5 dias de previsão
Transformações aplicadas
Agregação estatística — converte as séries horárias em registros diários, com média e máxima de cada poluente, e padroniza a data.
Cálculo do Índice de Qualidade do Ar — converte cada concentração em um índice de 0 a 400 por interpolação linear, conforme a Resolução CONAMA 491/2018, e adota o pior poluente como índice do dia.
Classificação e recomendação — enquadra o índice nas faixas BOA, MODERADA, RUIM, MUITO RUIM ou PÉSSIMA e associa a recomendação de saúde.
Como executar
1. Instalar as dependências
pip install requests oracledb
2. Configurar o acesso ao banco
Copie .env.exemplo para .env e preencha com suas credenciais:

ORACLE_USER=rm123456
ORACLE_PASSWORD=sua_senha
ORACLE_DSN=oracle.fiap.com.br:1521/ORCL
O arquivo .env é ignorado pelo Git e nunca é versionado. Sem ele, a aplicação pede usuário e senha pelo teclado durante a execução.

3. Executar
python pipeline_qualidade_ar.py
A tabela e a sequence são criadas automaticamente na primeira execução. O pipeline pode ser reexecutado sem gerar registros duplicados.

A conexão com o Oracle da FIAP exige estar na rede da faculdade ou com a VPN ativa.

Estrutura do banco
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
Arquivos
Arquivo	Descrição
pipeline_qualidade_ar.py	Código-fonte completo do pipeline
.env.exemplo	Modelo de configuração das credenciais
.gitignore	Impede o versionamento do .env
Referência
Resolução CONAMA nº 491, de 19 de novembro de 2018 — dispõe sobre padrões de qualidade do ar.