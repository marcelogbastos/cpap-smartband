"""
Limpeza de tabelas mifitness_* legadas.

O processador antigo gerava tabelas com prefixo 'mifitness_'.
O processador atual (smartband_processor.py) gera apenas tabelas 'smartband_*'.
As tabelas mifitness_* em data/processed/ são orphaned (sem endpoints na API).

Execute este script UMA VEZ para remover os dados duplicados:
    python scripts/cleanup_legacy_tables.py

Para apenas listar sem apagar, use:
    python scripts/cleanup_legacy_tables.py --dry-run
"""

import os
import shutil
import argparse

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")

LEGACY_TABLES = [
    "mifitness_activity",
    "mifitness_profile",
    "mifitness_sleep",
    "mifitness_sleep_daily",
    "mifitness_vitals",
]


def main(dry_run: bool = False):
    if not os.path.exists(PROCESSED_DIR):
        print(f"Diretório não encontrado: {PROCESSED_DIR}")
        return

    found_any = False
    for table in LEGACY_TABLES:
        table_path = os.path.join(PROCESSED_DIR, table)
        if os.path.exists(table_path):
            found_any = True
            if dry_run:
                print(f"[DRY-RUN] Removeria: {table_path}")
            else:
                shutil.rmtree(table_path)
                print(f"Removido: {table_path}")

    if not found_any:
        print("Nenhuma tabela legada encontrada. Nada a limpar.")
    elif not dry_run:
        print("\nLimpeza concluída. Rode update_data.ps1 para regenerar apenas as tabelas smartband_*.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Remove tabelas mifitness_* legadas de data/processed/")
    parser.add_argument("--dry-run", action="store_true", help="Apenas lista o que seria removido, sem apagar.")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
