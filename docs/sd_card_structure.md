# Estrutura de Arquivos do Cartão SD (ResMed AirSense)

Este documento descreve a organização técnica dos dados armazenados nos cartões SD dos dispositivos CPAP ResMed, conforme analisado no diretório `data/cpap_sd`.

## 1. Visão Geral da Raiz
Cada diretório de usuário (ex: `João/`, `Marcelo/`) simula a raiz de um cartão SD.

- **`Identification.tgt`**: Arquivo binário de identificação do dispositivo (Nº de série, modelo).
- **`Identification.crc`**: Checksum para validação do arquivo de identificação.
- **`STR.edf`**: (Statistics) Resumo estatístico da terapia no formato European Data Format. É o arquivo que contém as métricas consolidadas usadas para gerar relatórios de conformidade.

## 2. Diretório `DATALOG/`
Este diretório armazena os dados de alta resolução (dados "Full Data") necessários para análise clínica detalhada.

### Organização Cronológica
Os dados são divididos em subpastas nomeadas por data: `YYYYMMDD`.

### Tipos de Arquivos (.edf)
Dentro de cada pasta de data, os arquivos seguem o padrão `YYYYMMDD_HHMMSS_TIPO.edf`:

| Sufixo | Nome Completo | Descrição |
| :--- | :--- | :--- |
| **BRP** | Breath-to-Breath | Fluxo e pressão em alta resolução (aprox. 25Hz). Permite visualizar a curva respiratória. |
| **EVE** | Events | Log de eventos respiratórios (Apneias, Hipopneias, Roncos) com timestamp preciso. |
| **PLD** | Pulse/Detailed | Dados de oximetria e pulso (se utilizado sensor SpO2) ou dados de fluxo detalhados. |
| **SAD** | Summary Data | Dados resumidos e médias de sinais durante a sessão. |
| **CSL** | Control/Log | Registros de início, interrupção e fim das sessões de terapia. |

## 3. Diretório `SETTINGS/`
Contém as configurações clínicas e registros de sistema do aparelho.

- **Arquivos `.tgt`**: Configurações de pressão (fina/variável), alívio expiratório (EPR), configurações de conforto (Rampa, Umidificação) e tipo de máscara.
- **Arquivos `.log`**:
    - `ERR.log`: Log de erros de hardware ou sistema.
    - `DLL.log`: Registro de histórico de downloads/leituras do cartão.
    - `ABR.log`, `ELI.log`: Logs internos do sistema operacional do dispositivo.

## 4. Considerações para Análise de Dados
- **EDF Standard**: O formato EDF é amplamente utilizado em medicina do sono. Bibliotecas como `pyedflib` ou `mne` podem ser usadas para extrair os sinais.
- **Fuso Horário**: Os timestamps nos nomes dos arquivos referem-se ao horário de início da gravação configurado no dispositivo.
- **Integridade**: A ausência dos arquivos `.crc` correspondentes pode impedir a leitura dos dados por softwares oficiais (ResScan) ou de terceiros (OSCAR).
