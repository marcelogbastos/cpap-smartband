# Especificação de Exportação de Dados - Mi Fitness

Este documento descreve as especificações técnicas, estruturas e schemas dos arquivos gerados pelo recurso de exportação ("Data Copy Guide") do aplicativo **Xiaomi Mi Fitness (Xiaomi运动健康)**, conforme documentado no guia oficial da Xiaomi (versão 2025/7) e **validado contra os dados reais exportados em 20/05/2026**.

> [!IMPORTANT]
> **Os nomes dos campos (headers) nos CSVs reais utilizam CamelCase** (ex: `UpdateTime`), enquanto a documentação oficial da Xiaomi usa snake_case (ex: `update_time`). Este documento já reflete os nomes reais encontrados nos arquivos.

---

## 1. Visão Geral da Exportação

A exportação de dados do Mi Fitness gera um conjunto de arquivos em formato **CSV (Comma-Separated Values)** com o padrão de nome:
```
YYYYMMDD_<UID>_MiFitness_<nome_da_tabela>.csv
```

### Inventário dos Arquivos Exportados

| # | Arquivo | Registros | Tamanho | Status |
| :--- | :--- | ---: | ---: | :--- |
| 1 | `hlth_center_fitness_data.csv` | 26.128 | 2.7 MB | ✅ Com dados |
| 2 | `hlth_center_aggregated_fitness_data.csv` | 382 | 73 KB | ✅ Com dados |
| 3 | `hlth_center_data_source.csv` | 4 | 638 B | ✅ Com dados |
| 4 | `user_fitness_data_records.csv` | 24 | 3.9 KB | ✅ Com dados |
| 5 | `user_fitness_profile.csv` | 1 | 364 B | ✅ Com dados |
| 6 | `user_member_profile.csv` | 1 | 140 B | ✅ Com dados |
| 7 | `user_device_setting.csv` | 1 | 142 B | ✅ Com dados |
| 8 | `hlth_center_sport_record.csv` | 0 | 43 B | ⬜ Somente header |
| 9 | `hlth_center_sport_track_data.csv` | 0 | 32 B | ⬜ Somente header |
| 10 | `user_fitness_with_uuid_data_records.csv` | 0 | 49 B | ⬜ Somente header |
| 11 | `user_health_plan_records.csv` | 0 | 64 B | ⬜ Somente header |
| 12 | `user_pk_invite_record.csv` | 0 | 62 B | ⬜ Somente header |
| 13 | `user_pk_record.csv` | 0 | 143 B | ⬜ Somente header |
| 14 | `user_pk_result_statistics.csv` | 0 | 42 B | ⬜ Somente header |

> [!NOTE]
> Quatro arquivos descritos na documentação oficial **não estão presentes** na exportação atual:
> `hlthappUserFeedback.csv`, `hlth_user_course_train_statistics.csv`, `hlth_user_course_train_record.csv`, `hlth_center_medical_data.csv`.
> Isso pode ocorrer porque o usuário não possui dados nessas categorias ou o recurso não está habilitado na região/versão do app.

---

## 2. Schemas dos Arquivos (Validados)

### 2.1 `hlth_center_fitness_data.csv` — Dados Brutos de Saúde
**Principal tabela do dataset.** Contém 26.128 registros de medições individuais de saúde e atividade física capturadas pelo wearable. Cobertura temporal: **13/04/2026 a 19/05/2026** (~37 dias, ~706 registros/dia).

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Uid` | int | Mi Account ID |
| `Sid` | string | Identificador da fonte de dados (ex: `2105367160` = dispositivo wearable) |
| `Key` | string | Tipo de dado de saúde (ver tabela de keys abaixo) |
| `Time` | int (epoch) | Timestamp Unix da medição |
| `Value` | string (JSON) | Dado da medição em formato JSON estruturado |
| `UpdateTime` | int (epoch) | Última modificação do registro |

#### Tipos de dados (`Key`) encontrados:

| Key | Registros | Estrutura do JSON `Value` | Descrição |
| :--- | ---: | :--- | :--- |
| `calories` | 10.296 | `{"time", "calories"}` | Queima calórica incremental (~60s granularidade) |
| `steps` | 4.496 | `{"time", "steps", "distance", "calories"}` | Contagem de passos com distância (m) e calorias |
| `heart_rate` | 3.575 | `{"time", "bpm", "type"}` | Frequência cardíaca contínua (monitoramento automático, `type`=0) |
| `abnormal_heart_rate` | 3.575 | `{"bpm", "prev_bpm", "time"}` | Espelho de `heart_rate` — ver nota abaixo |
| `spo2` | 2.303 | `{"time", "spo2"}` | Saturação de oxigênio no sangue (SpO2 %, ~1 medição a cada 10 min) |
| `single_heart_rate` | 1.598 | `{"bpm", "time"}` | Medição avulsa de frequência cardíaca (resolução por segundo) |
| `intensity` | 181 | `{"time"}` | Registro de atividade de intensidade |
| `sleep` | 43 | `{"avg_hr", "avg_spo2", "bedtime", "breath_quality", "sleep_deep_duration", "sleep_light_duration", "sleep_rem_duration", "duration", "items":[...], ...}` | **Dados completos de sono** (ver detalhes abaixo) |
| `valid_stand` | 31 | `{"count"}` | Horas em pé efetivas do dia |
| `resting_heart_rate` | 18 | `{"bpm", "date_time"}` | FC de repouso diária |
| `low_heart_rate` | 11 | — | Alertas de FC baixa |
| `weight` | 1 | — | Registro de peso |

> [!WARNING]
> **`abnormal_heart_rate` não são alertas reais.** Apesar do nome, este Key possui relação 1:1 exata com `heart_rate` (ambos 3.575 registros) e inclui valores de BPM perfeitamente normais (55-90 bpm). O campo `prev_bpm` é **sempre 0**. Na prática, é um espelho redundante de `heart_rate`. Para análises, usar apenas `heart_rate` é suficiente.

#### Estrutura detalhada do JSON de sono (`sleep`):

| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `bedtime` | epoch | Horário de deitar |
| `device_bedtime` | epoch | Horário detectado pelo dispositivo |
| `device_wake_up_time` | epoch | Horário de despertar detectado |
| `wake_up_time` | epoch | Horário de despertar (mesmo valor de `device_wake_up_time`) |
| `duration` | int (min) | Duração total do sono em minutos |
| `sleep_deep_duration` | int (min) | Sono profundo |
| `sleep_light_duration` | int (min) | Sono leve |
| `sleep_rem_duration` | int (min) | Sono REM |
| `sleep_awake_duration` | int (min) | Tempo acordado durante o sono |
| `awake_count` | int | Número de vezes que acordou durante a noite |
| `breath_quality` | int (0-100) | Qualidade respiratória do sono |
| `avg_hr` / `min_hr` / `max_hr` | int (bpm) | FC média, mínima e máxima durante o sono |
| `avg_spo2` / `min_spo2` / `max_spo2` | int (%) | SpO2 média, mínima e máxima durante o sono |
| `items` | array | Estágios do sono: `[{"start_time", "end_time", "state"}]` |
| `timezone` | int | Fuso horário (ex: `-12` para UTC-3 no formato interno Xiaomi) |
| `version` | int | Versão do formato de dados (ex: `4`) |
| `sleep_algorithm_version` | int | Versão do algoritmo de detecção de sono (ex: `0`) |
| `protoTime` | epoch | Timestamp duplicado (mesmo valor do campo `Time` do registro) |

> [!TIP]
> Os estágios de sono no campo `items` usam os seguintes códigos para `state`:
> `3` = Sono Leve, `4` = Sono Profundo, `5` = Sono REM, `2` = Acordado.

---

### 2.2 `hlth_center_aggregated_fitness_data.csv` — Dados Agregados Diários
Resumos diários pré-calculados pelo app, consolidando as medições brutas. Contém 382 registros.

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Uid` | int | Mi Account ID |
| `Sid` | string | Identificador da fonte (sempre `default` para dados agregados) |
| `Tag` | string | Categoria primária: `daily_report`, `daily_mark`, ou `daily_fitness` |
| `Key` | string | Subcategoria: `calories`, `heart_rate`, `sleep`, `spo2`, `steps`, `intensity`, `valid_stand`, `weight`, `goal` |
| `Time` | int (epoch) | Timestamp do dia referência (meia-noite UTC) |
| `Value` | string (JSON) | Dados agregados do dia |
| `UpdateTime` | int (epoch) | Última modificação |

#### Combinações `Tag` × `Key` encontradas:

| Tag | Keys disponíveis | Registros | Descrição |
| :--- | :--- | ---: | :--- |
| `daily_report` | `calories`, `heart_rate`, `intensity`, `sleep`, `spo2`, `steps`, `valid_stand` | 177 | Relatório diário completo |
| `daily_mark` | `calories`, `heart_rate`, `intensity`, `sleep`, `spo2`, `steps`, `valid_stand`, `weight` | 178 | Marcação/resumo diário |
| `daily_fitness` | `goal` | 29 | Metas diárias e progresso |

#### Estrutura detalhada do JSON agregado de sono (`daily_report` × `sleep`):

O JSON de sono nos dados agregados possui campos adicionais em relação aos dados brutos, especialmente úteis para correlação com CPAP:

| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `sleep_score` | int (0-100) | Score geral de qualidade do sono (algoritmo Xiaomi) |
| `sleep_stage` | int | Classificação do estágio dominante: `1`=Leve, `2`=Profundo, `3`=REM, `5`=Insuficiente |
| `total_duration` | int (min) | Duração total incluindo cochilos diurnos |
| `day_sleep_evaluation` | int (1-5) | Avaliação do padrão de sono do dia (2=normal, 5=fragmentado com cochilos) |
| `long_sleep_evaluation` | int | Avaliação numérica do sono principal |
| `segment_details` | array | Lista de segmentos de sono (principal + cochilos), cada um com seus próprios `bedtime`, `wake_up_time`, durações por estágio, FC e SpO2 |
| `sleep_deep_duration` | int (min) | Total de sono profundo (consolidado de todos os segmentos) |
| `sleep_light_duration` | int (min) | Total de sono leve |
| `sleep_rem_duration` | int (min) | Total de sono REM |
| `sleep_awake_duration` | int (min) | Total de tempo acordado durante o sono |
| `avg_hr` / `min_hr` / `max_hr` | int (bpm) | FC do sono principal |
| `avg_spo2` / `min_spo2` / `max_spo2` | int (%) | SpO2 do sono principal |

> [!TIP]
> O campo `segment_details` diferencia **sono principal** (com `avg_hr`, `avg_spo2`, durações por estágio) de **cochilos** (sem métricas de FC/SpO2, apenas `bedtime`, `duration`, `wake_up_time`). Para correlação com CPAP, o segmento principal (geralmente o mais longo) é o mais relevante.

---

### 2.3 `hlth_center_data_source.csv` — Fontes de Dados Vinculadas
Cadastro dos dispositivos e aplicativos que geram dados de saúde.

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Uid` | int | Mi Account ID |
| `Sid` | string | Identificador da fonte de dados (chave estrangeira) |
| `Identifier` | string (UUID) | Identificador exclusivo universal |
| `Model` | string | Modelo do dispositivo (ex: `mihlth.xiaomi.fitness.phone`) |
| `Name` | string | Nome padrão (ex: `motorola edge 40 neo`) |
| `Alias` | string | Apelido atribuído pelo usuário |
| `Status` | int | Status de vinculação (1 = wearable desvinculado/inativo, 2 = ativo) |
| `CreateTime` | int (nanoseconds) | Data de criação (⚠️ timestamp em nanosegundos!) |
| `UpdateTime` | int (nanoseconds) | Última atualização (⚠️ timestamp em nanosegundos!) |

> [!WARNING]
> Os campos `CreateTime` e `UpdateTime` neste arquivo usam **nanosegundos** (19 dígitos), diferente dos outros CSVs que usam **segundos** (10 dígitos). É necessário dividir por `1e9` para converter para epoch em segundos.

---

### 2.4 `user_fitness_data_records.csv` — Referências de Objetos de Sono
Contém 24 registros, todos com `tag=object_name`. Cada registro corresponde a uma noite de sono e referencia um objeto de dados armazenado na nuvem Xiaomi. Os timestamps do campo `time` coincidem com os `wake_up_time` dos registros de sono em `hlth_center_fitness_data.csv`. Os `value` são hashes base64 dos objetos remotos.

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `uid` | int | Mi Account ID |
| `tag` | string | Categoria primária (ex: `object_name`) |
| `key` | string | Chave secundária / caminho do objeto |
| `time` | int (epoch) | Timestamp do registro |
| `did` | int | Identificador do dispositivo |
| `value` | string | Valor (pode ser hash/referência de objeto) |
| `metric` | int | Flag de atingimento de meta (0/1) |
| `last_modify` | int (epoch) | Última modificação |

> [!NOTE]
> Os headers deste arquivo usam **snake_case** (minúsculas), diferente da maioria dos outros CSVs que usam CamelCase.

---

### 2.5 `user_fitness_profile.csv` — Perfil de Condicionamento
Parâmetros biológicos e metas diárias do usuário.

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Uid` | int | Mi Account ID |
| `Vo2Max` | int | VO2 Máximo (capacidade cardiorrespiratória) |
| `MaximalMet` | int | MET Máximo |
| `MaxHrm` | int | FC máxima configurada |
| `MinHrm` | int | FC mínima de repouso |
| `RecordMaxHrm` | string (JSON) | FC máxima registrada: `{"hrm":190,"source":"auto"}` |
| `DailyCalGoal` | int | Meta diária de calorias (ex: 500) |
| `DailyStepGoal` | int | Meta diária de passos (ex: 6000) |
| `InitialWeight` | string (JSON) | Peso inicial: `{"weight":87,"timestamp":1776091914}` |
| `ChildAuth` | int | Perfil infantil (0 = não) |
| `InitialTime` | int | Data de criação do perfil |
| `DailyStandGoal` | int | Meta de horas em pé |
| `DailySleepGoal` | int | Meta de duração do sono |
| `RegularGoalList` | string (JSON) | Histórico de metas: `[{"field":2,"target":500},{"field":1,"target":6000},{"field":4,"target":30}]` |

---

### 2.6 `user_member_profile.csv` — Perfil do Membro
Dados pessoais do titular e membros da família.

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Uid` | int | Mi Account ID |
| `Name` | int/string | Nome ou ID do membro |
| `Sex` | string | Gênero (ex: `male`) |
| `Birth` | string (date) | Data de nascimento (ex: `1978-10-28`) |
| `Height` | int | Altura em cm |
| `Weight` | int | Peso em kg |
| `Relation` | string | Região/relação (ex: `br`) |
| `XiaomiId` | int | ID da conta Xiaomi |
| `Region` | string | Região/país (ex: `br`) |
| `SpecialMark` | int | Marcações especiais (0 = nenhuma) |
| `Icon` | string/null | URL do avatar |

---

### 2.7 `user_device_setting.csv` — Configurações de Dispositivos

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Uid` | int | Mi Account ID |
| `Did` | string | Identificador do dispositivo (ex: `xiaomiwear_app`) |
| `Module` | string | Módulo de configuração (ex: `device_setting`) |
| `Key` | string | Chave da configuração (ex: `selectMode`) |
| `Value` | string (JSON) | Valor da configuração |
| `CreateTime` | int (epoch) | Data de criação |
| `UpdateTime` | int (epoch) | Última modificação |

---

### 2.8 `hlth_center_sport_record.csv` — Registros de Exercícios
⬜ **Sem dados na exportação atual.**

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Uid` | int | Mi Account ID |
| `Sid` | string | Identificador da fonte |
| `Key` | string | Subclassificação do esporte |
| `Time` | int (epoch) | Timestamp da sessão |
| `Category` | string | Categoria primária do esporte |
| `Value` | string (JSON) | Métricas da sessão |
| `UpdateTime` | int (epoch) | Última modificação |

> [!NOTE]
> A documentação oficial lista o campo como `categroy` (com erro de digitação). O CSV real usa `Category` (CamelCase, grafia correta).

---

### 2.9 `hlth_center_sport_track_data.csv` — Trajetos GPS
⬜ **Sem dados na exportação atual.**

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Uid` | int | Mi Account ID |
| `Did` | int | Identificador do dispositivo |
| `Key` | string | Tipo de atividade |
| `Time` | int (epoch) | Timestamp de início |
| `UpdateTime` | int (epoch) | Última modificação |
| `GPX` | string (XML) | Dados GPS no formato GPX |

---

### 2.10 `user_fitness_with_uuid_data_records.csv` — Registros com UUID
⬜ **Sem dados na exportação atual.**

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `uid` | int | Mi Account ID |
| `did` | int | Identificador do dispositivo |
| `tag` | string | Categoria primária |
| `key` | string | Categoria secundária |
| `record_id` | string (UUID) | UUID único do registro |
| `time` | int (epoch) | Timestamp |
| `value` | string | Dados de fitness |
| `last_modify` | int (epoch) | Última modificação |

---

### 2.11 `user_health_plan_records.csv` — Planos de Saúde
⬜ **Sem dados na exportação atual.**

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `uid` | int | Mi Account ID |
| `plan_type` | string | Tipo do plano |
| `status` | string | Status (ativo, concluído) |
| `timestamp` | int (epoch) | Data de criação |
| `plan_info` | string (JSON) | Conteúdo/etapas do plano |
| `value` | string | Dados de progresso |
| `desc` | string | Descrição textual |
| `last_modify` | int (epoch) | Última modificação |

---

### 2.12 `user_pk_invite_record.csv` — Convites de Competição (PK)
⬜ **Sem dados na exportação atual.**

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Id` | int | ID do convite |
| `Inviter` | int | Mi Account ID de quem convidou |
| `Invitee` | int | Mi Account ID do convidado |
| `PkId` | int | ID da competição |
| `PkType` | string | Tipo/modalidade |
| `IStatus` | string | Status do convite |
| `ZoneOffset` | string | Fuso horário |
| `CTime` | int (epoch) | Data de criação |
| `UTime` | int (epoch) | Data de atualização |

---

### 2.13 `user_pk_record.csv` — Registros de Competição (PK)
⬜ **Sem dados na exportação atual.**

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Id` | int | ID do registro |
| `Uid` | int | Mi Account ID |
| `PkUid` | int | Mi Account ID do oponente |
| `PkId` | int | ID da competição |
| `PkType` | string | Tipo da disputa |
| `PkStatus` | string | Status (em andamento, concluído) |
| `PkUidPrivacy` | int | Privacidade do oponente |
| `PkStartTime` | int (epoch) | Início da competição |
| `PkEndTime` | int (epoch) | Término da competição |
| `UserZoneOffset` | string | Fuso horário do usuário |
| `PkUserZoneOffset` | string | Fuso horário do oponente |
| `PkSettleTime` | int (epoch) | Data de apuração final |
| `PkScore` | string (JSON) | Placar de ambos |
| `PkResult` | string | Resultado final |
| `CTime` | int (epoch) | Data de criação |
| `UTime` | int (epoch) | Data de atualização |

---

### 2.14 `user_pk_result_statistics.csv` — Estatísticas de Competição
⬜ **Sem dados na exportação atual.**

| Campo | Tipo Real | Descrição |
| :--- | :--- | :--- |
| `Id` | int | ID do registro de estatísticas |
| `Uid` | int | Mi Account ID |
| `PkUid` | int | Mi Account ID do oponente |
| `StatisticsResult` | string (JSON) | Resultados consolidados |
| `CTime` | int (epoch) | Data de criação |
| `UTime` | int (epoch) | Data de atualização |

---

## 3. Arquivos Documentados Mas Ausentes na Exportação

Os seguintes arquivos são descritos na documentação oficial da Xiaomi, mas **não foram gerados** na exportação de 20/05/2026:

| Arquivo | Descrição |
| :--- | :--- |
| `hlthappUserFeedback.csv` | Feedbacks e problemas reportados pelo usuário |
| `hlth_user_course_train_statistics.csv` | Estatísticas de cursos de treinamento |
| `hlth_user_course_train_record.csv` | Registros individuais de sessões de treino |
| `hlth_center_medical_data.csv` | Dados médicos (ECG, pressão arterial) |

---

## 4. Notas Técnicas e Observações

### Timestamps
- **Padrão**: A maioria dos campos de tempo usa **epoch em segundos** (10 dígitos).
- **Exceção**: O arquivo `hlth_center_data_source.csv` usa **epoch em nanosegundos** (19 dígitos) nos campos `CreateTime` e `UpdateTime`.
- **Conversão**: Para converter epoch em segundos para datetime: `datetime.fromtimestamp(epoch_value)`.

### Fonte de Dados Primária

| Sid | Modelo | Nome | Status | Registros |
| :--- | :--- | :--- | :--- | ---: |
| `2105367160` | `miwear.watch.n69gl` | Xiaomi Smart Band 9 Active | 1 (inativo) | 26.127 |
| `hlth.gen_156456619868711` | `mihlth.xiaomi.fitness.phone` | motorola edge 40 neo | 2 (ativo) | 0 |
| `xiaomiwear_app_manually` | `mihlth.xiaomi.fitness.manually` | Add data | 2 (ativo) | 1 |
| `xiaomiwear_app` | `mihlth.xiaomi.fitness.app` | Mi Fitness | 2 (ativo) | 0 |

- O `Sid` predominante (`2105367160`) corresponde ao **dispositivo wearable** (Xiaomi Smart Band 9 Active) — responsável por 99,99% dos registros.
- O `Sid` `xiaomiwear_app_manually` indica dados inseridos manualmente pelo app (apenas 1 registro: peso).
- O `Sid` `default` nos dados agregados indica consolidação pelo servidor.

> [!NOTE]
> O wearable `2105367160` aparece com **Status=1** (possivelmente desvinculado), porém continua sendo a fonte de todos os dados. Isso pode indicar que o dispositivo foi revinculado ou que Status=1 tem semântica diferente para wearables.

### Encoding dos CSVs
- Todos os CSVs utilizam encoding **UTF-8** com separador **vírgula** (`,`).
- Valores JSON estão incorporados como strings dentro das células CSV, com aspas internas escapadas como `""` (CSV standard).

### Relevância para o Projeto CPAP

Os dados mais relevantes para correlação com os dados CPAP são:

| Dado MiFitness | Uso CPAP | Granularidade |
| :--- | :--- | :--- |
| **`sleep`** (bruto) | Comparar duração/estágios com dados do CPAP na mesma noite | Por sessão de sono |
| **`sleep`** (agregado `daily_report`) | `sleep_score`, `segment_details` para qualidade geral | Diário |
| **`spo2`** | SpO2 noturno do wearable vs. métricas do CPAP | ~10 min |
| **`heart_rate`** (bruto) | FC noturna contínua durante uso do CPAP | ~10 min |
| **`resting_heart_rate`** | Tendência de FC repouso como indicador de saúde cardiovascular | Diário |
| **`steps`** / **`calories`** | Nível de atividade diurna → impacto na qualidade do sono | Diário |
