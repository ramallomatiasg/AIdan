"""
GPU monitor para AIdan — detecta cuando otro proceso (juego, render) usa la GPU
y permite pausar llamadas LLM no-críticas para no competir por VRAM.

Usa nvidia-smi (CLI). Cache 30s para evitar overhead.

Threshold para 'pausar LLM':
  - GPU util > 50% Y memoria usada > 11 GB
  (eso indica un proceso pesado, no solo Ollama idle)

Uso:
    from src.common.gpu_monitor import should_pause_llm, get_gpu_state
    if should_pause_llm():
        return None  # skip non-critical LLM call
    # else proceder normal
"""
import subprocess
import time
import os

_last_check = 0
_cached_state = {
    'pause_llm': False,
    'gpu_util': 0,
    'gpu_mem_used_mb': 0,
    'gpu_mem_total_mb': 0,
    'available': False,
    'reason': 'not_checked',
}
CHECK_INTERVAL = 30  # cache TTL en segundos

# Thresholds (ajustables via env vars)
PAUSE_GPU_UTIL = int(os.getenv('AIDAN_PAUSE_GPU_UTIL', '50'))     # > 50% utilization
PAUSE_GPU_MEM_MB = int(os.getenv('AIDAN_PAUSE_GPU_MEM_MB', '11000'))  # > 11 GB used


def get_gpu_state(force_refresh=False):
    """Get current GPU state with 30s cache. Returns dict with pause_llm flag."""
    global _last_check, _cached_state
    now = time.time()
    if not force_refresh and (now - _last_check) < CHECK_INTERVAL:
        return _cached_state

    _last_check = now
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total',
             '--format=csv,noheader,nounits'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode != 0:
            _cached_state = {**_cached_state, 'available': False, 'reason': 'nvidia-smi failed'}
            return _cached_state
        line = result.stdout.strip().split('\n')[0]
        parts = [p.strip() for p in line.split(',')]
        if len(parts) < 3:
            _cached_state = {**_cached_state, 'available': False, 'reason': 'parse error'}
            return _cached_state

        util = int(parts[0])
        mem_used = int(parts[1])
        mem_total = int(parts[2])

        pause = util > PAUSE_GPU_UTIL and mem_used > PAUSE_GPU_MEM_MB
        reason = 'idle'
        if pause:
            reason = f'busy: util={util}% mem={mem_used}/{mem_total}MB'

        _cached_state = {
            'pause_llm': pause,
            'gpu_util': util,
            'gpu_mem_used_mb': mem_used,
            'gpu_mem_total_mb': mem_total,
            'available': True,
            'reason': reason,
        }
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError) as e:
        # nvidia-smi not in PATH or no GPU → no pausing (default behavior)
        _cached_state = {
            'pause_llm': False,
            'gpu_util': 0,
            'gpu_mem_used_mb': 0,
            'gpu_mem_total_mb': 0,
            'available': False,
            'reason': f'error: {type(e).__name__}',
        }
    return _cached_state


def should_pause_llm():
    """Bool shortcut: pause LLM calls if GPU is heavily used by other process."""
    return get_gpu_state()['pause_llm']


def get_status_summary():
    """Human-readable status for logs/dashboard."""
    s = get_gpu_state()
    if not s['available']:
        return f"GPU monitor: unavailable ({s['reason']})"
    return f"GPU: util={s['gpu_util']}% mem={s['gpu_mem_used_mb']}/{s['gpu_mem_total_mb']}MB pause_llm={s['pause_llm']}"
