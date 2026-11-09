"""
================================================================================
TopGraphics | math_utils.py
Utilitários matemáticos puros (sem OpenGL): normalização de vetores e normal de face.
Módulo-folha: pode ser importado por qualquer outro sem gerar dependência circular.
================================================================================
"""

import numpy as np


def normalize(v):
    """Normaliza um vetor 3D."""
    norm = np.linalg.norm(v)
    return v / norm if norm > 1e-8 else v


def compute_normal(p1, p2, p3):
    """Calcula o vetor normal unitário de um triângulo (p1, p2, p3) para iluminação."""
    u = np.array(p2, dtype=np.float32) - np.array(p1, dtype=np.float32)
    v = np.array(p3, dtype=np.float32) - np.array(p1, dtype=np.float32)
    n = np.cross(u, v)
    return normalize(n)
