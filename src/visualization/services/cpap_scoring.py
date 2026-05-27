import math
import pandas as pd

def calculate_mask_seal_score(leak):
    if pd.isna(leak) or leak < 0:
        return 20
    if leak <= 16:
        return 20
    if leak >= 55:
        return 0
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
    return min(70, int(round(raw_score)))

def calculate_myair_score(row):
    usage_score = calculate_usage_score(row.get('usage_mins', 0))
    if usage_score <= 0:
        return 0
    leak_score = calculate_mask_seal_score(row.get('Leak.95', 0))
    on_off_score = calculate_mask_on_off_score(row.get('MaskEvents', 0))
    ahi_score = calculate_ahi_score(row.get('AHI', 0))
    return usage_score + leak_score + on_off_score + ahi_score
