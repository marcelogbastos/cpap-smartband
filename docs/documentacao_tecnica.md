# Documentação Técnica — Dashboard Apneia do Sono

## 1. Visão Geral

Sistema full-stack para coleta, processamento e visualização de dados de terapia do sono, integrando:

- **CPAP ResMed AirSense** — leitura do cartão SD (arquivos STR.edf em formato EDF+)
- **Xiaomi Smart Band (Mi Fitness)** — importação de dados exportados do aplicativo Mi Fitness

O pipeline transforma dados brutos proprietários em Parquet estruturado e os expõe via API REST com dashboard frontend single-page.

---

## 2. Estrutura do Projeto

```
CPAP-ResMed/
├── data/
│   ├── cpap_sd/<paciente>/          # Dados brutos do cartão SD do CPAP
│   │   ├── STR.edf                  # Estatísticas diárias sumarizadas
│   │   ├── Identification.crc/tgt   # Metadados do dispositivo
│   │   └── DATALOG/YYYYMMDD/        # Sessões detalhadas por data
│   │       ├── *_CSL.edf            # Pressão, fluxo, vazamento (alta frequência)
│   │       ├── *_EVE.edf            # Eventos (apneias, hipopneias)
│   │       ├── *_BRP.edf            # Respiração (banda torácica)
│   │       ├── *_PLD.edf            # Carga pulmonar
│   │       └── *_SAD.edf            # Saturação/desaturação
│   ├── Smartband/                   # CSVs exportados do Xiaomi Mi Fitness
│   │   └── <paciente>/              # Mesmo nome da pasta em cpap_sd/
│   │       └── AAAAMMDD_<UID>_MiFitness_*.csv
│   └── processed/                   # Dados processados em Parquet
│       ├── summary/                 # CPAP: particionado por patient_slug
│       ├── smartband_sleep/         # Sono bruto (sessões)
│       ├── smartband_sleep_daily/   # Sono agregado diário (com sleep_score)
│       ├── smartband_vitals/        # FC e SpO2 contínuos
│       └── smartband_activity/      # Passos e calorias diários
├── src/
│   ├── ingestion/
│   │   ├── processor.py             # Pipeline CPAP: STR.edf → Parquet
│   │   └── smartband_processor.py   # Pipeline Smartband: CSV → Parquet
│   └── visualization/
│       ├── app.py                   # Entry point FastAPI (porta 8000)
│       ├── routers/
│       │   └── api.py               # Endpoints REST (6 rotas)
│       ├── schemas/
│       │   └── models.py            # Pydantic models de resposta
│       ├── services/
│       │   ├── data_loader.py       # Carregamento dos Parquets
│       │   └── cpap_scoring.py      # Algoritmo myAir Score (0–100)
│       ├── static/
│       │   └── index.html           # Dashboard SPA (1190 linhas)
│       ├── dashboard.py             # Dashboard legado Dash (porta 8050)
│       ├── dashboard_pro.py         # Dashboard "Pro" Dash (porta 8051)
│       ├── generate_report.py       # Gerador de relatório texto CLI
│       └── inspect_data.py          # Ferramenta de inspeção CLI
├── docs/
│   ├── resumo_linkedin.md           # Resumo para apresentação
│   ├── documentacao_tecnica.md      # Este documento
│   ├── cpap_project_analysis.md     # Análise da arquitetura
│   ├── sd_card_structure.md         # Estrutura do cartão SD ResMed
│   └── smartband_data_specification.md  # Especificação dos CSVs Smartband
├── requirements.txt                 # Dependências Python
├── start.bat                        # Inicializador Windows Batch
├── start.ps1                        # Inicializador PowerShell
├── update_data.ps1                  # Atualização completa dos dados
└── process_data.bat                 # Processamento CPAP apenas
```

---

## 3. Stack Tecnológica

### Backend (Python)

| Biblioteca   | Versão Mínima | Função                                |
|-------------|---------------|---------------------------------------|
| FastAPI     | ≥0.100.0      | Framework REST API                    |
| Uvicorn     | ≥0.23.0       | Servidor ASGI                         |
| Pandas      | ≥2.0.0        | Manipulação de dados tabulares        |
| PyArrow     | ≥12.0.0       | Leitura/escrita Parquet com partições |
| Pydantic    | ≥2.0.0        | Validação de schemas de resposta      |
| NumPy       | ≥1.24.0       | Leitura binária do STR.edf (leitor EDF próprio) |

### Frontend (CDN, carregado no navegador)

| Biblioteca                      | Função                          |
|--------------------------------|---------------------------------|
| Tailwind CSS 3.x               | Framework CSS utility-first     |
| Chart.js 4.x                   | Renderização de gráficos (6)    |
| chartjs-plugin-datalabels 2.x  | Rótulos nos dados dos gráficos  |

### Formato de Armazenamento

- **Parquet com partição por paciente** (`patient_slug=...`): permite adição incremental sem reprocessar tudo, consultas eficientes por paciente, compressão colunar.

---

## 4. Pipeline de Ingestão

### 4.1 CPAP — `processor.py`

**Entrada:** `data/cpap_sd/<paciente>/STR.edf`

**Processo:**
1. `CPAPIngestion.__init__(reset=False)` — define diretórios, opcionalmente limpa dados existentes
2. `read_str_edf(file_path)` → usa `read_resmed_str()`, um leitor EDF próprio (NumPy)
   - 1 registro EDF = 1 dia (inicia ao meio-dia) → **1 linha por dia**
   - Só sinais com 1 amostra/registro viram colunas (`AHI`, `Leak.95`, `Duration`, `MaskEvents`...);
     `MaskOn`/`MaskOff` (10 amostras/dia) são ignorados
   - Valor digital `-1` (convenção ResMed para "sem dado") → `NaN`
   - `Leak.*` é convertido de L/s (unidade do arquivo) para **L/min**
3. `process_all_users()` → itera sobre pastas em `data/cpap_sd/`, processa STR.edf de cada paciente
4. `save_to_parquet(df, table_name, dedupe_keys)`:
   - Particiona por `patient_slug` (nome normalizado: sem acentos, lowercase, underscores)
   - Se partição já existe e `reset=False`: carrega dados existentes, combina com novos e remove duplicatas por `[patient, data_terapia]` mantendo **a leitura mais recente** (`keep='last'`)
   - Dados no formato antigo (várias linhas reamostradas por dia, gerados pelo leitor MNE) são detectados e descartados automaticamente
   - A partição é regravada com `pq.write_to_dataset()`

**Chave de desduplicação:** `["patient", "data_terapia"]`

**Tratamento de `usage_mins` (data_loader.py):**
- Se algum `Duration` do paciente excede 1440 minutos (24h), assume que está em segundos → divide por 60
- Caso contrário, mantém em minutos
- Preenche NaN com 0

### 4.1b CPAP — sessões detalhadas (`datalog_processor.py`)

**Entrada:** `data/cpap_sd/<paciente>/DATALOG/<AAAAMMDD>/<AAAAMMDD_HHMMSS>_*.edf` — chamado pelo `processor.py`.

| Arquivo | Conteúdo | Tabela Parquet |
|---|---|---|
| `*_EVE.edf` | Anotações EDF+: apneia central/obstrutiva/não classificada, hipopneia, despertar (horário e duração) | `cpap_events` |
| `*_PLD.edf` | Pressão na máscara, pressão alvo, EPR, fuga, freq. respiratória, volume, ventilação, ronco, limitação de fluxo (a cada 2 s) — agregados em janelas de 30 s; fuga em L/min | `cpap_signals` |
| `*_SAD.edf` | Pulso e SpO₂ do oxímetro (só com oxímetro conectado; sessões vazias são ignoradas) | `cpap_oximetry` |

- A noite de cada registro é `início − 12 h` (mesma regra do STR.edf).
- Gravação por sessão: sessões presentes no cartão substituem as antigas; sessões que já saíram do cartão são preservadas.
- `*_BRP.edf` (fluxo a 25 Hz) e `*_CSL.edf` não são processados.

### 4.2 Smartband — `smartband_processor.py`

**Entrada:** `data/Smartband/<paciente>/AAAAMMDD_<UID>_MiFitness_<tabela>.csv`

- Uma pasta por paciente, com o **mesmo nome** da pasta em `data/cpap_sd/` — é o nome da pasta que liga os dados do CPAP aos da Smartband.
- Se houver mais de uma exportação na pasta, usa a mais recente (data no nome do arquivo). Um aviso é emitido se a pasta misturar contas Mi Fitness diferentes (UIDs distintos).
- CSVs soltos direto em `data/Smartband/` são ignorados (com aviso).

**Fases do sono:** a tabela `smartband_sleep_stages` guarda cada intervalo (início, fim, fase) com a noite calculada por `início − 12 h`. Códigos do Mi Fitness (campo `state`), conferidos contra os totais do próprio registro: **2 = profundo, 3 = leve, 4 = REM, 5 = acordado**.

**Tabelas processadas:**

| Tabela CSV                    | Tabela Parquet de saída        | Conteúdo                           |
|------------------------------|-------------------------------|-----------------------------------|
| hlth_center_fitness_data     | smartband_sleep               | Sessões de sono (raw, estágios detalhados, FC, SpO2) |
| hlth_center_fitness_data     | smartband_vitals              | FC contínua + SpO2                 |
| hlth_center_aggregated_fitness_data | smartband_sleep_daily   | Sono diário agregado (sleep_score, durações) |
| hlth_center_aggregated_fitness_data | smartband_activity      | Passos, distância, calorias diários |
| user_member_profile          | smartband_profile             | Perfil do usuário                  |

**Processo:**
1. `find_csv()` — localiza o CSV mais recente por padrão de nome (`*_Smartband_<table>.csv`)
2. Parse de JSON: o campo `Value` dos CSVs contém JSON aninhado → `safe_json_parse()`
3. Conversão de timestamp: epoch seconds → datetime UTC-3 (`timedelta(hours=-3)`)
4. Sono raw: extrai `bedtime`, `wake_up_time`, estágios (acordado/leve/profundo/REM), FC, SpO2
5. Sono diário: extrai `sleep_score`, durações, segmentos (suporta sonecas)
6. Vitals: unifica heart_rate (contínua + resting) + SpO2 em um único dataset
7. Atividade: steps + calorias (cal_agg enriquece steps com total_calories)
8. `save_parquet()` — sempre sobrescreve a partição (não há incremento; reload total)

---

## 5. API REST — `api.py`

Servidor: `uvicorn src.visualization.app:app --host 127.0.0.1 --port 8000`

### 5.1 Rotas

| Método | Rota                                    | Retorno                          | Fonte de dados             |
|--------|----------------------------------------|----------------------------------|---------------------------|
| GET    | `/api/patients`                        | `List[str]` — nomes dos pacientes | `summary/` Parquet        |
| GET    | `/api/data/{patient}`                  | KPIs + séries temporais CPAP     | `summary/` Parquet        |
| GET    | `/api/smartband/{patient}/daily`       | Sono + atividade Smartband       | `smartband_sleep_daily/`, `smartband_activity/` |
| GET    | `/api/smartband/{patient}/monthly-sleep` | Tabela mensal de sono          | `smartband_sleep_daily/`  |
| GET    | `/api/cpap/{patient}/monthly`          | Tabela mensal CPAP               | `summary/` Parquet        |
| GET    | `/api/available-periods`               | Anos/meses disponíveis           | `summary/` Parquet        |

### 5.2 Lógica de Sessão (data_sessao)

`data_sessao = (data_terapia - 12h).date`

Uma sessão de sono noturno é definida de **12:00 às 12:00 do dia seguinte**. Isso garante que uma única noite de terapia (que pode cruzar a meia-noite) permaneça agrupada.

### 5.3 Agregação Mensal CPAP

```python
session_df = df.groupby('data_sessao').agg({
    'usage_mins': 'max',
    'AHI': 'max',          # pico da sessão (evita médias com valores negativos do sinal bruto)
    'Leak.95': 'max',
    'MaskEvents': 'max',
    'MaskPress.95': 'max',
    'TidVol.50': 'max',
    'MinVent.50': 'max',
    'RespRate.50': 'max',
    'BlowPress.95': 'max'
})
```

O STR.edf armazena sinais contínuos com ~10 amostras por sessão. Cada métrica clínica (AHI, vazamento, etc.) varia ao longo da noite. A agregação `max` captura o valor representativo do pico. AHI é adicionalmente limitado a ≥ 0 via `clip(lower=0)`.

### 5.4 Renomeação de Colunas

```python
rename_map = {
    'AHI': 'ahi',
    'Leak.95': 'leak_95',
    'MaskEvents': 'mask_events',
    'MaskPress.95': 'pressure',
    'TidVol.50': 'tidal_volume',
    'MinVent.50': 'minute_ventilation',
    'RespRate.50': 'breath_rate',
    'BlowPress.95': 'p95_pressure'
}
```

### 5.5 Cálculo do myAir Score — `cpap_scoring.py`

Composto por 4 sub-scores (total 0–100):

| Componente      | Pontos Máx | Lógica                                               |
|----------------|-----------|------------------------------------------------------|
| Uso (usage)    | 70        | 10 pts por hora de uso, limitado a 7h                |
| Selo Máscara   | 20        | 20 se ≤16 L/min, decresce 1 pt a cada 2 L/min, 0 se ≥55 |
| Remoções       | 5         | 5 se ≤2, 4 se 3, 3 se 4, 1 se 5, 0 se ≥6 — remoções = `MaskEvents ÷ 2 − 1` (MaskEvents conta colocações e retiradas) |
| AHI            | 5         | 5 se <7, 4 se <10, 3 se <13, 2 se <16, 1 se <19, 0 se ≥19 |

---

## 6. Frontend — `index.html`

### 6.1 Arquitetura

SPA puro (sem framework) com 1190 linhas:

- **HTML** → estrutura das abas (Resumo, Gráficos, Tabelas)
- **CSS inline** → dark theme, cards, popups, info buttons
- **JavaScript vanilla** → data fetching, renderização, sorting, charts

### 6.2 Abas

| Aba        | Conteúdo                                                                 |
|-----------|-------------------------------------------------------------------------|
| Resumo    | KPIs da última noite (CPAP + Smartband), ring status (score combinado), médias 7 dias |
| Gráficos  | 6 Chart.js: Pontuação CPAP, Score Sono, IAH, Pressão, Fuga, Duração vs Uso |
| Tabelas   | Tabelas sortáveis: Sono Mensal (data, duração, REM, profundo, leve, acordado, %REM) + CPAP Mensal (data, uso, IAH, fuga, eventos, score, pressão, vol. tidal, vent. minuto, freq. resp., P95 pressão) |

### 6.3 Fluxo de Dados

```
fetchPatients() → /api/patients → popula <select>
    ↓ (seleção de paciente/mês/ano)
loadPatientData() → /api/data/{patient} → KPIs + timeseries
loadMonthlySleep() → /api/smartband/{patient}/monthly-sleep → tabela sono
loadMonthlyCpap() → /api/cpap/{patient}/monthly → tabela CPAP
    ↓
sortTable() → ordena + renderCpapTable() / renderSleepTable()
renderCharts() → 6 createChart() com Chart.js
```

### 6.4 Cores por Status Clínico

Todos os gráficos usam cores dinâmicas baseadas em thresholds clínicos:

| Gráfico             | Verde                            | Amarelo                      | Vermelho                     |
|--------------------|----------------------------------|------------------------------|------------------------------|
| Pontuação CPAP     | ≥70                              | 50–70                        | <50                          |
| Score Sono         | ≥70                              | 50–70                        | <50                          |
| IAH                | <5                               | 5–15                         | >15                          |
| Pressão            | ≤12 cmH₂O                        | 12–16                        | >16                          |
| Fuga               | ≤24 L/min                        | —                            | >24 L/min                    |

---

## 7. Armazenamento: Parquet com Partições

### 7.1 Estrutura no Disco

```
data/processed/
├── summary/
│   └── patient_slug=marcelo/
│       └── 0f930aaec51d42ba9f4f8880fb21fe15-0.parquet
├── smartband_sleep/
│   └── patient_slug=marcelo/
│       └── ...
├── smartband_sleep_daily/
│   └── patient_slug=marcelo/
├── smartband_vitals/
│   └── patient_slug=marcelo/
└── smartband_activity/
    └── patient_slug=marcelo/
```

### 7.2 Vantagens

- **Leitura seletiva**: `pd.read_parquet("summary/patient_slug=marcelo")` carrega apenas dados de um paciente
- **Compressão colunar**: `pyarrow` + `snappy` ou `zstd` (default)
- **Schema evolutivo**: novas colunas são adicionadas sem quebrar dados existentes
- **Particionamento Hive-style**: compatível com Spark, DuckDB, etc.

---

## 8. Scripts de Execução

### 8.1 Inicialização do Servidor

**`start.bat` / `start.ps1`:**
1. Cria venv se não existir
2. Instala dependências via `pip install -r requirements.txt`
3. Inicia `uvicorn src.visualization.app:app --host 127.0.0.1 --port 8000 --reload`

### 8.2 Atualização de Dados

**`update_data.ps1`:**
```
.\update_data.ps1 [-Reset] [-Patient <nome>]   # sem -Patient: todos os pacientes
```

Executa em sequência:
1. `python -m src.ingestion.processor [--reset] [--patient <nome>]` — processa o STR.edf de cada pasta em `data/cpap_sd/`
2. `python -m src.ingestion.smartband_processor [--patient <nome>]` — processa cada pasta em `data/Smartband/`

**`process_data.bat`:**
```
process_data.bat [--reset]
```

Executa apenas o pipeline CPAP (sem Smartband).

### 8.3 Processadores Individuais

```bash
# CPAP (todos os pacientes, ou um só com --patient)
python -m src.ingestion.processor [--reset] [--patient Marcelo]

# Smartband
python -m src.ingestion.smartband_processor [--patient Marcelo]
```

---

## 9. Informações do Hardware

### CPAP
- **Modelo**: ResMed AirSense (10 ou 11)
- **Cartão SD**: armazena `STR.edf` (sumário diário) + `DATALOG/` (sessões detalhadas)
- **Canais do STR.edf**: 81 canais, incluindo AHI, Leak.95/50, MaskPress.95/50, MinVent.50/95, RespRate.50/95, TidVol.50/95, BlowPress.95/5, Flow.95/5, SpO2.50/95, estágios de pressão (TgtIPAP, TgtEPAP), configurações do dispositivo
- **Frequência de amostragem**: ~0.0001157 Hz (1 amostra a cada ~2.4h, 10 amostras/dia)
- **Período coberto**: 04/05/2026 a 20/05/2026 (17 dias, 170 amostras)

### Smartband
- **Dispositivo**: Xiaomi Smart Band 9 Active
- **Período**: ~37 dias de dados (até 21/05/2026)

---

## 10. Decisões Técnicas Relevantes

### 10.1 Leitor EDF próprio para o STR.edf
O STR.edf mistura sinais com 1 amostra/dia e sinais com 10 amostras/dia (`MaskOn`/`MaskOff`). O MNE (usado até a versão anterior) reamostra todos os sinais para a maior taxa e interpola, o que distorce os valores diários (IAH, uso e eventos inflados; valores negativos em dias sem uso). O pyedflib recusa o arquivo porque o cabeçalho da ResMed não é 100% conforme (ex.: unidade `Â°C`). Como o formato EDF é simples, o projeto lê o arquivo diretamente com NumPy, cada sinal na sua taxa nativa.

### 10.2 Sessão Noon-to-Noon
`data_sessao = data_terapia - 12h` → garante que uma sessão de sono que começa às 22:00 e termina às 06:00 do dia seguinte seja contabilizada como uma única noite.

### 10.3 Heurística de Unidade do Duration
```python
if p_dur.max() > 1440:  # > 1440 minutos = 24h
    usage_mins = p_dur / 60  # estava em segundos
else:
    usage_mins = p_dur        # já está em minutos
```
Alguns dispositivos ResMed reportam Duration em minutos, outros em segundos. O threshold de 1440 (minutos = 24h) distingue os dois casos.

### 10.4 Agregação com `max` em vez de `mean`
Os sinais do STR.edf oscilam ao longo da sessão (ex.: AHI varia sinusoidalmente entre -4 e +19). O `max` captura o pico representativo. `mean` propagaria valores negativos (artefato do sinal bruto).

### 10.5 Incremental vs Total
- CPAP: incremental (append + dedup por `[patient, data_terapia]`)
- Smartband: total (sempre sobrescreve a partição)
  - Motivo: Smartband exporta CSVs completos; não há delta tracking

---

## 11. Endpoints Detalhados

### `GET /api/cpap/{patient}/monthly`
**Query params:** `year`, `month` (opcionais)

**Resposta:**
```json
{
  "rows": [
    {
      "data_sessao": "2026-05-20",
      "usage_mins": 421.3,
      "ahi": 7.12,
      "leak_95": 0.18,
      "mask_events": 4.0,
      "score": 99,
      "pressure": 9.78,
      "tidal_volume": 0.40,
      "minute_ventilation": 4.59,
      "breath_rate": 11.04,
      "p95_pressure": 10.91
    }
  ]
}
```

### `GET /api/smartband/{patient}/monthly-sleep`
**Query params:** `year`, `month` (opcionais)

### Normalização do paciente

As rotas que recebem `{patient}` filtram o nome usando a mesma normalização das
partições Parquet: minúsculas, remoção de acentos e conversão de espaços para
underscore. Portanto, `Marcelo`, `marcelo` e `MARCELO` identificam o mesmo
paciente.

---

## 12. Como Executar (Docker / Sem Docker)

Estas instruções mostram como executar o projeto localmente tanto usando Docker (recomendado para isolamento) quanto sem Docker (ambiente Python local).

12.1. Usando Docker (recomendado)

- Pré-requisitos: `docker` e `docker-compose` instalados.
- O repositório já inclui `Dockerfile` e `docker-compose.yml` para rodar o servidor e um volume para `data/`.

Construir a imagem (opcional - o `docker-compose` faz build automaticamente):

```bash
docker build -t cpap_smartband:latest .
```

Executar com `docker run` (exemplo simples):

```bash
docker run --rm -it -p 8000:8000 \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  --env-file .env \
  cpap_smartband:latest
```

Ou usar `docker-compose` (recomendado):

```bash
docker-compose up --build
```

Pontos importantes:
- Monte `data/` como volume para o container acessar os dados brutos e processados.
- Monte `logs/` se quiser persistir logs gerados dentro do container.
- Forneça um arquivo `.env` (copie `.env.example`) com as variáveis necessárias.

12.2. Sem Docker (Python local)

- Pré-requisitos: Python 3.12+, `pip` e (opcional) `virtualenv`.

Passos (Windows PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Opcional: copie exemplo de variáveis
copy .env.example .env
# Processar dados (CPAP + Smartband)
python -m src.ingestion.processor
python -m src.ingestion.smartband_processor
# Iniciar servidor
uvicorn src.visualization.app:app --host 127.0.0.1 --port 8000 --reload
```

Linux / macOS (bash):

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python -m src.ingestion.processor
python -m src.ingestion.smartband_processor
uvicorn src.visualization.app:app --host 0.0.0.0 --port 8000 --reload
```

Dicas:
- Para reprocessar tudo use `--reset` no `processor.py` ou rode `.\update_data.ps1 -Reset`.
- Logs são gravados em `logs/processor.log` e `logs/smartband_processor.log` por padrão.
- O leitor do STR.edf não depende de bibliotecas de sistema; basta `pip install -r requirements.txt`.

12.3. Testes rápidos

Suíte completa:

```bash
python -m unittest tests.test_api_helpers tests.test_processing tests.test_analysis
```

Executar teste rápido unitário (criação simples) para `calculate_myair_score` (exemplo):

```bash
python - <<'PY'
from src.visualization.services.cpap_scoring import calculate_myair_score
import pandas as pd
row = pd.Series({'usage_mins': 300, 'Leak.95': 10, 'mask_removals': 0, 'AHI': 4})
print(calculate_myair_score(row))
PY
```

---

**Resposta:**
```json
{
  "rows": [
    {
      "report_date": "2026-05-20",
      "total_duration_min": 480,
      "rem_min": 96,
      "deep_min": 72,
      "light_min": 240,
      "awake_min": 72,
      "sleep_score": 82
    }
  ]
}
```

---

## 12. Dashboard Legado (Dash/Plotly)

Além da SPA principal, existem dois dashboards construídos com **Dash** e **Plotly**:

| Arquivo              | Porta | Descrição                        |
|---------------------|-------|----------------------------------|
| `dashboard.py`      | 8050  | Dashboard básico: seleção de paciente, KPIs semanais, gráficos score/ahi/uso |
| `dashboard_pro.py`  | 8051  | "myAir Analytics Pro": grid 3-colunas com gauges (score, AHI, remoções), gráfico de vazamento, pizza de estágios, cartões de revisão semanal/mensal |

Ambos usam `plotly.express` e `plotly.graph_objects` para gráficos interativos. A SPA os substitui por serem mais leves e sem necessidade de servidor WebSocket.

---

## 13. Ferramentas CLI

### `generate_report.py`
```bash
python src/visualization/generate_report.py --patient marcelo --period 7
```
Gera relatório texto no terminal com médias, última noite, score, etc.

### `inspect_data.py`
```bash
python src/visualization/inspect_data.py
```
Inspeciona dados processados: lista pacientes, datas disponíveis, colunas dos Parquets.

---

## 14. Configuração do Ambiente

### Requisitos
- Python ≥3.10
- Windows (scripts .bat/.ps1) ou Linux (adaptação dos paths)

### Instalação Manual
```bash
python -m venv venv
.\venv\Scripts\activate     # Windows
# source venv/bin/activate  # Linux
pip install -r requirements.txt
```

### Execução
```bash
python -m uvicorn src.visualization.app:app --host 127.0.0.1 --port 8000
```

Acesso: http://127.0.0.1:8000

### CORS

Por padrão, a API aceita requisições do dashboard em:

```env
CPAP_CORS_ORIGINS=http://127.0.0.1:8000,http://localhost:8000
```

Para permitir outras origens, defina `CPAP_CORS_ORIGINS` no arquivo `.env` como
uma lista de URLs separadas por vírgula. Evite usar `*` em ambientes com dados
reais.

---

## 15. Volumetria (Maio/2026)

| Dataset               | Registros | Período |
|----------------------|-----------|---------|
| CPAP (summary)       | 170       | 17 dias |
| Smartband sleep raw  | ~30       | ~37 dias |
| Smartband sleep daily| ~37       | ~37 dias |
| Smartband vitals     | ~500+     | ~37 dias |
| Smartband activity   | ~37       | ~37 dias |

---

## Abas de análise

Cálculos em `src/visualization/services/analysis.py` (funções puras, testadas em `tests/test_analysis.py`); endpoints em `src/visualization/routers/analysis.py`.

- **Tendências** (`/api/trends`): calendário completo (dias sem uso = 0 h). Adesão = % dos dias com uso ≥ 4 h (meta 70%), também em janela móvel de 30 dias. Índices médios do período ponderados pelas horas de uso (eventos totais ÷ horas). Pressão P95 "no máximo" quando ≥ máx. configurado − 0,2 cmH₂O (só AutoSet). Pontos de atenção gerados por `observations()` — texto factual, sem diagnóstico.
- **Noite detalhada** (`/api/night`): janela = sessões do CPAP ∪ sono da pulseira (± 15 min). Cada evento recebe a fase do sono em que ocorreu; a taxa por fase usa só o tempo daquela fase com a máscara em uso (mínimo de 15 min).
- **Correlação** (`/api/correlation/.../matrix` e `/pair`): Spearman com p-valor por permutação (sem SciPy); marcação de "poucas noites" abaixo de 20. Registros da pulseira com 0 min de profundo/REM ou score 0 são tratados como ausentes.
- **Relatório** (`/relatorio`): página A4 imprimível com resumo, pontos de atenção, gráficos de uso e IAH por tipo, configuração, piores noites e sono da pulseira.
