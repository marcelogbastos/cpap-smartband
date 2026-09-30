# Dashboard Apneia do Sono 🌙

[![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Dashboard clínico integrado para monitoramento de **Apneia do Sono**, combinando dados de terapia CPAP (ResMed AirSense) com dados de sono e atividade da **Smartband Xiaomi Mi Fitness**.

---

## 📸 Screenshots

### Resumo Noturno
![Resumo Noturno](img/1-resumo.png)

### Gráficos Mensais
![Gráficos Mensais](img/2-graficos.png)

### Tabelas de Dados
![Tabelas](img/3-tabelas.png)

### Correlação CPAP × Sono
![Correlação](img/4-correlação.png)

---

## ✨ Funcionalidades

- 📊 **Resumo Noturno** — score CPAP, IAH, fuga, pressão e dados de sono da Smartband para qualquer noite selecionada
- 📅 **Calendário interativo** em português — filtra toda a tela pela data escolhida
- 📈 **Gráficos mensais** — visualiza score, IAH, pressão e score de sono do mês completo
- 🔢 **Médias do período** — 7 ou 30 dias anteriores à data selecionada
- 📑 **Tabelas detalhadas** — histórico completo com ordenação por coluna
- ℹ️ **Tooltips explicativos** — clique no `?` para entender cada métrica
- 👤 **Multi-paciente** — selecione entre diferentes pacientes
- 📉 **Tendências** — tipos de evento por noite (central, obstrutiva, hipopneia), adesão móvel de 30 dias com meta de 70%, pressão vs faixa configurada, médias móveis de IAH/uso/fuga e pontos de atenção automáticos
- 🌃 **Noite detalhada** — linha do tempo da noite: fases do sono da pulseira, eventos do CPAP no horário em que ocorreram, pressão/fuga a cada 30 s, respiração/ronco, FC e SpO₂, e eventos por fase do sono
- 🔗 **Explorador de correlações** — matriz de Spearman CPAP × sono com p-valor e nº de noites, e dispersão de qualquer par
- 📄 **Relatório para consulta** — página imprimível (ou PDF) com adesão, IAH por tipo, pressão, piores noites e sono do período

---

## 🏗️ Arquitetura

```
cpap_smartband/
├── data/                          # Dados brutos e processados (não versionados)
│   ├── cpap_sd/<paciente>/        # Cartão SD do CPAP ResMed
│   ├── Smartband/<paciente>/      # CSVs exportados do Mi Fitness (mesmo nome da pasta do CPAP)
│   └── processed/                 # Parquet gerados pelos pipelines
│       ├── summary/               # Dados CPAP por paciente
│       ├── smartband_sleep/       # Sono bruto Smartband
│       ├── smartband_sleep_daily/ # Sono agregado diário
│       ├── smartband_vitals/      # FC e SpO2 contínuos
│       └── smartband_activity/    # Passos e calorias diários
├── src/
│   ├── ingestion/                 # Pipelines de processamento
│   │   ├── edf.py                 # Leitor EDF/EDF+ próprio (arquivos da ResMed)
│   │   ├── processor.py           # Processamento CPAP: STR.edf (resumo diário) + DATALOG
│   │   ├── datalog_processor.py   # Sessões detalhadas: eventos (EVE) e sinais (PLD, SAD)
│   │   └── smartband_processor.py # Processamento Smartband (CSV → Parquet)
│   └── visualization/             # Servidor FastAPI + Frontend
│       ├── app.py                 # Entry point FastAPI
│       ├── routers/api.py         # Endpoints REST
│       ├── routers/analysis.py    # Endpoints de Tendências, Noite, Correlação e Relatório
│       ├── services/              # Lógica de scoring e carregamento
│       └── static/                # Frontend: index.html (dashboard) e report.html (relatório)
├── scripts/
│   └── generate_demo.py           # Gera demo HTML estática (dados reais, criptografados)
├── docs/                          # Documentação técnica
├── requirements.txt
├── start.ps1 / start.bat          # Scripts de inicialização
└── update_data.ps1                # Atualiza dados processados
```

---

## 🚀 Instalação e Uso

### Pré-requisitos

- Python **3.12+**
- Dados do CPAP: cartão SD do ResMed AirSense copiado para `data/cpap_sd/<paciente>/`
- Dados da Smartband: CSVs exportados do app Mi Fitness em `data/Smartband/<paciente>/`

> O **nome da pasta** identifica o paciente e liga as duas fontes: `data/cpap_sd/Marcelo/` e
> `data/Smartband/Marcelo/` são a mesma pessoa. Para um novo paciente, crie as duas pastas
> com o mesmo nome.


### 1. Clonar o repositório

```bash
git clone https://github.com/marcelogbastos/cpap-smartband.git
cd cpap_smartband
```

### 2. Criar ambiente virtual e instalar dependências

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Processar os dados

```powershell
# Windows (PowerShell) — CPAP + Smartband, todos os pacientes
.\update_data.ps1

# Reset completo (reprocessa tudo do zero)
.\update_data.ps1 -Reset

# Só um paciente (nome da pasta)
.\update_data.ps1 -Patient Marcelo
```

### 4. Iniciar o dashboard

```powershell
# Windows
.\start.ps1
# ou
.\start.bat
```

```bash
# Linux/macOS (ativar venv primeiro)
uvicorn src.visualization.app:app --reload --port 8000
```

Acesse: **http://127.0.0.1:8000**

Para executar o frontend em outra origem, configure `CPAP_CORS_ORIGINS` no
ambiente como uma lista de URLs separadas por virgula. Por padrao, a API aceita
apenas `localhost` e `127.0.0.1` na porta 8000.

> **Atualizando de uma versão anterior?** O leitor do `STR.edf` foi reescrito
> (a versão antiga, baseada em MNE, interpolava os valores diários). Na primeira
> execução do `update_data.ps1` os dados antigos são detectados e reconstruídos
> automaticamente; `.\update_data.ps1 -Reset` também funciona.

### Testes

```bash
python -m unittest tests.test_api_helpers tests.test_processing tests.test_analysis
```

---

## 🎮 Demo estática (HTML criptografado)

Gera um único arquivo HTML, sem servidor, com os dados embutidos e protegidos por senha:

```bash
python scripts/generate_demo.py --password <senha> [--output docs/demo.html]
```

> ⚠️ **Os dados embutidos são os dados reais** dos pacientes em `data/processed/` (o script
> sobe o servidor e copia as respostas da API). O arquivo é criptografado, mas a proteção
> depende inteiramente da força da senha — use uma senha forte antes de publicar ou
> versionar o `docs/demo.html`. Regenere o arquivo depois de reprocessar os dados.

---

## 📡 API REST

| Endpoint | Descrição |
|---|---|
| `GET /api/patients` | Lista pacientes disponíveis |
| `GET /api/data/{patient}` | Dados CPAP completos (timeseries + KPIs) |
| `GET /api/smartband/{patient}/daily` | Dados diários da Smartband |
| `GET /api/smartband/{patient}/monthly-sleep` | Sono mensal da Smartband |
| `GET /api/cpap/{patient}/monthly` | Dados CPAP mensais |
| `GET /api/cpap/{patient}/ahi-heatmap` | IAH diário agrupado por mês (heatmap) |
| `GET /api/correlation/{patient}` | Sono da Smartband em noites com IAH < 5 vs ≥ 5 |
| `GET /api/available-periods?patient=` | Meses com sessões CPAP |
| `GET /api/health` | Verificação de saúde do servidor |
| `GET /api/trends/{patient}?days=` | Série diária do calendário, adesão, tipos de evento, pressão vs faixa, pontos de atenção |
| `GET /api/night/{patient}/dates` | Noites com dados detalhados (CPAP e/ou pulseira) |
| `GET /api/night/{patient}/{AAAA-MM-DD}` | Linha do tempo de uma noite |
| `GET /api/correlation/{patient}/matrix` | Spearman CPAP × sono (ρ, p, n) |
| `GET /api/correlation/{patient}/pair?x=&y=` | Pontos e reta de tendência de um par de variáveis |
| `GET /api/report/{patient}?days=` ou `?start=&end=` | Dados do relatório para consulta |
| `GET /relatorio?patient=` | Página do relatório (imprimir / salvar PDF) |

Documentação interativa disponível em: **http://127.0.0.1:8000/docs**

---

## 📊 Métricas Monitoradas

### CPAP (ResMed AirSense)
| Métrica | Descrição | Referência |
|---|---|---|
| **Score myAir** | Pontuação geral da sessão | 0-100 (≥70 = Excelente) |
| **IAH** | Índice de Apneia-Hipopneia | <5 = Normal |
| **Fuga P95** | Vazamento de ar (percentil 95; o STR.edf grava em L/s, convertido para L/min) | ≤24 L/min |
| **Pressão P95** | Pressão aplicada (percentil 95) | cmH₂O |
| **Uso da Máscara** | Tempo de uso contínuo | ≥4h recomendado |
| **Eventos de Máscara** | Remoções durante a noite | — |

### Smartband (Xiaomi Mi Fitness)
| Métrica | Descrição |
|---|---|
| **Score do Sono** | Avaliação geral da qualidade do sono |
| **Duração Total** | Tempo total dormindo |
| **Sono REM** | Fase de recuperação mental |
| **Sono Profundo** | Fase de recuperação física |
| **Sono Leve** | Fase de transição |
| **Tempo Acordado** | Interrupções durante a noite |

---

## 🔒 Privacidade e Dados

Os dados médicos do paciente **nunca são versionados** no repositório. O `.gitignore` exclui:

- `data/cpap_sd/` — dados brutos do CPAP
- `data/Smartband/` — CSVs da Smartband
- `data/processed/` — dados processados em Parquet

Apenas o código-fonte e os scripts são publicados.

---

## 🛠️ Tecnologias

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.12, FastAPI, Uvicorn |
| Processamento | Pandas, PyArrow, NumPy (leitor EDF próprio para o STR.edf) |
| Frontend | HTML5, Vanilla JS, Tailwind CSS |
| Gráficos | Chart.js |
| Calendário | Flatpickr (pt-BR) |
| Dados | Apache Parquet |

---

## 📄 Licença

MIT License — veja [LICENSE](LICENSE) para detalhes.

---

## 👤 Autor

**Marcelo G. Bastos** — Criador e mantenedor do projeto.

---

## ⚙️ Como executar (rápido)

Encontrará instruções detalhadas de execução com e sem Docker em: `docs/documentacao_tecnica.md` (seção "12. Como Executar (Docker / Sem Docker)").

Em resumo:

- Docker: `docker-compose up --build` (recomendado)
- Local: criar venv, `pip install -r requirements.txt`, rodar `python -m src.ingestion.processor`, `python -m src.ingestion.smartband_processor` e `uvicorn src.visualization.app:app --reload`


Desenvolvido para uso pessoal e clínico no monitoramento de terapia CPAP integrado com wearables.
