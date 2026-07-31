"""
db_backup.py — Backup consistente de financial_news.db con rotacion.

Por que existe (auditoria 31 Jul 2026): la DB tiene 566 trades, 10.736 insights y
todos los shadows — es el 100% del track record del proyecto, y NO habia ninguna
copia. Un disco corrupto borraba cuatro meses de trabajo, y toda la metodologia
(medir antes de tocar) depende de esa data.

Usa la API `Connection.backup()` de sqlite3, NO un copy de archivo:
  - es consistente aunque AIdan este escribiendo en ese momento,
  - respeta WAL (un copy plano del .db sin el -wal puede quedar desactualizado).

Vive en src/common/ (NO en tools/) porque tools/ no es un paquete y PyInstaller
solo empaqueta sus .html => un import desde el exe fallaria.
CLI equivalente: python tools/backup_db.py [--list]

Se llama solo al arrancar AIdan (start_services) y es idempotente por dia:
si ya existe el backup de hoy, no lo rehace.
"""
import os
import sys
import glob
import sqlite3
from datetime import datetime, timedelta, timezone

TZ_AR = timezone(timedelta(hours=-3))

KEEP_DAYS = int(os.getenv('DB_BACKUP_KEEP_DAYS', '7'))


def _paths():
    base = os.path.join(os.environ.get('APPDATA', ''), 'AIdan')
    db = os.path.join(base, 'state', 'financial_news.db')
    backup_dir = os.path.join(base, 'backups')
    return db, backup_dir


def list_backups():
    _, backup_dir = _paths()
    files = sorted(glob.glob(os.path.join(backup_dir, 'financial_news_*.db')))
    for f in files:
        print(f"  {os.path.basename(f)}  {os.path.getsize(f)/1e6:.1f} MB")
    if not files:
        print("  (sin backups)")
    return files


def run_backup(logger=None):
    """Crea el backup del dia si no existe y rota los viejos.

    Returns: path del backup (str) o None si fallo / ya existia.
    """
    def _log(msg, err=False):
        if logger:
            (logger.warning if err else logger.info)(f"[backup_db] {msg}")
        else:
            print(f"[backup_db] {msg}")

    db_path, backup_dir = _paths()
    if not os.path.isfile(db_path):
        _log(f"DB no encontrada en {db_path}", err=True)
        return None

    os.makedirs(backup_dir, exist_ok=True)
    stamp = datetime.now(TZ_AR).strftime('%Y%m%d')
    dest = os.path.join(backup_dir, f'financial_news_{stamp}.db')

    if os.path.exists(dest):
        _log(f"backup de hoy ya existe ({os.path.basename(dest)}), skip")
        _rotate(backup_dir, _log)
        return dest

    tmp = dest + '.part'

    # Barrer un .part de una corrida fallida ANTES de empezar. Si quedo basura
    # (fallo de IO a mitad de escritura), el connect de abajo tiraria
    # "file is not a database" y el backup no volveria a funcionar nunca mas.
    if os.path.exists(tmp):
        try:
            os.remove(tmp)
            _log(f"limpiado {os.path.basename(tmp)} de una corrida previa fallida")
        except Exception as _pe:
            _log(f"no se pudo limpiar {os.path.basename(tmp)}: {_pe}", err=True)

    src = dst = None
    ok = False
    try:
        # timeout alto: si AIdan esta escribiendo, esperamos en vez de fallar.
        # OJO: Connection.backup() NO respeta este timeout — ante lock reintenta
        # indefinidamente. Corre en un thread daemon, asi que no traba el cierre.
        src = sqlite3.connect(db_path, timeout=30.0)
        dst = sqlite3.connect(tmp)
        with dst:
            src.backup(dst)
        ok = True
    except Exception as e:
        _log(f"FALLO: {e}", err=True)
    finally:
        # Cerrar SIEMPRE, y antes de tocar el archivo: en Windows un handle
        # sqlite abierto impide borrar/renombrar (WinError 32) => sin esto el
        # cleanup del path de error es codigo muerto y el .part queda colgado
        # (y no lo levanta el glob de rotacion, asi que no se limpia nunca).
        for _c in (dst, src):
            if _c is not None:
                try:
                    _c.close()
                except Exception:
                    pass
        if not ok and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception as _ce:
                _log(f"no se pudo borrar {os.path.basename(tmp)}: {_ce}", err=True)

    if not ok:
        return None

    try:
        os.replace(tmp, dest)   # atomico: nunca queda un backup a medias
        _log(f"OK {os.path.basename(dest)} ({os.path.getsize(dest)/1e6:.1f} MB)")
    except Exception as e:
        _log(f"FALLO al mover el backup a destino: {e}", err=True)
        return None

    _rotate(backup_dir, _log)
    return dest


def _rotate(backup_dir, _log):
    """Borra backups mas viejos que KEEP_DAYS, pero NUNCA deja menos de 2."""
    try:
        files = sorted(glob.glob(os.path.join(backup_dir, 'financial_news_*.db')))
        if len(files) <= 2:
            return
        cutoff = datetime.now(TZ_AR).date() - timedelta(days=KEEP_DAYS)
        removed = 0
        # dejar siempre los 2 mas nuevos, sin importar la fecha
        for f in files[:-2]:
            base = os.path.basename(f)
            try:
                d = datetime.strptime(base.replace('financial_news_', '').replace('.db', ''), '%Y%m%d').date()
            except ValueError:
                continue
            if d < cutoff:
                os.remove(f)
                removed += 1
        if removed:
            _log(f"rotacion: {removed} backup(s) viejo(s) borrado(s)")
    except Exception as e:
        _log(f"rotacion fallo (no critico): {e}", err=True)


if __name__ == '__main__':
    if '--list' in sys.argv:
        print("Backups en %APPDATA%/AIdan/backups:")
        list_backups()
    else:
        result = run_backup()
        sys.exit(0 if result else 1)
