"""Utilitários compartilhados do projeto cpap_smartband."""

import unicodedata


def normalize_patient_name(name: str) -> str:
    """Normaliza o nome do paciente para uso em caminhos de arquivo.

    Remove acentos e converte para minúsculas com underscores.

    Args:
        name: Nome do paciente (ex: 'Marcelo', 'João Silva')

    Returns:
        Slug normalizado (ex: 'marcelo', 'joao_silva').
    """
    return "".join(
        c for c in unicodedata.normalize("NFD", name)
        if unicodedata.category(c) != "Mn"
    ).lower().replace(" ", "_")
