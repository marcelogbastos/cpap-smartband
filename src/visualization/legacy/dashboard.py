import dash
from dash import dcc, html, dash_table, Input, Output, State
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime, timedelta

# Configurações de caminhos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed", "summary")

def load_data():
    if not os.path.exists(PROCESSED_DIR):
        return pd.DataFrame()
    
    df = pd.read_parquet(PROCESSED_DIR)
    # Lógica de Sessão (Noon-to-Noon)
    df['data_sessao'] = (df['data_terapia'] - pd.Timedelta(hours=12)).dt.date
    # Filtra apenas registros com uso
    df = df[df['PatientHours'] > 0].copy()
    
    # Heurística de conversão de unidades para Duration
    # Se para um paciente a maioria dos Duration está > 1440, é segundos.
    for patient in df['patient'].unique():
        p_mask = df['patient'] == patient
        p_dur = df.loc[p_mask, 'Duration']
        if not p_dur.empty and p_dur.max() > 1440:
            df.loc[p_mask, 'Duration_hrs'] = p_dur / 3600
        else:
            df.loc[p_mask, 'Duration_hrs'] = p_dur / 60
            
    return df

app = dash.Dash(__name__, title="CPAP Analytics Dashboard")

# Layout
app.layout = html.Div(style={'backgroundColor': '#f8f9fa', 'minHeight': '100vh', 'fontFamily': 'Inter, sans-serif'}, children=[
    # Header
    html.Div(style={'backgroundColor': '#2c3e50', 'padding': '20px', 'color': 'white', 'boxShadow': '0 2px 4px rgba(0,0,0,0.1)'}, children=[
        html.H1("CPAP Analytics Dashboard", style={'margin': '0', 'fontSize': '24px'}),
        html.P("Análise Clínica de Terapia de Sono", style={'margin': '5px 0 0', 'opacity': '0.8'})
    ]),
    
    # Controls
    html.Div(style={'padding': '20px', 'display': 'flex', 'gap': '20px', 'alignItems': 'center'}, children=[
        html.Div(style={'flex': '1'}, children=[
            html.Label("Selecione o Paciente:", style={'fontWeight': 'bold', 'marginBottom': '5px', 'display': 'block'}),
            dcc.Dropdown(
                id='patient-selector',
                placeholder="Escolha um paciente",
                style={'width': '100%'}
            )
        ]),
        html.Div(id='date-range-info', style={'paddingTop': '25px', 'color': '#666'})
    ]),
    
    # KPI Cards
    html.Div(id='kpi-container', style={'display': 'grid', 'gridTemplateColumns': 'repeat(auto-fit, minmax(200px, 1fr))', 'gap': '20px', 'padding': '0 20px 20px'}),
    
    # Charts Row 1
    html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '20px', 'padding': '0 20px 20px'}, children=[
        html.Div(style={'backgroundColor': 'white', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)'}, children=[
            html.H3("Tendência de IAH (Eventos/h)", style={'fontSize': '18px', 'marginBottom': '15px'}),
            dcc.Graph(id='ahi-trend-chart')
        ]),
        html.Div(style={'backgroundColor': 'white', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)'}, children=[
            html.H3("Horas de Uso Diário", style={'fontSize': '18px', 'marginBottom': '15px'}),
            dcc.Graph(id='usage-trend-chart')
        ])
    ]),
    
    # Charts Row 2
    html.Div(style={'padding': '0 20px 20px'}, children=[
        html.Div(style={'backgroundColor': 'white', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)'}, children=[
            html.H3("Pressão (95%) e Fuga (95%)", style={'fontSize': '18px', 'marginBottom': '15px'}),
            dcc.Graph(id='pressure-leak-chart')
        ])
    ]),
    
    # Data Table
    html.Div(style={'padding': '0 20px 40px'}, children=[
        html.Div(style={'backgroundColor': 'white', 'padding': '20px', 'borderRadius': '8px', 'boxShadow': '0 2px 4px rgba(0,0,0,0.05)'}, children=[
            html.H3("Detalhamento de Sessões", style={'fontSize': '18px', 'marginBottom': '15px'}),
            dash_table.DataTable(
                id='session-table',
                style_table={'overflowX': 'auto'},
                style_header={'backgroundColor': '#f8f9fa', 'fontWeight': 'bold'},
                style_cell={'textAlign': 'left', 'padding': '10px'},
                page_size=10
            )
        ])
    ]),
    
    dcc.Interval(id='refresh-interval', interval=60*1000, n_intervals=0) # Auto-refresh a cada minuto
])

def create_kpi_card(label, value, unit, color="#2c3e50"):
    return html.Div(style={
        'backgroundColor': 'white', 
        'padding': '20px', 
        'borderRadius': '8px', 
        'boxShadow': '0 2px 4px rgba(0,0,0,0.05)',
        'borderLeft': f'5px solid {color}'
    }, children=[
        html.P(label, style={'margin': '0', 'fontSize': '14px', 'color': '#666', 'textTransform': 'uppercase'}),
        html.Div(style={'display': 'flex', 'alignItems': 'baseline', 'gap': '5px'}, children=[
            html.H2(value, style={'margin': '5px 0', 'fontSize': '28px', 'color': color}),
            html.Span(unit, style={'fontSize': '14px', 'color': '#888'})
        ])
    ])

@app.callback(
    [Output('patient-selector', 'options'),
     Output('patient-selector', 'value')],
    [Input('refresh-interval', 'n_intervals')]
)
def update_patient_list(n):
    df = load_data()
    if df.empty:
        return [], None
    patients = sorted(df['patient'].unique())
    options = [{'label': p, 'value': p} for p in patients]
    return options, patients[0] if patients else None

@app.callback(
    [Output('kpi-container', 'children'),
     Output('ahi-trend-chart', 'figure'),
     Output('usage-trend-chart', 'figure'),
     Output('pressure-leak-chart', 'figure'),
     Output('session-table', 'data'),
     Output('session-table', 'columns'),
     Output('date-range-info', 'children')],
    [Input('patient-selector', 'value')]
)
def update_dashboard(patient):
    if not patient:
        return [], {}, {}, {}, [], [], ""
    
    df_all = load_data()
    df = df_all[df_all['patient'] == patient].copy()
    df = df.sort_values('data_terapia')
    
    # Agrupamento por Sessão
    # Para o dashboard, queremos uma linha por noite
    session_df = df.groupby('data_sessao').agg({
        'Duration_hrs': 'max', # Heurística: se for cumulativo no STR.edf, o max é o total da noite
        'AHI': 'mean',
        'AI': 'mean',
        'CAI': 'mean',
        'BlowPress.95': 'max',
        'Leak.95': 'mean',
        'Humidifier': 'max'
    }).reset_index()
    
    # Heurística extra: se o Duration_hrs médio for muito baixo (ex: < 1h), 
    # talvez as amostras no EDF fossem intervalos e não cumulativos.
    if session_df['Duration_hrs'].mean() < 1:
        # Tenta a soma dos PatientHours
        df['PH_hrs'] = df['PatientHours'] / 3600 if df['PatientHours'].max() > 1440 else df['PatientHours'] / 60
        session_df['Duration_hrs'] = df.groupby('data_sessao')['PH_hrs'].sum().values

    # KPI - Última Noite
    last_night = session_df.iloc[-1]
    ahi_color = "#27ae60" if last_night['AHI'] < 5 else "#f39c12" if last_night['AHI'] < 15 else "#e74c3c"
    usage_color = "#27ae60" if last_night['Duration_hrs'] >= 4 else "#e74c3c"
    
    kpis = [
        create_kpi_card("Uso Última Noite", f"{int(last_night['Duration_hrs'])}h {int((last_night['Duration_hrs']%1)*60)}m", "", usage_color),
        create_kpi_card("IAH Última Noite", f"{last_night['AHI']:.1f}", "eventos/h", ahi_color),
        create_kpi_card("IA Central", f"{last_night['CAI']:.1f}", "eventos/h", "#2980b9"),
        create_kpi_card("Pressão (95%)", f"{last_night['BlowPress.95']:.1f}", "cmH2O"),
        create_kpi_card("Fuga (95%)", f"{last_night['Leak.95']:.1f}", "L/min", "#7f8c8d")
    ]
    
    # Charts
    fig_ahi = px.bar(session_df, x='data_sessao', y='AHI', color='AHI',
                     color_continuous_scale=[[0, "#27ae60"], [0.33, "#f39c12"], [1, "#e74c3c"]],
                     labels={'data_sessao': 'Data', 'AHI': 'IAH'})
    fig_ahi.update_layout(margin=dict(l=0, r=0, t=0, b=0), showlegend=False, coloraxis_showscale=False)
    
    fig_usage = px.line(session_df, x='data_sessao', y='Duration_hrs', markers=True,
                        labels={'data_sessao': 'Data', 'Duration_hrs': 'Horas'})
    fig_usage.add_hline(y=4, line_dash="dash", line_color="red", annotation_text="Meta 4h")
    fig_usage.update_layout(margin=dict(l=0, r=0, t=0, b=0), yaxis_range=[0, max(10, session_df['Duration_hrs'].max() + 2)])
    
    fig_leak = go.Figure()
    fig_leak.add_trace(go.Scatter(x=session_df['data_sessao'], y=session_df['BlowPress.95'], name="Pressão (95%)", line=dict(color='#2980b9')))
    fig_leak.add_trace(go.Scatter(x=session_df['data_sessao'], y=session_df['Leak.95'], name="Fuga (95%)", line=dict(color='#7f8c8d'), yaxis="y2"))
    fig_leak.update_layout(
        margin=dict(l=0, r=0, t=0, b=0),
        yaxis=dict(title="Pressão (cmH2O)", color="#2980b9"),
        yaxis2=dict(title="Fuga (L/min)", color="#7f8c8d", overlaying="y", side="right"),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    
    # Table Data
    table_data = session_df.sort_values('data_sessao', ascending=False).to_dict('records')
    table_cols = [
        {"name": "Data", "id": "data_sessao"},
        {"name": "Uso (h)", "id": "Duration_hrs", "type": "numeric", "format": {"specifier": ".2f"}},
        {"name": "IAH", "id": "AHI", "type": "numeric", "format": {"specifier": ".1f"}},
        {"name": "IA Central", "id": "CAI", "type": "numeric", "format": {"specifier": ".1f"}},
        {"name": "Pressão (95%)", "id": "BlowPress.95", "type": "numeric", "format": {"specifier": ".1f"}},
        {"name": "Fuga (95%)", "id": "Leak.95", "type": "numeric", "format": {"specifier": ".1f"}}
    ]
    
    date_info = f"Dados de {session_df['data_sessao'].min().strftime('%d/%m/%Y')} até {session_df['data_sessao'].max().strftime('%d/%m/%Y')}"
    
    return kpis, fig_ahi, fig_usage, fig_leak, table_data, table_cols, date_info

if __name__ == '__main__':
    print("\nIniciando Dashboard em http://127.0.0.1:8050")
    app.run(debug=True, port=8050)
