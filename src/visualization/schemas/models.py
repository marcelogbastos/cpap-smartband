from pydantic import BaseModel
from typing import List, Dict, Any, Optional


class KPIData(BaseModel):
    usage_mins: float
    ahi: float
    leak: float
    score: int
    mask_events: float
    leak_95: float = 0
    mask_on_off: float = 0
    pressure: float = 0


class PatientDataResponse(BaseModel):
    kpis: KPIData
    timeseries: Dict[str, List[Any]]


class SmartbandDataResponse(BaseModel):
    sleep: Dict[str, List[Any]]
    activity: Dict[str, List[Any]]


class SleepRow(BaseModel):
    report_date: str
    total_duration_min: float
    rem_min: float
    deep_min: float
    light_min: float
    awake_min: float
    sleep_score: float


class MonthlySleepTable(BaseModel):
    rows: List[SleepRow]


class CpapRow(BaseModel):
    data_sessao: str
    usage_mins: float
    ahi: float
    leak_95: float
    mask_events: float
    score: int
    pressure: Optional[float] = None
    tidal_volume: Optional[float] = None
    minute_ventilation: Optional[float] = None
    breath_rate: Optional[float] = None
    p95_pressure: Optional[float] = None


class MonthlyCpapTable(BaseModel):
    rows: List[CpapRow]


class CorrelationMetric(BaseModel):
    label: str
    good_nights_avg: float
    bad_nights_avg: float
    n_good: int
    n_bad: int
    direction: str


class CorrelationResponse(BaseModel):
    metrics: List[CorrelationMetric]
    nights_with_both: int
    ahi_sleep_score_pairs: Dict[str, List[Any]]
