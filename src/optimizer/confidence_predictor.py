"""
confidence_predictor.py — Carga modelos ML dedicados y predice P(win)
en runtime para reemplazar (parcialmente) la heuristica `dynamic_conf`.

Solo se invoca cuando:
1. Env var `USE_ML_CONFIDENCE=true` (default false para safety)
2. El trigger_type del signal tiene modelo dedicado disponible
   (actualmente: news, m15_structure)

Fallback: si modelo no disponible o feature vector incompleto -> None.
Caller debe usar heuristica vieja en ese caso.

Output del `predict_confidence`:
- int 0-100 (mapping P(win) [0,1] → score)
- None si no aplicable (caller usa heuristica)
"""
import json
import logging
import os
from pathlib import Path
from typing import Optional, Dict

logger = logging.getLogger('confidence_predictor')

import sys as _sys
# Path resolution: dev vs frozen exe
if getattr(_sys, 'frozen', False):
    # PyInstaller frozen: _MEIPASS es donde se desempaquetaron los datas
    ROOT = Path(getattr(_sys, '_MEIPASS', '.'))
else:
    ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = ROOT / 'config'

# Fallback path if running from dev but model is elsewhere
_FALLBACK_CONFIG_DIRS = [
    Path('F:/AIdan/config'),
    Path(__file__).resolve().parent.parent.parent / 'config',
]

# Lazy-loaded model cache
_MODELS = {}
_META = None
_LOAD_ATTEMPTED = False


def _load_models():
    """Cargar modelos una vez (lazy). Retorna dict {trigger: model_data}."""
    global _MODELS, _META, _LOAD_ATTEMPTED
    if _LOAD_ATTEMPTED:
        return _MODELS
    _LOAD_ATTEMPTED = True

    # Buscar meta en config dir (frozen exe extract dir o dev)
    meta_path = CONFIG_DIR / 'confidence_predictor_meta.json'
    config_dir_used = CONFIG_DIR
    if not meta_path.exists():
        # Try fallbacks
        for fb in _FALLBACK_CONFIG_DIRS:
            fb_meta = fb / 'confidence_predictor_meta.json'
            if fb_meta.exists():
                meta_path = fb_meta
                config_dir_used = fb
                break
    if not meta_path.exists():
        logger.debug(f"No meta found at {meta_path} or fallbacks, ML predictor disabled")
        return _MODELS

    try:
        import joblib
        with open(meta_path, 'r', encoding='utf-8') as f:
            _META = json.load(f)

        for trigger, info in _META.get('models', {}).items():
            model_path = config_dir_used / info['path']
            if model_path.exists():
                _MODELS[trigger] = joblib.load(model_path)
                logger.info(f"Loaded confidence model: {trigger} ({info['type'].upper()}, AUC {info['auc']:.3f})")
            else:
                logger.warning(f"Model file missing: {model_path}")
    except Exception as e:
        logger.warning(f"Failed to load ML models: {e}")

    return _MODELS


def _derive_session_from_hour(h: int) -> str:
    """Forex sessions UTC."""
    if h is None: return ''
    if h < 7 or h >= 22: return 'asia'
    if 7 <= h < 13: return 'london'
    if 13 <= h < 16: return 'overlap'
    if 16 <= h < 21: return 'ny'
    return 'late_ny'


def _build_feature_vector(signal: dict, model_data: dict) -> Optional[Dict[str, float]]:
    """Construye dict feature_name -> value en el orden esperado por el modelo.
    Usa medians del training para features missing (graceful degradation)."""
    feature_names = model_data['features']
    medians = model_data.get('medians', {})

    features = {}

    # Categorical (one-hot) — se generan a partir de signal['session'], signal['htf_bias'], etc.
    categorical = _META.get('categorical_features', {})
    for col, levels in categorical.items():
        signal_val = signal.get(col, '') or ''
        for level in levels:
            fname = f'{col}__{level}'
            features[fname] = 1.0 if signal_val == level else 0.0

    # Numeric base
    numeric = _META.get('numeric_features', [])
    for col in numeric:
        val = signal.get(col)
        if val is None:
            val = medians.get(col, 0)
        try:
            features[col] = float(val)
        except (TypeError, ValueError):
            features[col] = medians.get(col, 0.0)

    # Enriched
    enriched = _META.get('enriched_features', [])
    for col in enriched:
        val = signal.get(col)
        if val is None:
            val = medians.get(col, 0)
        try:
            features[col] = float(val)
        except (TypeError, ValueError):
            features[col] = medians.get(col, 0.0)

    # Asegurar que devolvemos en el orden esperado
    return [features.get(fn, medians.get(fn, 0.0)) for fn in feature_names]


def predict_confidence(signal: dict) -> Optional[int]:
    """Predict confidence score (0-100) usando modelo dedicado para el trigger.

    Args:
        signal: dict con keys minimo:
            trigger_type, direction, session, htf_bias, market_trend,
            trend_strength, volatility, rsi_at_entry, avg_range_pips,
            hour_utc, day_of_week + enriched (optional, usa medians si faltan)

    Returns:
        int 0-100 si modelo disponible Y prediction exitosa
        None si fallback a heuristica
    """
    # Feature flag check
    if os.getenv('USE_ML_CONFIDENCE', 'false').lower() not in ('true', '1', 'yes'):
        return None

    trigger = signal.get('trigger_type', '')
    if not trigger:
        return None

    models = _load_models()
    if not models or trigger not in models:
        return None

    model_data = models[trigger]
    try:
        feature_vector = _build_feature_vector(signal, model_data)
        if feature_vector is None:
            return None

        import numpy as np
        X = np.array([feature_vector])

        # Apply scaler if model used one
        scaler = model_data.get('scaler')
        if scaler is not None:
            X = scaler.transform(X)

        model = model_data['model']
        p_win = float(model.predict_proba(X)[0, 1])

        # Map P(win) [0,1] → confidence [0,100]
        # Calibrated: directo. Range esperado: ~30-70 dado WR base 38%
        confidence = int(round(p_win * 100))
        return max(0, min(100, confidence))
    except Exception as e:
        logger.debug(f"predict_confidence error for {trigger}: {e}")
        return None


def get_predictor_info() -> dict:
    """Info para dashboard/diagnostico."""
    models = _load_models()
    if not models:
        return {'enabled': False, 'reason': 'no models loaded'}
    flag = os.getenv('USE_ML_CONFIDENCE', 'false').lower() in ('true', '1', 'yes')
    return {
        'enabled': flag,
        'feature_flag': 'USE_ML_CONFIDENCE',
        'models_loaded': list(models.keys()),
        'model_count': len(models),
        'meta': {t: {'type': info['type'], 'auc': info['auc']}
                 for t, info in _META.get('models', {}).items()},
    }
