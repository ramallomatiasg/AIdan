"""
backup_db.py — CLI del backup de la DB. La logica vive en src/common/db_backup.py.

Se separo asi porque tools/ NO es un paquete y PyInstaller solo empaqueta sus
.html: si AIdan.exe importara desde tools/, fallaria en el exe congelado.

Uso:
    python tools/backup_db.py            # backup + rotacion
    python tools/backup_db.py --list     # listar backups existentes
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.common.db_backup import run_backup, list_backups  # noqa: E402

if __name__ == '__main__':
    if '--list' in sys.argv:
        print("Backups en %APPDATA%/AIdan/backups:")
        list_backups()
    else:
        sys.exit(0 if run_backup() else 1)
