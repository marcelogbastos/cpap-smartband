# Dashboard Apneia do Sono

**Dashboard integrado de terapia do sono**

## Problema

Pacientes de apneia do sono usam CPAP ResMed e smartbands (Xiaomi Mi Band), mas os dados ficam em silos — o cartão SD do CPAP armazena métricas clínicas (IAH, vazamento, pressão) em formato EDF proprietário, e a smartband registra estágios do sono, SpO2 e FC. Não há correlação entre eles.

## Solução

Pipeline ETL + dashboard full-stack que unifica essas fontes:

- **Ingestão**: Leitura de arquivos STR.edf do cartão SD via MNE (biblioteca EEG adaptada para CPAP) + processamento de CSVs exportados do Mi Fitness → dados estruturados em Parquet particionado por paciente
- **API**: FastAPI com 6 endpoints REST servindo KPIs, séries temporais e tabelas mensais
- **Frontend**: SPA vanilla (Chart.js + Tailwind CSS) com 3 abas — Resumo (KPIs + status ring), Gráficos (6 charts com cores por status clínico), Tabelas (sortáveis com dados diários)
- **Score myAir**: Algoritmo próprio (0–100) ponderando uso, vazamento, eventos de máscara e IAH
- **Armazenamento incremental**: Parquet com dedup, suporte a múltiplos pacientes e reprocessamento

## Stack

Python, FastAPI, Pandas, PyArrow, MNE, Chart.js, Tailwind CSS, Dash (legado)

## Resultado

Dashboard único correlacionando terapia CPAP com sono do wearable — acesso local via navegador, atualização incremental dos dados.
