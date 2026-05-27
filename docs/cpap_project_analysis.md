# Análise do Projeto CPAP-ResMed

Este documento apresenta uma análise detalhada da arquitetura, funcionalidades e estrutura do projeto **CPAP-ResMed**, projetado para processar e visualizar dados de terapia de aparelhos CPAP (especificamente ResMed AirSense).

## Visão Geral

O projeto é um sistema end-to-end para ingestão, processamento e visualização de dados extraídos de cartões SD de dispositivos CPAP. Ele converte dados médicos brutos no formato binário EDF (European Data Format) para o formato otimizado Parquet, permitindo o armazenamento particionado por paciente, e expõe esses dados através de uma API FastAPI para visualização num dashboard interativo.

## Arquitetura do Sistema

O sistema é dividido em duas camadas principais: **Ingestão** e **Visualização**.

### 1. Ingestão de Dados (`src/ingestion/`)
Responsável por extrair os dados brutos e prepará-los para análise.
- **`processor.py`**: O script principal do pipeline de dados.
  - Utiliza a biblioteca `mne` para ler o arquivo `STR.edf` (que contém estatísticas diárias da terapia).
  - Normaliza os nomes dos pacientes para gerar "slugs" seguros e salvar os dados particionados (`patient_slug=...`).
  - Salva os dados em formato **Parquet** (`pyarrow` e `pandas`), oferecendo uma ingestão incremental que só adiciona novos registros ou permite um `--reset` completo.

### 2. Backend e Visualização (`src/visualization/`)
Responsável por servir os dados tratados para a interface do usuário.
- **`app.py`**: Aplicação backend construída com **FastAPI**.
  - **Endpoints API**:
    - `/api/patients`: Retorna a lista de pacientes únicos disponíveis.
    - `/api/data/{patient}`: Calcula métricas agregadas (uso diário em minutos, média de IAH, fugas, etc.) e pontuação de terapia (myAir Score) para o paciente selecionado, retornando um JSON com KPIs e séries temporais.
  - Serve arquivos estáticos (HTML/CSS/JS) contidos no diretório `static/` (ex: `index.html`).
- **Scripts Alternativos**: Existem `dashboard.py` e `dashboard_pro.py`, que sugerem implementações alternativas ou antigas baseadas em Dash/Plotly para visualização de relatórios.

## Estrutura de Pastas e Dados

- **`/data/cpap_sd/`**: Diretório esperado para os dados brutos copiados dos cartões SD. Organizado com uma subpasta por paciente.
- **`/data/processed/`**: Diretório onde os dados Parquet estruturados são armazenados.
- **`/docs/`**: Contém a documentação técnica, notavelmente `sd_card_structure.md` que explica a estrutura dos dados gerados pelo aparelho CPAP.
- **`skill.md`**: Um documento de contexto contendo o conhecimento clínico fundamental sobre estágios do sono, metas de terapia e métricas ResMed (IAH, Fuga, Horas de Uso).

## Funcionalidades e Regras de Negócio

1. **Multi-Paciente**: O sistema identifica diferentes pastas no diretório de dados SD e particiona os dados no armazenamento Parquet, permitindo que a aplicação sirva múltiplos usuários de forma independente.
2. **Cálculo de Score (myAir) Oficial**: O sistema calcula a pontuação diária de 0 a 100 pontos baseada nas quatro métricas oficiais da ResMed:
   - **Horas de Uso (Até 70 pontos)**: 10 pontos por hora de uso (ex: 2h de uso = 20 pontos), com limite máximo de 70 pontos (7 horas).
   - **Vedação da Máscara (Até 20 pontos)**: Calculado a partir da taxa de fuga de ar em 95% (Leak.95):
     - 0 a 16 L/min: 20 pontos
     - 17 a 54 L/min: 19 a 1 ponto (decresce 1 ponto a cada 2 L/min de acréscimo: $20 - \lceil \frac{\text{fuga} - 16}{2} \rceil$)
     - 55 L/min ou mais: 0 pontos
   - **Colocação/Retirada da Máscara (Até 5 pontos)**: Mede quantas vezes a máscara foi removida à noite:
     - 1 a 2 remoções: 5 pontos
     - 3 remoções: 4 pontos
     - 4 remoções: 3 pontos
     - 5 remoções: 1 ponto
     - 6 ou mais: 0 pontos
   - **Eventos por Hora / IAH (Até 5 pontos)**: Mede o Índice de Apneia e Hipopneia por hora:
     - Menos de 7 eventos/hora: 5 pontos
     - 7 a 9 eventos/hora: 4 pontos
     - 10 a 12 eventos/hora: 3 pontos
     - 13 a 15 eventos/hora: 2 pontos
     - 16 a 18 eventos/hora: 1 ponto
     - 19 ou mais eventos/hora: 0 pontos
3. **Cálculo de Tendências (15 dias)**: A visualização compara o desempenho atual com o histórico através de duas janelas:
   - *Esta semana*: dados dos últimos 7 dias (excluindo hoje).
   - *Semana passada*: dados de 8 a 14 dias atrás.
   - As tendências só são exibidas se houver dados em ambos os períodos.
4. **Resiliência e Performance**: O uso do formato Parquet otimiza a leitura de séries temporais pela API, enquanto o mecanismo de *append* na ingestão impede dados duplicados usando chaves deduplicadoras (`['patient', 'data_terapia']`).

### Exemplo Prático de Cálculo de Score (Caso de Uso Real)

Para ilustrar a precisão matemática da lógica de pontuação, considere o seguinte registro real do aplicativo myAir (segunda-feira, 18 de maio):
- **Horas de Uso**: 4h 51m (291 minutos) $\rightarrow$ **49 pontos** (Cálculo: $\frac{291}{60} \times 10 = 48.5$, arredondado matematicamente para 49).
- **Vedação da Máscara**: Boa (Fuga < 16 L/min) $\rightarrow$ **20 pontos**.
- **Eventos por hora (IAH)**: 6.3 eventos/hora $\rightarrow$ **5 pontos** (visto que é menor que 7.0/h).
- **Colocação/Retirada da Máscara**: 1 vez $\rightarrow$ **5 pontos** (visto que está na faixa de 1-2 remoções).
- **Pontuação Total**: **79 pontos** ($49 + 20 + 5 + 5$).

## Conclusão

O projeto está muito bem estruturado e focado na eficiência. A separação clara entre a etapa de processamento pesado (ETL para Parquet) e a API de consulta em tempo real (FastAPI) garante que a interface do dashboard seja rápida e escalável, suportando a adição de novos pacientes e métricas clínicas no futuro.
