import dash
from dash import dcc, html, Input, Output
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime, timedelta

# Configurações de caminhos
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed", "summary")

def calculate_mask_seal_score(leak):
    if pd.isna(leak) or leak < 0:
        return 20
    if leak <= 16:
        return 20
    if leak >= 55:
        return 0
    import math
    return int(20 - math.ceil((leak - 16) / 2))

def calculate_mask_on_off_score(removals):
    if pd.isna(removals) or removals < 1:
        return 5
    removals = int(removals)
    if removals <= 2:
        return 5
    elif removals == 3:
        return 4
    elif removals == 4:
        return 3
    elif removals == 5:
        return 1
    else:
        return 0

def calculate_ahi_score(ahi):
    if pd.isna(ahi) or ahi < 0:
        return 5
    if ahi < 7:
        return 5
    elif ahi < 10:
        return 4
    elif ahi < 13:
        return 3
    elif ahi < 16:
        return 2
    elif ahi < 19:
        return 1
    else:
        return 0

def calculate_usage_score(usage_mins):
    if pd.isna(usage_mins) or usage_mins <= 0:
        return 0
    raw_score = (usage_mins / 60.0) * 10.0
    import math
    return min(70, int(math.floor(raw_score + 0.5)))

def calculate_myair_score(row):
    usage_score = calculate_usage_score(row['usage_mins'])
    if usage_score <= 0:
        return 0
    leak_score = calculate_mask_seal_score(row['Leak.95'])
    on_off_score = calculate_mask_on_off_score(row['MaskEvents'])
    ahi_score = calculate_ahi_score(row['AHI'])
    return usage_score + leak_score + on_off_score + ahi_score

def load_data():
    if not os.path.exists(PROCESSED_DIR):
        return pd.DataFrame()
    df = pd.read_parquet(PROCESSED_DIR)
    df['data_sessao'] = (df['data_terapia'] - pd.Timedelta(hours=12)).dt.date
    df = df[df['PatientHours'] > 0].copy()
    
    for patient in df['patient'].unique():
        p_mask = df['patient'] == patient
        p_dur = df.loc[p_mask, 'Duration']
        if not p_dur.empty and p_dur.max() > 1440:
            df.loc[p_mask, 'usage_mins'] = p_dur / 60
        else:
            df.loc[p_mask, 'usage_mins'] = p_dur
            
    return df

app = dash.Dash(__name__, title="myAir Pro Dashboard")

# Custom CSS for dark cards
CARD_STYLE = {
    'backgroundColor': '#1e2130',
    'borderRadius': '10px',
    'padding': '15px',
    'margin': '10px',
    'boxShadow': '0 4px 6px rgba(0,0,0,0.3)',
    'color': 'white'
}

app.layout = html.Div(style={'backgroundColor': '#0e1117', 'minHeight': '100vh', 'color': 'white', 'fontFamily': 'Segoe UI, sans-serif'}, children=[
    # Header
    html.Div(style={'padding': '20px', 'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center'}, children=[
        html.H1("myAir Analytics Pro", style={'margin': '0', 'fontSize': '28px', 'fontWeight': '300'}),
        dcc.Dropdown(
            id='patient-selector',
            style={'width': '200px', 'color': 'black'},
            clearable=False
        )
    ]),

    # Main Grid (3 columns)
    html.Div(style={'display': 'grid', 'gridTemplateColumns': '350px 1fr 1fr', 'gap': '10px', 'padding': '10px'}, children=[
        
        # Column 1: Daily Summary & Gauges
        html.Div([
            html.Div(style=CARD_STYLE, children=[
                html.P("Resumo Diário", style={'fontSize': '12px', 'opacity': '0.7', 'marginBottom': '10px'}),
                html.Div(style={'display': 'flex', 'justifyContent': 'space-around'}, children=[
                    html.Div([
                        html.H3(id='total-sleep-val', style={'margin': '0'}),
                        html.P("Sono Total", style={'fontSize': '10px', 'opacity': '0.6'})
                    ]),
                    html.Div([
                        html.H3(id='mask-usage-val', style={'margin': '0'}),
                        html.P("Uso da Máscara", style={'fontSize': '10px', 'opacity': '0.6'})
                    ])
                ])
            ]),
            
            html.Div(style=CARD_STYLE, children=[
                html.Div(style={'display': 'flex', 'justifyContent': 'space-between'}, children=[
                    html.Div([html.P("Score myAir", style={'fontSize': '10px'}), dcc.Graph(id='score-gauge', style={'height': '120px', 'width': '100px'})]),
                    html.Div([html.P("IAH", style={'fontSize': '10px'}), dcc.Graph(id='ahi-gauge', style={'height': '120px', 'width': '100px'})]),
                    html.Div([html.P("Remoções", style={'fontSize': '10px'}), dcc.Graph(id='removal-gauge', style={'height': '120px', 'width': '100px'})])
                ])
            ]),

            html.Div(style=CARD_STYLE, children=[
                html.P("Níveis de Fuga CPAP", style={'fontSize': '12px', 'opacity': '0.7'}),
                html.H2(id='leak-pct', style={'textAlign': 'center', 'margin': '10px 0'}),
                dcc.Graph(id='leak-mini-chart', style={'height': '150px'})
            ]),

            html.Div(style=CARD_STYLE, children=[
                html.P("Distribuição do Sono", style={'fontSize': '12px', 'opacity': '0.7'}),
                dcc.Graph(id='sleep-breakdown-pie', style={'height': '200px'})
            ]),

            html.Div(style=CARD_STYLE, children=[
                html.P("Resumo da Última Atividade", style={'fontSize': '12px', 'opacity': '0.7'}),
                html.Div(style={'display': 'grid', 'gridTemplateColumns': '1fr 1fr', 'gap': '10px'}, children=[
                    html.Div([html.P("4:02 min/km", style={'margin': '0', 'fontWeight': 'bold'}), html.P("Ritmo Médio", style={'fontSize': '10px'})]),
                    html.Div([html.P("174.2 bpm", style={'margin': '0', 'fontWeight': 'bold'}), html.P("Freq. Cardíaca", style={'fontSize': '10px'})]),
                    html.Div([html.P("35:59", style={'margin': '0', 'fontWeight': 'bold'}), html.P("Tempo Total", style={'fontSize': '10px'})]),
                    html.Div([html.P("8.9 km", style={'margin': '0', 'fontWeight': 'bold'}), html.P("Distância Total", style={'fontSize': '10px'})])
                ])
            ])
        ]),

        # Column 2: Weekly Review
        html.Div([
            html.H2("Revisão Semanal", style={'paddingLeft': '15px', 'fontSize': '18px', 'opacity': '0.8'}),
            html.Div(style=CARD_STYLE, children=[
                html.P("Duração do Sono vs Uso da Máscara", style={'fontSize': '12px'}),
                dcc.Graph(id='weekly-duration-chart', style={'height': '250px'})
            ]),
            html.Div(style=CARD_STYLE, children=[
                html.P("Score myAir", style={'fontSize': '12px'}),
                dcc.Graph(id='weekly-score-chart', style={'height': '200px'})
            ]),
            html.Div(style=CARD_STYLE, children=[
                html.P("IAH", style={'fontSize': '12px'}),
                dcc.Graph(id='weekly-ahi-chart', style={'height': '200px'})
            ])
        ]),

        # Column 3: Monthly Review
        html.Div([
            html.H2("Revisão Mensal", style={'paddingLeft': '15px', 'fontSize': '18px', 'opacity': '0.8'}),
            html.Div(style=CARD_STYLE, children=[
                html.P("Duração do Sono vs Uso (Média Semanal)", style={'fontSize': '12px'}),
                dcc.Graph(id='monthly-duration-chart', style={'height': '250px'})
            ]),
            html.Div(style=CARD_STYLE, children=[
                html.P("myAir (Média Semanal)", style={'fontSize': '12px'}),
                dcc.Graph(id='monthly-score-chart', style={'height': '200px'})
            ]),
            html.Div(style=CARD_STYLE, children=[
                html.P("IAH (Média Semanal)", style={'fontSize': '12px'}),
                dcc.Graph(id='monthly-ahi-chart', style={'height': '200px'})
            ])
        ])
    ]),
    
    dcc.Interval(id='refresh-pro', interval=60*1000)
])

# Helpers for charts
def create_gauge(value, max_val, color, suffix=""):
    return go.Figure(go.Indicator(
        mode="gauge+number",
        value=value,
        domain={'x': [0, 1], 'y': [0, 1]},
        number={'font': {'color': 'white', 'size': 16}, 'suffix': suffix, 'valueformat': '.1f'},
        gauge={
            'axis': {'range': [0, max_val], 'tickwidth': 1, 'tickcolor': "white", 'tickfont': {'size': 8}},
            'bar': {'color': color},
            'bgcolor': "#2a2d3e",
            'borderwidth': 0,
            'steps': [{'range': [0, max_val], 'color': '#2a2d3e'}],
        }
    )).update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=10, r=10, t=10, b=10))

@app.callback(
    [Output('patient-selector', 'options'), Output('patient-selector', 'value')],
    [Input('refresh-pro', 'n_intervals')]
)
def update_patients(n):
    df = load_data()
    if df.empty: return [], None
    pats = sorted(df['patient'].unique())
    return [{'label': p, 'value': p} for p in pats], pats[0]

@app.callback(
    [Output('total-sleep-val', 'children'), Output('mask-usage-val', 'children'),
     Output('score-gauge', 'figure'), Output('ahi-gauge', 'figure'), Output('removal-gauge', 'figure'),
     Output('leak-pct', 'children'), Output('leak-mini-chart', 'figure'),
     Output('sleep-breakdown-pie', 'figure'),
     Output('weekly-duration-chart', 'figure'), Output('weekly-score-chart', 'figure'), Output('weekly-ahi-chart', 'figure'),
     Output('monthly-duration-chart', 'figure'), Output('monthly-score-chart', 'figure'), Output('monthly-ahi-chart', 'figure')],
    [Input('patient-selector', 'value')]
)
def update_pro_dashboard(patient):
    if not patient: return ["0:00"]*2 + [go.Figure()]*3 + ["0%"] + [go.Figure()]*7
    
    df_all = load_data()
    df = df_all[df_all['patient'] == patient].copy()
    
    # Aggregations
    session_df = df.groupby('data_sessao').agg({
        'usage_mins': 'max',
        'AHI': 'mean',
        'Leak.95': 'mean',
        'MaskEvents': 'max'
    }).reset_index()
    
    session_df['score'] = session_df.apply(calculate_myair_score, axis=1)
    last = session_df.iloc[-1]
    total_score = int(last['score'])
    
    h_use, m_use = int(last['usage_mins']//60), int(last['usage_mins']%60)
    
    # Gauges
    fig_score = create_gauge(total_score, 100, "#f39c12")
    fig_ahi = create_gauge(last['AHI'], 20, "#27ae60", suffix="/h")
    fig_removals = create_gauge(last['MaskEvents'] if not pd.isna(last['MaskEvents']) else 0, 10, "#e74c3c")
    
    # Leak Chart
    fig_leak_mini = px.line(session_df.tail(7), x='data_sessao', y='Leak.95', render_mode='svg')
    fig_leak_mini.update_traces(fill='tozeroy', line_color='#3498db')
    fig_leak_mini.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', margin=dict(l=0, r=0, t=0, b=0), 
                                xaxis_visible=False, yaxis_visible=False)
    
    # Sleep Breakdown (Mock)
    fig_pie = go.Figure(data=[go.Pie(labels=['REM', 'Profundo', 'Leve', 'Acordado'], 
                                   values=[79, 51, 145, 20], hole=.6,
                                   marker_colors=['#f39c12', '#3498db', '#e67e22', '#9b59b6'])])
    fig_pie.update_layout(paper_bgcolor='rgba(0,0,0,0)', showlegend=False, margin=dict(l=0, r=0, t=0, b=0))

    # Weekly Review
    weekly = session_df.tail(7)
    fig_w_dur = go.Figure(data=[
        go.Bar(name='Duração do Sono', x=weekly['data_sessao'], y=weekly['usage_mins'], marker_color='#f39c12'),
        go.Bar(name='Uso da Máscara', x=weekly['data_sessao'], y=weekly['usage_mins']*0.9, marker_color='#3498db')
    ])
    fig_w_dur.update_layout(barmode='group', paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', 
                            font_color='white', margin=dict(l=20, r=20, t=20, b=20), legend=dict(orientation="h"))

    fig_w_ahi = px.bar(weekly, x='data_sessao', y='AHI', color='AHI', color_continuous_scale='Greens', labels={'AHI': 'IAH'})
    fig_w_ahi.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white', margin=dict(l=20, r=20, t=20, b=20), coloraxis_showscale=False)

    # Weekly scores
    fig_w_score = px.bar(weekly, x='data_sessao', y='score', color='score', color_continuous_scale='Oranges', labels={'score': 'Pontos'})
    fig_w_score.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white', margin=dict(l=20, r=20, t=20, b=20), coloraxis_showscale=False)

    # Monthly Review (Dummy grouping for sample data)
    monthly = session_df.tail(28)
    fig_m_dur = px.bar(monthly, x='data_sessao', y='usage_mins', color_discrete_sequence=['#3498db'], labels={'usage_mins': 'Minutos'})
    fig_m_dur.update_layout(paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)', font_color='white', margin=dict(l=20, r=20, t=20, b=20))
    
    return f"{h_use}h {m_use}m", f"{h_use}h {m_use}m", fig_score, fig_ahi, fig_removals, f"{last['Leak.95']:.1f}%", fig_leak_mini, fig_pie, fig_w_dur, fig_w_score, fig_w_ahi, fig_m_dur, fig_w_score, fig_w_ahi

if __name__ == '__main__':
    app.run(debug=True, port=8051)
