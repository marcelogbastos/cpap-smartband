import pandas as pd
import os

PROCESSED_DIR = "data/processed/summary"

def generate_summary():
    if not os.path.exists(PROCESSED_DIR):
        return "Dados não processados."

    df = pd.read_parquet(PROCESSED_DIR)
    # Adiciona data da sessão (lógica de meio-dia a meio-dia)
    # Isso garante que uma noite que começa às 22h e termina às 06h do dia seguinte seja agrupada como uma única sessão.
    df['data_sessao'] = (df['data_terapia'] - pd.Timedelta(hours=12)).dt.date
    
    # Filtra apenas dias com uso real (PatientHours > 0)
    # Alguns registros no STR.edf podem ser placeholders
    df_used = df[df['PatientHours'] > 0].copy()
    
    summary = []
    for patient in df['patient'].unique():
        p_df = df_used[df_used['patient'] == patient]
        if p_df.empty:
            summary.append(f"### {patient}\nNenhum dado de uso efetivo encontrado.")
            continue
            
        # 1. Dados da Última Noite (Sessão mais recente)
        last_session_date = p_df['data_sessao'].max()
        p_night_df = p_df[p_df['data_sessao'] == last_session_date]
        
        # Uso da noite: Heurística para Duration (minutos) vs PatientHours (segundos)
        # Se 'Duration' for razoável para uma noite (ex: 30 a 1000 min), usamos ele.
        # Caso contrário, usamos PatientHours.
        raw_duration = p_night_df['Duration'].iloc[0] if 'Duration' in p_night_df.columns else 0
        if 30 <= raw_duration <= 1440:
            # Parece estar em minutos (caso Marcelo)
            usage_mins = raw_duration
        else:
            # Caso João: PatientHours em segundos
            total_sec = p_night_df['PatientHours'].sum()
            usage_mins = total_sec / 60

        usage_h = int(usage_mins // 60)
        usage_m = int(usage_mins % 60)
        
        ahi_night = p_night_df['AHI'].iloc[0]
        leak_night = p_night_df['Leak.95'].iloc[0] if 'Leak.95' in p_night_df.columns else 0
        press_night = p_night_df['BlowPress.95'].iloc[0] if 'BlowPress.95' in p_night_df.columns else 0
        
        # 2. Dados do Período (Averages/Compliance)
        total_days = p_df['data_sessao'].nunique()
        # Dias 4h+ (240 minutos)
        # Para cada sessão, somamos a duração
        daily_usage = p_df.groupby('data_sessao')['Duration'].max() # Heurística: usa o max se for cumulativo
        # Se o max for muito baixo, tenta a soma de PatientHours
        if daily_usage.max() < 30: 
             daily_usage = p_df.groupby('data_sessao')['PatientHours'].sum() / 60
             
        days_4h_plus = (daily_usage >= 240).sum()
        avg_usage_h = daily_usage.mean() / 60
        total_usage_h = daily_usage.sum() / 60
        
        # Médias clínicas (últimos registros costumam conter os acumulados do aparelho)
        p_last = p_df.iloc[-1]
        ahi_period = p_last['AHI']
        ai_total = p_last['AI'] if 'AI' in p_last else 0
        ai_central = p_last['CAI'] if 'CAI' in p_last else 0
        leak_period = p_last['Leak.95'] if 'Leak.95' in p_last else 0
        press_period = p_last['BlowPress.95'] if 'BlowPress.95' in p_last else 0

        s = f"### Paciente: {patient}\n"
        s += f"#### Relatório da Última Noite (Sessão: {last_session_date.strftime('%d/%m/%Y')})\n"
        s += f"- **Horas de Uso**: {usage_h}:{usage_m:02d}\n"
        s += f"- **Eventos por hora (IAH)**: {ahi_night:.1f}\n"
        s += f"- **Vedação da Máscara**: {'Bom' if leak_night < 24 else 'Ajustar'}\n"
        s += f"- **Umidificador**: {'Ativo' if p_night_df['Humidifier'].iloc[0] > 0 else 'Desligado'}\n"
        s += f"- **Pressão (95%)**: {press_night:.1f} cmH2O\n"
        
        s += f"\n#### Resumo do Período\n"
        s += f"- **Dias de Uso**: {total_days}/{total_days}\n"
        s += f"- **Dias 4h+**: {days_4h_plus}/{total_days}\n"
        s += f"- **Média de Uso**: {avg_usage_h:.1f} horas\n"
        s += f"- **Horas de Uso Total**: {total_usage_h:.1f} horas\n"
        s += f"- **Pressão Média (95%)**: {press_period:.1f} cmH2O\n"
        s += f"- **Fuga Média (95%)**: {leak_period:.1f} L/min\n"
        s += f"- **IAH Médio**: {ahi_period:.1f}\n"
        s += f"- **IA Total**: {ai_total:.1f}\n"
        s += f"- **IA Central**: {ai_central:.1f}\n"
        summary.append(s)
    
    return "\n".join(summary)

if __name__ == "__main__":
    print(generate_summary())
