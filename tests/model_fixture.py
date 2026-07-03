"""Ensure a valid model.nnue exists for native tests (HIDDEN=256)."""
from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

FEATURES, HIDDEN = 4096, 256


def model_header_valid(path: Path) -> bool:
    if not path.is_file():
        return False
    data = path.read_bytes()
    if len(data) < 64:
        return False
    magic, version, nf, nh, size, _, _, checksum, _ = struct.unpack("<8sIIIIffQ24s", data[:64])
    if magic != b"PKNNUE1\0" or version != 2 or nf != FEATURES or nh != HIDDEN:
        return False
    if size != len(data) - 64:
        return False
    value = 14695981039346656037
    for byte in data[64:]:
        value = ((value ^ byte) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return value == checksum


def ensure_valid_model(path: Path) -> bool:
    if model_header_valid(path):
        return True
    try:
        from training.train_nnue import export
    except ImportError:
        return False
    emb = np.zeros((FEATURES, HIDDEN), np.float32)
    action_emb = np.zeros((FEATURES, HIDDEN), np.float32)
    value = np.zeros(HIDDEN, np.float32)
    export(path, emb, np.zeros(HIDDEN, np.float32), value, 0.0, action_emb)
    return model_header_valid(path)
