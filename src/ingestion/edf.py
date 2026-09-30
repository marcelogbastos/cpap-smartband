"""Leitor EDF/EDF+ mínimo para os arquivos do cartão SD da ResMed.

Os arquivos da ResMed não são 100% conformes ao padrão (ex.: unidade 'Â°C' no
STR.edf), o que faz bibliotecas como o pyedflib recusá-los; e leitores
genéricos como o MNE reamostram sinais de taxas diferentes, distorcendo os
valores. O formato EDF é simples o bastante para ser lido diretamente:

    cabeçalho fixo (256 bytes) + 256 bytes por sinal + registros de int16.

Cada sinal é devolvido na sua taxa nativa, e as anotações EDF+ (eventos) são
decodificadas a partir do canal "EDF Annotations".
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Tuple

import numpy as np


@dataclass
class EdfSignal:
    label: str
    dimension: str
    samples_per_record: int
    physical: np.ndarray          # shape (n_records, samples_per_record); NaN = sem dado


@dataclass
class EdfFile:
    start: datetime
    n_records: int
    record_duration: float        # segundos (0 em arquivos só de anotações)
    signals: Dict[str, EdfSignal] = field(default_factory=dict)
    annotations: List[Tuple[float, float, str]] = field(default_factory=list)  # (início s, duração s, texto)

    def series(self, label: str) -> Tuple[np.ndarray, np.ndarray]:
        """Sinal contínuo: (segundos desde o início, valores físicos)."""
        sig = self.signals[label]
        values = sig.physical.reshape(-1)
        step = self.record_duration / sig.samples_per_record
        return np.arange(values.size) * step, values


def parse_edf_start(date_str: str, time_str: str) -> datetime:
    """Converte data/hora do cabeçalho EDF (dd.mm.yy / hh.mm.ss)."""
    dd, mm, yy = (int(x) for x in date_str.split("."))
    hh, mi, ss = (int(x) for x in time_str.split("."))
    year = 1900 + yy if yy >= 85 else 2000 + yy
    return datetime(year, mm, dd, hh, mi, ss)


_TAL = re.compile(rb"([+-]\d+(?:\.\d+)?)(?:\x15(\d+(?:\.\d+)?))?\x14(.*?)\x14", re.S)


def _parse_annotations(raw: bytes) -> List[Tuple[float, float, str]]:
    out = []
    for onset, duration, texts in _TAL.findall(raw):
        for text in texts.split(b"\x14"):
            text = text.strip(b"\x00").decode("latin-1").strip()
            if text:
                out.append((float(onset), float(duration or 0), text))
    return out


def read_edf(path) -> EdfFile:
    with open(path, "rb") as fh:
        raw = fh.read()

    hdr = raw[:256].decode("latin-1")
    start = parse_edf_start(hdr[168:176].strip(), hdr[176:184].strip())
    header_bytes = int(hdr[184:192].strip())
    n_records = int(hdr[236:244].strip())
    record_duration = float(hdr[244:252].strip() or 0)
    ns = int(hdr[252:256].strip())

    sig = raw[256:256 + ns * 256].decode("latin-1")
    pos = 0

    def fld(width):
        nonlocal pos
        vals = [sig[pos + i * width: pos + (i + 1) * width].strip() for i in range(ns)]
        pos += width * ns
        return vals

    labels = fld(16)
    fld(80)                                   # transducer
    dims = fld(8)
    pmin = [float(v) for v in fld(8)]
    pmax = [float(v) for v in fld(8)]
    dmin = [int(v) for v in fld(8)]
    dmax = [int(v) for v in fld(8)]
    fld(80)                                   # prefiltering
    nsamp = [int(v) for v in fld(8)]

    rec_len = sum(nsamp)
    avail = (len(raw) - header_bytes) // (2 * rec_len) if rec_len else 0
    if n_records < 0 or n_records > avail:
        n_records = avail

    body = raw[header_bytes: header_bytes + n_records * rec_len * 2]
    data = np.frombuffer(body, dtype="<i2").reshape(n_records, rec_len) if n_records else np.empty((0, rec_len), "<i2")

    edf = EdfFile(start=start, n_records=n_records, record_duration=record_duration)
    offset = 0
    for i, label in enumerate(labels):
        n = nsamp[i]
        block = data[:, offset:offset + n]
        offset += n
        if label == "EDF Annotations":
            edf.annotations.extend(_parse_annotations(block.tobytes()))
            continue
        if label == "Crc16" or not label:
            continue
        dig = block.astype("float64")
        scale = (pmax[i] - pmin[i]) / (dmax[i] - dmin[i]) if dmax[i] != dmin[i] else 1.0
        phys = np.round((dig - dmin[i]) * scale + pmin[i], 4)   # remove ruído de ponto flutuante
        phys[dig < dmin[i]] = np.nan                             # ResMed: -1 = "sem dado"
        edf.signals[label] = EdfSignal(label, dims[i], n, phys)
    edf.annotations.sort()
    return edf


def to_l_per_min(values: np.ndarray, dimension: str) -> np.ndarray:
    """Fuga/fluxo em L/s (unidade da ResMed) convertidos para L/min."""
    return values * 60.0 if dimension.lower() == "l/s" else values


def add_seconds(start: datetime, seconds) -> List[datetime]:
    return [start + timedelta(seconds=float(s)) for s in seconds]
