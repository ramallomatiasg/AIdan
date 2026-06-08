"""
significance.py — Verificacion adversarial de hallazgos estadisticos (v3.38.0).

Antes de proponer/aplicar cualquier filtro, block de bucket, o cambio de param,
el hallazgo pasa por un check esceptico: ¿sobrevive a significancia o es ruido
de muestra chica?

Metodologia (acordada 29 May 2026, ver CLAUDE.md "Metodologia de trabajo con IA"):
- baseline WR = 37.4% (294 trades en trade_archive al 29 May 2026)
- Default = RUIDO (rechazar) si: n < MIN_N  O  el CI 95% del subset cruza el baseline
- Binomial test one-sided en la direccion del claim (worse para blocks, better para allows)

Uso:
  from src.optimizer.significance import verify_finding, verify_change_proposal
  res = verify_finding(n=66, wins=24, direction='worse')
  # res.significant -> True/False, res.verdict, res.p_value, res.ci_low, res.ci_high

NO requiere sub-agentes: es estadistica determinista (scipy.stats.binom).
"""
import logging
import math
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger('significance')

# Baseline empirico: WR del trade_archive. Recalculable con compute_baseline_wr().
DEFAULT_BASELINE_WR = 0.374
MIN_N = 25          # piso de muestra: bajo esto -> ruido por falta de poder estadistico
ALPHA = 0.05        # nivel de significancia
Z_95 = 1.959963985  # z para CI 95%


@dataclass
class SignificanceResult:
    n: int
    wins: int
    wr: float                 # win rate observado del subset (0-1)
    baseline_wr: float
    direction: str            # 'worse' | 'better'
    p_value: float            # binomial one-sided en la direccion del claim
    ci_low: float             # CI 95% Wilson, low
    ci_high: float            # CI 95% Wilson, high
    significant: bool         # True si el hallazgo sobrevive (no es ruido)
    verdict: str              # texto legible del veredicto
    reason: str               # por que significant True/False

    def to_dict(self):
        return asdict(self)

    def summary(self) -> str:
        return (f"n={self.n} WR={self.wr*100:.1f}% vs base {self.baseline_wr*100:.1f}% "
                f"| CI95 [{self.ci_low*100:.1f}%, {self.ci_high*100:.1f}%] "
                f"| p={self.p_value:.3f} | {self.verdict}")


def _wilson_ci(wins: int, n: int, z: float = Z_95):
    """Intervalo de Wilson score 95% para una proporcion. Robusto en n chico."""
    if n == 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def _binom_one_sided(wins: int, n: int, p0: float, direction: str) -> float:
    """P-value binomial one-sided.
    direction='worse': H1 = subset WR < p0  -> P(X <= wins)
    direction='better': H1 = subset WR > p0 -> P(X >= wins)
    """
    try:
        from scipy.stats import binom
        if direction == 'worse':
            return float(binom.cdf(wins, n, p0))
        else:  # better
            return float(binom.sf(wins - 1, n, p0))  # sf(k-1) = P(X >= k)
    except Exception:
        # Fallback sin scipy: normal approx
        if n == 0:
            return 1.0
        mu = n * p0
        sd = math.sqrt(n * p0 * (1 - p0)) or 1e-9
        from statistics import NormalDist
        nd = NormalDist()
        if direction == 'worse':
            # P(X <= wins) con correccion de continuidad
            return nd.cdf((wins + 0.5 - mu) / sd)
        else:
            return 1.0 - nd.cdf((wins - 0.5 - mu) / sd)


def verify_finding(n: int, wins: int, baseline_wr: float = DEFAULT_BASELINE_WR,
                   direction: str = 'auto', min_n: int = MIN_N,
                   alpha: float = ALPHA) -> SignificanceResult:
    """Verifica si un hallazgo (subset con n trades, wins ganadores) es
    estadisticamente distinguible del baseline o es ruido de muestra chica.

    direction:
      'worse'  -> el claim es "este subset rinde PEOR" (justifica un block)
      'better' -> el claim es "este subset rinde MEJOR" (justifica un allow/boost)
      'auto'   -> infiere por la WR observada vs baseline

    Returns SignificanceResult. .significant=True solo si:
      n >= min_n  Y  p_value < alpha  Y  el CI 95% NO cruza el baseline en contra.
    """
    n = int(n)
    wins = int(wins)
    wr = wins / n if n > 0 else 0.0

    if direction == 'auto':
        direction = 'worse' if wr < baseline_wr else 'better'

    ci_low, ci_high = _wilson_ci(wins, n)
    p_value = _binom_one_sided(wins, n, baseline_wr, direction)

    # Regla 1: muestra insuficiente -> ruido
    if n < min_n:
        return SignificanceResult(
            n, wins, wr, baseline_wr, direction, p_value, ci_low, ci_high,
            significant=False, verdict='RUIDO (muestra insuficiente)',
            reason=f"n={n} < min_n={min_n}: sin poder estadistico")

    # Regla 2: CI cruza el baseline -> no distinguible
    if direction == 'worse':
        # Para afirmar "peor", el techo del CI debe estar por DEBAJO del baseline
        ci_crosses = ci_high >= baseline_wr
    else:
        # Para afirmar "mejor", el piso del CI debe estar por ENCIMA del baseline
        ci_crosses = ci_low <= baseline_wr

    if ci_crosses:
        return SignificanceResult(
            n, wins, wr, baseline_wr, direction, p_value, ci_low, ci_high,
            significant=False, verdict='RUIDO (CI cruza baseline)',
            reason=f"CI95 [{ci_low*100:.1f}%, {ci_high*100:.1f}%] no separa del baseline {baseline_wr*100:.1f}%")

    # Regla 3: p-value
    if p_value < alpha:
        return SignificanceResult(
            n, wins, wr, baseline_wr, direction, p_value, ci_low, ci_high,
            significant=True, verdict=f'SIGNIFICATIVO ({direction})',
            reason=f"p={p_value:.4f} < {alpha}, n={n}, CI no cruza baseline")
    else:
        return SignificanceResult(
            n, wins, wr, baseline_wr, direction, p_value, ci_low, ci_high,
            significant=False, verdict='RUIDO (p-value alto)',
            reason=f"p={p_value:.4f} >= {alpha}: no distinguible del baseline")


# ─── Mapeo change_type -> subset del trade_archive ───

def _query_subset(change_type: str, params: dict, db_path: str = None):
    """Dado un change_type + params, devuelve (n, wins, claim_direction) del
    subset relevante en trade_archive. Devuelve None si el change_type no se
    puede verificar estadisticamente (ej: tune_optimizer_param)."""
    import sqlite3
    if db_path is None:
        from src.common.db import DB_PATH
        db_path = DB_PATH

    # block_* -> claim "este subset es peor" (worse). adjust/allow -> 'better' o 'auto'.
    where = None
    args = []
    claim = 'worse'

    if change_type == 'block_setup_type':
        st = params.get('setup_type', '')
        # match contra trigger_type O setup_type
        where = "(trigger_type = ? OR setup_type = ?)"
        args = [st, st]
    elif change_type == 'block_conf_bucket':
        lo = params.get('bucket_lo', 0); hi = params.get('bucket_hi', 100)
        where = "confidence >= ? AND confidence <= ?"
        args = [lo, hi]
    elif change_type == 'block_hour_utc':
        hours = params.get('hours', [])
        if not hours:
            return None
        where = f"hour_utc IN ({','.join('?'*len(hours))})"
        args = list(hours)
    elif change_type == 'block_session':
        sessions = params.get('sessions', [])
        if not sessions:
            return None
        where = f"session IN ({','.join('?'*len(sessions))})"
        args = list(sessions)
    elif change_type in ('adjust_setup_confidence',):
        st = params.get('setup_type', '')
        where = "(trigger_type = ? OR setup_type = ?)"
        args = [st, st]
        # direccion depende del signo del ajuste.
        # v3.40.3 FIX: el sistema entero usa 'delta' (prompts LLM, change_manager, shadow);
        # 'adjustment' nunca venia → el gate corria la hipotesis direccional equivocada.
        claim = 'better' if params.get('delta', params.get('adjustment', 0)) >= 0 else 'worse'
    else:
        # block_pattern, tune_optimizer_param, adjust_min_confidence_per_track:
        # no mapean a un subset simple -> no verificable por este metodo
        return None

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT COUNT(*), SUM(CASE WHEN mt5_pnl > 0 THEN 1 ELSE 0 END)
        FROM trade_archive
        WHERE mt5_pnl IS NOT NULL AND {where}
    """, args)
    n, wins = cur.fetchone()
    conn.close()
    return (int(n or 0), int(wins or 0), claim)


def verify_change_proposal(change_type: str, params: dict,
                           baseline_wr: float = DEFAULT_BASELINE_WR,
                           db_path: str = None) -> Optional[SignificanceResult]:
    """Verifica una propuesta del nightly_analyst contra el trade_archive.

    Returns:
      SignificanceResult si el change_type es verificable estadisticamente.
      None si NO es verificable (tune_optimizer_param, block_pattern, etc.) ->
           el caller decide (por defecto: dejar pasar, no es un block de subset).
    """
    try:
        subset = _query_subset(change_type, params, db_path)
        if subset is None:
            return None
        n, wins, claim = subset
        return verify_finding(n, wins, baseline_wr=baseline_wr, direction=claim)
    except Exception as e:
        logger.warning(f"verify_change_proposal error ({change_type}): {e}")
        return None


def compute_baseline_wr(db_path: str = None) -> float:
    """Recalcula el baseline WR desde trade_archive (para mantener actualizado)."""
    import sqlite3
    if db_path is None:
        from src.common.db import DB_PATH
        db_path = DB_PATH
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*), SUM(CASE WHEN mt5_pnl > 0 THEN 1 ELSE 0 END) FROM trade_archive WHERE mt5_pnl IS NOT NULL")
    n, wins = cur.fetchone()
    conn.close()
    return (wins / n) if n else DEFAULT_BASELINE_WR
