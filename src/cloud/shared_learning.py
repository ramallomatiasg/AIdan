"""
Shared Learning — Syncs anonymized trade data to Supabase cloud
so multiple AIdan instances learn from each other.

Uses requests (REST API) — no extra dependencies needed.
Supabase credentials are hardcoded (shared project).
User authentication via users table in Supabase.
"""
import json
import time
import uuid
import hashlib
import socket
import requests
from datetime import datetime, timezone, timedelta

# ── Hardcoded Supabase config (shared project) ──
SUPABASE_URL = "https://lunjwgycevhpgqupmhnn.supabase.co"
SUPABASE_KEY = "sb_publishable_eNPHX0S7AaFnLJRg1oZqhA_seRgWlsf"
_SALT = "aidan_salt_"


def hash_password(password):
    """Hash a password with salt."""
    return hashlib.sha256(f"{_SALT}{password}".encode()).hexdigest()


def _sb_headers():
    """Supabase REST API headers."""
    return {
        'apikey': SUPABASE_KEY,
        'Authorization': f"Bearer {SUPABASE_KEY}",
        'Content-Type': 'application/json',
    }


def _sb_url(table):
    return f"{SUPABASE_URL}/rest/v1/{table}"


def authenticate_user(username, password):
    """Authenticate user against Supabase users table.
    Returns (ok, message, user_data)."""
    from urllib.parse import quote
    try:
        pwd_hash = hash_password(password)
        resp = requests.get(
            _sb_url('users') + f'?username=eq.{quote(username, safe="")}&password_hash=eq.{pwd_hash}&select=id,username,created_at',
            headers=_sb_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            users = resp.json()
            if users:
                return True, "Login exitoso", users[0]
            else:
                return False, "Usuario o clave incorrectos", None
        else:
            return False, f"Error de conexion: {resp.status_code}", None
    except requests.exceptions.ConnectionError:
        return False, "Sin conexion a internet", None
    except Exception as e:
        return False, f"Error: {str(e)}", None


def change_password(username, old_password, new_password):
    """Change user password in Supabase. Returns (ok, message)."""
    if not new_password or len(new_password) < 8:
        return False, "La clave debe tener al menos 8 caracteres"
    try:
        # Verify old password first
        old_hash = hash_password(old_password)
        from urllib.parse import quote
        resp = requests.get(
            _sb_url('users') + f'?username=eq.{quote(username, safe="")}&password_hash=eq.{old_hash}&select=id',
            headers=_sb_headers(),
            timeout=10,
        )
        if resp.status_code != 200 or not resp.json():
            return False, "Clave actual incorrecta"

        # Update password
        new_hash = hash_password(new_password)
        resp = requests.patch(
            _sb_url('users') + f'?username=eq.{quote(username, safe="")}',
            headers={**_sb_headers(), 'Prefer': 'return=minimal'},
            json={'password_hash': new_hash},
            timeout=10,
        )
        if resp.status_code < 300:
            return True, "Clave actualizada"
        else:
            return False, f"Error: {resp.status_code}"
    except Exception as e:
        return False, f"Error: {str(e)}"


class SharedLearning:
    def __init__(self, logger):
        self.logger = logger
        self._config = None
        self._last_sync = 0
        self._sync_interval = 7200  # 2 hours
        self._last_fetch = 0
        self._tables_verified = False

    def _load_config(self):
        """Load config from SQLite + hardcoded Supabase credentials."""
        from src.common.db import get_shared_learning_config
        self._config = get_shared_learning_config()
        # Always use hardcoded Supabase credentials
        self._config['supabase_url'] = SUPABASE_URL
        self._config['supabase_key'] = SUPABASE_KEY
        # Auto-verify tables on first load if enabled
        if not self._tables_verified and self._config.get('enabled'):
            try:
                ok, _ = self.test_connection()
                if ok:
                    self._tables_verified = True
            except Exception:
                pass
        return self._config

    @property
    def enabled(self):
        if not self._config:
            self._load_config()
        return bool(self._config and self._config.get('enabled'))

    def reload_config(self):
        """Force reload config."""
        self._config = None
        self._tables_verified = False
        return self._load_config()

    @staticmethod
    def _safe_float(val):
        """Convert value to float safely, returning 0 for non-numeric strings."""
        if val is None:
            return 0.0
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    def _headers(self):
        return {**_sb_headers(), 'Prefer': 'return=representation'}

    def _url(self, table):
        return _sb_url(table)

    # ── Table Setup ──

    def setup_tables(self):
        """Create Supabase tables via REST SQL endpoint. Returns (ok, message)."""
        if not self._config or not self._config.get('supabase_url'):
            return False, "No Supabase URL configured"

        sql = """
        CREATE TABLE IF NOT EXISTS instances (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ DEFAULT now(),
            last_sync TIMESTAMPTZ
        );

        CREATE TABLE IF NOT EXISTS shared_trades (
            id BIGSERIAL PRIMARY KEY,
            instance_id UUID REFERENCES instances(id),
            local_strategy_id INTEGER,
            direction TEXT,
            result TEXT,
            pips REAL,
            sl_pips REAL,
            tp_pips REAL,
            sl_hit BOOLEAN,
            tp_hit BOOLEAN,
            confidence REAL,
            trigger_type TEXT,
            setup_type TEXT,
            session TEXT,
            hour_utc INTEGER,
            day_of_week INTEGER,
            htf_bias TEXT,
            market_trend TEXT,
            trend_strength REAL,
            rsi_at_entry REAL,
            volatility REAL,
            news_category TEXT,
            mt5_pnl REAL,
            created_at TIMESTAMPTZ,
            synced_at TIMESTAMPTZ DEFAULT now(),
            UNIQUE(instance_id, local_strategy_id)
        );

        CREATE TABLE IF NOT EXISTS shared_insights (
            id BIGSERIAL PRIMARY KEY,
            category TEXT,
            insight TEXT,
            data JSONB,
            min_trades INTEGER,
            created_at TIMESTAMPTZ DEFAULT now()
        );
        """
        try:
            base = self._config['supabase_url'].rstrip('/')
            # Use the SQL RPC endpoint
            resp = requests.post(
                f"{base}/rest/v1/rpc/exec_sql",
                headers=self._headers(),
                json={'query': sql},
                timeout=15,
            )
            # If exec_sql doesn't exist, try the pg_meta endpoint
            if resp.status_code in (404, 400):
                # Alternative: use Supabase Management API or direct SQL
                # For free tier, tables should be created via SQL Editor
                return False, "Tablas no encontradas. Crealas manualmente en Supabase SQL Editor con el script provisto."

            if resp.status_code < 300:
                self._tables_verified = True
                return True, "Tablas creadas correctamente"
            else:
                return False, f"Error: {resp.status_code} - {resp.text[:200]}"
        except Exception as e:
            return False, f"Error de conexion: {str(e)}"

    def test_connection(self):
        """Test if Supabase connection works. Returns (ok, message)."""
        if not self._config or not self._config.get('supabase_url'):
            return False, "No configurado"
        try:
            resp = requests.get(
                self._url('instances') + '?select=id&limit=1',
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                self._tables_verified = True
                return True, "Conexion OK"
            elif resp.status_code == 404:
                return False, "Tabla 'instances' no existe. Ejecuta el SQL de setup."
            else:
                return False, f"Error {resp.status_code}: {resp.text[:100]}"
        except requests.exceptions.ConnectionError:
            return False, "No se pudo conectar a Supabase"
        except Exception as e:
            return False, f"Error: {str(e)}"

    # ── Instance Registration ──

    def register_instance(self):
        """Register this AIdan instance in Supabase (idempotent)."""
        if not self.enabled:
            return False
        instance_id = self._config.get('instance_id', '')
        name = self._config.get('instance_name', '') or f"AIdan-{socket.gethostname()}"

        try:
            # Upsert instance
            resp = requests.post(
                self._url('instances'),
                headers={**self._headers(), 'Prefer': 'resolution=merge-duplicates,return=representation'},
                json={'id': instance_id, 'name': name, 'last_sync': datetime.now(timezone.utc).isoformat()},
                timeout=10,
            )
            if resp.status_code < 300:
                self.logger.info(f"Shared Learning: instance registered as '{name}'")
                return True
            else:
                self.logger.warning(f"Shared Learning: register failed {resp.status_code}")
                return False
        except Exception as e:
            self.logger.warning(f"Shared Learning: register error: {e}")
            return False

    # ── Trade Sync ──

    def sync_trades(self):
        """Upload unsynced local trades to Supabase (anonymized)."""
        if not self.enabled:
            return 0
        from src.common.db import get_unsynced_trades, mark_trades_synced

        trades = get_unsynced_trades(limit=50)
        if not trades:
            return 0

        instance_id = self._config['instance_id']
        payload = []
        synced_ids = []

        for t in trades:
            # Skip weekend paper trades (unreliable with market closed)
            if t.get('day_of_week', -1) in (5, 6):
                synced_ids.append(t['id'])  # mark as synced to avoid retrying
                continue
            # Anonymize: strip prices, titles, personal data
            payload.append({
                'instance_id': instance_id,
                'local_strategy_id': t['strategy_id'],
                'direction': t.get('direction', ''),
                'result': t.get('result', ''),
                'pips': t.get('pips', 0),
                'sl_pips': t.get('sl_pips', 0),
                'tp_pips': t.get('tp_pips', 0),
                'sl_hit': bool(t.get('sl_hit', 0)),
                'tp_hit': bool(t.get('tp_hit', 0)),
                'confidence': t.get('confidence', 0),
                'trigger_type': t.get('trigger_type', ''),
                'setup_type': t.get('setup_type', ''),
                'session': t.get('session', ''),
                'hour_utc': t.get('hour_utc', 0),
                'day_of_week': t.get('day_of_week', 0),
                'htf_bias': t.get('htf_bias', ''),
                'market_trend': t.get('market_trend', ''),
                'trend_strength': self._safe_float(t.get('trend_strength', 0)),
                'rsi_at_entry': t.get('rsi_at_entry', 0),
                'volatility': self._safe_float(t.get('volatility', 0)),
                'news_category': self._categorize_news(t.get('news_title', '')),
                'mt5_pnl': t.get('mt5_pnl', 0),
                'created_at': t.get('created_at', ''),
            })
            synced_ids.append(t['id'])

        if not payload:
            return 0

        try:
            # Upsert to avoid duplicates (unique on instance_id + local_strategy_id)
            resp = requests.post(
                self._url('shared_trades'),
                headers={**self._headers(), 'Prefer': 'resolution=merge-duplicates,return=minimal'},
                json=payload,
                timeout=15,
            )
            if resp.status_code < 300:
                mark_trades_synced(synced_ids)
                self.logger.info(f"Shared Learning: synced {len(synced_ids)} trades to cloud")
                # Update instance last_sync
                self._update_last_sync()
                return len(synced_ids)
            else:
                self.logger.warning(f"Shared Learning: sync failed {resp.status_code}: {resp.text[:200]}")
                return 0
        except Exception as e:
            self.logger.warning(f"Shared Learning: sync error: {e}")
            return 0

    def _categorize_news(self, title):
        """Extract generic news category from title (no title shared)."""
        if not title:
            return ''
        title_lower = title.lower()
        categories = {
            'fed_rate': ['fed', 'rate', 'fomc', 'powell', 'interest rate'],
            'employment': ['employment', 'nonfarm', 'payroll', 'jobs', 'unemployment'],
            'gdp_growth': ['gdp', 'growth', 'recession'],
            'inflation': ['inflation', 'cpi', 'ppi', 'consumer price'],
            'geopolitical': ['war', 'conflict', 'tariff', 'sanction'],
            'oil_energy': ['oil', 'crude', 'opec', 'energy'],
            'central_bank': ['ecb', 'boe', 'boj', 'central bank'],
        }
        for cat, keywords in categories.items():
            if any(kw in title_lower for kw in keywords):
                return cat
        return 'other'

    # ── Fetch Shared Data ──

    def fetch_shared_trades(self, last_id=0, limit=500):
        """Download trades from OTHER instances newer than last_id."""
        if not self.enabled:
            return []
        instance_id = self._config['instance_id']
        try:
            resp = requests.get(
                self._url('shared_trades') + f'?instance_id=neq.{instance_id}&id=gt.{last_id}&order=id.asc&limit={limit}',
                headers=self._headers(),
                timeout=15,
            )
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            self.logger.warning(f"Shared Learning: fetch trades error: {e}")
            return []

    def import_shared_trades(self):
        """Fetch new trades from other instances and cache locally for learning."""
        if not self.enabled:
            return 0
        try:
            from src.common.db import get_last_fetched_remote_id, save_shared_trades, update_last_fetched_remote_id
            last_id = get_last_fetched_remote_id()
            trades = self.fetch_shared_trades(last_id=last_id, limit=500)
            if not trades:
                return 0
            inserted = save_shared_trades(trades)
            # Update cursor to max ID fetched
            max_id = max(t.get('id', 0) for t in trades)
            if max_id > last_id:
                update_last_fetched_remote_id(max_id)
            self.logger.info(f"Shared Learning: fetched {len(trades)} remote trades, {inserted} new cached")
            return inserted
        except Exception as e:
            self.logger.warning(f"Shared Learning: trade import error: {e}")
            return 0

    def fetch_shared_insights(self):
        """Download aggregated insights from the cloud."""
        if not self.enabled:
            return []
        try:
            # Get insights from last 7 days
            cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            resp = requests.get(
                self._url('shared_insights') + f'?created_at=gte.{cutoff}&order=created_at.desc&limit=50',
                headers=self._headers(),
                timeout=10,
            )
            if resp.status_code == 200:
                return resp.json()
            return []
        except Exception as e:
            self.logger.warning(f"Shared Learning: fetch insights error: {e}")
            return []

    # ── Status & Stats ──

    def get_status(self):
        """Get sync status for dashboard."""
        if not self._config:
            self._load_config()
        status = {
            'enabled': self.enabled,
            'configured': bool(self._config and self._config.get('supabase_url')),
            'instance_id': (self._config or {}).get('instance_id', ''),
            'instance_name': (self._config or {}).get('instance_name', ''),
            'last_sync': (self._config or {}).get('last_sync', ''),
            'tables_ok': self._tables_verified,
            'trades_synced': 0,
            'trades_remote': 0,
        }
        if self.enabled:
            try:
                from src.common.db import get_synced_trade_count
                status['trades_synced'] = get_synced_trade_count()
            except Exception:
                pass
            try:
                instance_id = self._config['instance_id']
                resp = requests.get(
                    self._url('shared_trades') + f'?instance_id=neq.{instance_id}&select=id',
                    headers={**self._headers(), 'Prefer': 'count=exact'},
                    timeout=5,
                )
                if resp.status_code == 200:
                    count_header = resp.headers.get('content-range', '')
                    if '/' in count_header:
                        status['trades_remote'] = int(count_header.split('/')[-1])
                    else:
                        status['trades_remote'] = len(resp.json())
            except Exception:
                pass
        return status

    def _update_last_sync(self):
        """Update last_sync timestamp in local DB and Supabase."""
        now_str = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
        try:
            from src.common.db import update_shared_learning_last_sync
            update_shared_learning_last_sync(now_str)
        except Exception:
            pass
        try:
            instance_id = self._config['instance_id']
            requests.patch(
                self._url('instances') + f'?id=eq.{instance_id}',
                headers=self._headers(),
                json={'last_sync': datetime.now(timezone.utc).isoformat()},
                timeout=5,
            )
        except Exception:
            pass

    # ── Tick (called from learning engine) ──

    def tick(self):
        """Called periodically. Syncs if enough time has passed."""
        if not self.enabled:
            return

        now = time.time()
        if now - self._last_sync < self._sync_interval:
            return

        self._last_sync = now

        # Register instance if first time
        if not self._tables_verified:
            ok, msg = self.test_connection()
            if not ok:
                self.logger.warning(f"Shared Learning: connection test failed: {msg}")
                return
            self.register_instance()

        # Sync trades up
        synced = self.sync_trades()

        # Import remote trades for cross-instance learning
        try:
            imported = self.import_shared_trades()
        except Exception as e:
            self.logger.warning(f"Shared Learning: trade import error: {e}")

        # Fetch remote insights and save locally
        try:
            remote_insights = self.fetch_shared_insights()
            if remote_insights:
                from src.common.db import save_learning_insight
                for ins in remote_insights:
                    save_learning_insight(
                        f"shared_{ins.get('category', 'unknown')}",
                        ins.get('insight', ''),
                        ins.get('data', {}),
                        'From shared learning cloud'
                    )
                self.logger.info(f"Shared Learning: imported {len(remote_insights)} remote insights")
        except Exception as e:
            self.logger.warning(f"Shared Learning: insight import error: {e}")


def generate_instance_id():
    """Generate a unique instance ID."""
    return str(uuid.uuid4())


def get_default_instance_name():
    """Generate default instance name from hostname."""
    try:
        return f"AIdan-{socket.gethostname()}"
    except Exception:
        return "AIdan-Unknown"
