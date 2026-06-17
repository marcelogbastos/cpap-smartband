import math
from typing import Optional
import pandas as pd

def calculate_mask_seal_score(leak: Optional[float]) -> int:
    """Calcula pontuação de vedação da máscara a partir do vazamento (Leak 95%).

    Args:
        leak: Valor do vazamento em L/min.

    Returns:
        Inteiro com a pontuação (0-20).
    """
    if pd.isna(leak) or leak is None or leak < 0:
        return 20
    if leak <= 16:
        return 20
    if leak >= 55:
        return 0
    return int(20 - math.ceil((leak - 16) / 2))

def calculate_mask_on_off_score(removals: Optional[float]) -> int:
    """Pontuação baseada no número de remoções da máscara durante a sessão.

    Args:
        removals: Número de eventos de remoção.

    Returns:
        Pontuação de 0 a 5.
    """
    if pd.isna(removals) or removals is None or removals < 1:
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

def calculate_ahi_score(ahi: Optional[float]) -> int:
    """Calcula pontuação a partir do índice AHI (eventos/hora).

    Args:
        ahi: Índice de apneia-hipopneia.

    Returns:
        Pontuação de 0 a 5.
    """
    if pd.isna(ahi) or ahi is None or ahi < 0:
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

def calculate_usage_score(usage_mins: Optional[float]) -> int:
    """Calcula pontuação baseada nas horas de uso do CPAP.

    Args:
        usage_mins: Minutos de uso da sessão.

    Returns:
        Pontuação (0-70) proporcional ao tempo de uso.
    """
    if pd.isna(usage_mins) or usage_mins is None or usage_mins <= 0:
        return 0
    raw_score = (usage_mins / 60.0) * 10.0
    return min(70, int(round(raw_score)))

def calculate_myair_score(row: pd.Series) -> int:
    """Calcula o score myAir a partir de uma linha (Series) de dados CPAP.

    Args:
        row: `pandas.Series` contendo colunas como `usage_mins`, `Leak.95`, `MaskEvents`, `AHI`.

    Returns:
        Inteiro representando o score combinado.
    """
    usage_score = calculate_usage_score(row.get('usage_mins', 0))
    if usage_score <= 0:
        return 0
    leak_score = calculate_mask_seal_score(row.get('Leak.95', 0))
    on_off_score = calculate_mask_on_off_score(row.get('MaskEvents', 0))
    ahi_score = calculate_ahi_score(row.get('AHI', 0))
    return usage_score + leak_score + on_off_score + ahi_score
