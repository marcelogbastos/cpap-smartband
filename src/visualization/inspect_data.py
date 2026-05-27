import pandas as pd
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed", "summary")

def inspect():
    if not os.path.exists(PROCESSED_DIR):
        print("Dados processados não encontrados.")
        return

    # Lê todos os dados particionados
    df = pd.read_parquet(PROCESSED_DIR)
    
    # Ordena por paciente e data
    df = df.sort_values(['patient', 'data_terapia'])
    
    print("\n=== Resumo dos Dados Processados ===")
    print(f"Total de registros: {len(df)}")
    print(f"Pacientes encontrados: {df['patient'].unique().tolist()}")
    
    # Colunas comuns em arquivos ResMed STR.edf
    # Elas podem variar dependendo do modelo, mas geralmente incluem Usage, AHI, Leak
    cols = ['data_terapia', 'patient', 'Usage', 'AHI', 'Leak', 'MaskLeak', 'EventsPerHr']
    available_cols = [c for c in cols if c in df.columns]
    
    print("\n--- Amostra de Dados (últimos 5 dias por paciente) ---")
    for patient in df['patient'].unique():
        patient_df = df[df['patient'] == patient].tail(5)
        print(f"\nPaciente: {patient}")
        print(patient_df[available_cols].to_string(index=False))

if __name__ == "__main__":
    inspect()
