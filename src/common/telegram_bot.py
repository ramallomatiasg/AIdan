"""
Telegram bot bidireccional para AIdan.

Polling de comandos via getUpdates. Comandos disponibles:
  /status       Balance + daily PnL + posiciones abiertas + version
  /track        Stats triple track (M5/M15/H1)
  /recent       Ultimas 5 estrategias
  /pause        Pausa MT5 trading (kill switch ON)
  /resume       Reanuda MT5 trading (kill switch OFF)
  /kill         Emergency stop (igual /pause con notificacion CRITICAL)
  /help         Lista de comandos

Solo responde a chat_id configurado en TELEGRAM_CHAT_ID. Otros chat_ids son ignorados.

Corre como thread en AIdan (analyzer service). Polling con long-polling 30s.
"""
import logging
import time
import json
import sqlite3
import os
import requests
from threading import Thread

logger = logging.getLogger(__name__)


class TelegramBot:
    """Long-polling Telegram bot. Thread-safe, robusto."""

    def __init__(self, mt5_executor_provider=None):
        """
        mt5_executor_provider: callable que retorna MT5Executor o None (lazy ref)
        """
        self.mt5_provider = mt5_executor_provider
        self.last_update_id = 0
        self.running = False
        self.thread = None
        self._token = None
        self._chat_id = None
        self._refresh_creds()

    def _refresh_creds(self):
        try:
            from src.common.config import Config
            self._token = Config.TELEGRAM_TOKEN or ""
            self._chat_id = str(Config.TELEGRAM_CHAT_ID or "")
        except Exception:
            self._token = os.getenv("TELEGRAM_TOKEN", "")
            self._chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

    def is_configured(self):
        return bool(self._token and self._chat_id)

    def start(self):
        if not self.is_configured():
            logger.info("Telegram bot: not configured (no token/chat_id), skipping")
            return False
        if self.running:
            return True
        self.running = True
        self.thread = Thread(target=self._poll_loop, daemon=True, name="TelegramBot")
        self.thread.start()
        logger.info(f"Telegram bot started (polling for chat_id={self._chat_id})")
        return True

    def stop(self):
        self.running = False

    def _poll_loop(self):
        """Long-polling loop. Robusto a errores: log + retry."""
        while self.running:
            try:
                # Long-polling 30s
                r = requests.get(
                    f"https://api.telegram.org/bot{self._token}/getUpdates",
                    params={'offset': self.last_update_id + 1, 'timeout': 30},
                    timeout=40
                )
                if r.status_code != 200:
                    logger.warning(f"Telegram getUpdates HTTP {r.status_code}")
                    time.sleep(5)
                    continue
                data = r.json()
                if not data.get('ok'):
                    logger.warning(f"Telegram getUpdates error: {data.get('description')}")
                    time.sleep(5)
                    continue
                for update in data.get('result', []):
                    self.last_update_id = update.get('update_id', self.last_update_id)
                    self._handle_update(update)
            except requests.exceptions.Timeout:
                continue  # long-poll timeout es normal
            except Exception as e:
                logger.warning(f"Telegram poll error: {e}")
                time.sleep(5)

    def _handle_update(self, update):
        msg = update.get('message') or update.get('edited_message')
        if not msg:
            return
        chat_id = str(msg.get('chat', {}).get('id', ''))
        text = msg.get('text', '').strip()
        # Solo aceptamos del chat_id configurado
        if chat_id != self._chat_id:
            logger.info(f"Telegram: ignored msg from chat_id={chat_id} (not authorized)")
            return
        if not text.startswith('/'):
            return  # solo procesamos comandos
        try:
            self._dispatch_command(text)
        except Exception as e:
            logger.error(f"Telegram cmd '{text}' error: {e}")
            self._send(f"Error procesando comando: {e}")

    def _send(self, text):
        try:
            requests.post(
                f"https://api.telegram.org/bot{self._token}/sendMessage",
                json={'chat_id': self._chat_id, 'text': text, 'parse_mode': 'Markdown'},
                timeout=10
            )
        except Exception as e:
            logger.warning(f"Telegram send error: {e}")

    def _dispatch_command(self, text):
        cmd = text.split()[0].lower().split('@')[0]  # /cmd@bot -> /cmd
        if cmd == '/status': self._cmd_status()
        elif cmd == '/track': self._cmd_track()
        elif cmd in ('/posiciones', '/pos', '/abiertas'): self._cmd_positions()
        elif cmd == '/recent': self._cmd_recent()
        elif cmd == '/pause': self._cmd_pause()
        elif cmd == '/resume': self._cmd_resume()
        elif cmd == '/kill': self._cmd_kill()
        elif cmd == '/help' or cmd == '/start': self._cmd_help()
        else: self._send(f"Comando desconocido: `{cmd}`. Usa /help.")

    def _cmd_help(self):
        self._send(
            "*AIdan bot* — comandos:\n\n"
            "/status — Balance + PnL del día + posiciones\n"
            "/posiciones — Abiertas ahora: gana/pierde y cuánto\n"
            "/track — Stats Triple Track (M5/M15/H1)\n"
            "/recent — Ultimas 5 estrategias\n"
            "/pause — Pausa MT5 trading\n"
            "/resume — Reanuda MT5 trading\n"
            "/kill — Emergency stop\n"
            "/help — Esta lista"
        )

    def _cmd_status(self):
        from src.common.config import Config
        mt5_exec = self.mt5_provider() if self.mt5_provider else None
        lines = [f"*AIdan v{Config.VERSION}*"]
        if mt5_exec and mt5_exec.is_ready():
            try:
                info = mt5_exec._mt5.account_info() if mt5_exec._mt5 else None
                if info:
                    lines.append(f"Balance: ${info.balance:.2f}")
                # v3.40.24: PnL del DIA (broker-truth, deals del dia AR con comision),
                # NO el total historico (balance-1000). Sin equity/free-margin (pedido del user).
                try:
                    _dp = mt5_exec.get_daily_pnl()
                    lines.append(f"PnL del día: ${_dp:+.2f}")
                except Exception:
                    pass
                positions = mt5_exec._mt5.positions_get(symbol='EURUSD')
                lines.append(f"Posiciones abiertas: {len(positions) if positions else 0}")
                # Kill switch (instance attribute)
                kill = getattr(mt5_exec, 'kill_switch', False)
                lines.append(f"Status: {'OFF ⏸ (kill switch)' if kill else 'ON ✅'}")
            except Exception as e:
                lines.append(f"MT5 error: {e}")
        else:
            lines.append("MT5: desconectado")
        self._send("\n".join(lines))

    def _cmd_positions(self):
        """v3.40.25 — Posiciones abiertas AHORA con P&L flotante (gana/pierde y cuánto)."""
        mt5_exec = self.mt5_provider() if self.mt5_provider else None
        if not (mt5_exec and mt5_exec.is_ready() and mt5_exec._mt5):
            self._send("MT5: desconectado"); return
        try:
            import re as _re
            positions = mt5_exec._mt5.positions_get(symbol='EURUSD') or []
            if not positions:
                self._send("Sin posiciones abiertas."); return
            lines = ["*Posiciones abiertas*"]
            total = 0.0
            for p in positions:
                total += p.profit
                _dir = 'CALL' if p.type == 0 else 'PUT'
                _m = _re.search(r'AIdan #(\d+)', p.comment or '')
                _sid = _m.group(1) if _m else '?'
                pips = ((p.price_current - p.price_open) if p.type == 0
                        else (p.price_open - p.price_current)) * 10000
                _ico = '🟢' if p.profit >= 0 else '🔴'
                lines.append(f"{_ico} #{_sid} {_dir}  ${p.profit:+.2f} ({pips:+.1f}p)")
                lines.append(f"   {p.price_open:.5f} → {p.price_current:.5f} · lote {p.volume}")
            _tico = '🟢' if total >= 0 else '🔴'
            lines.append(f"\n{_tico} *Total flotante: ${total:+.2f}*")
            self._send("\n".join(lines))
        except Exception as e:
            self._send(f"Error: {e}")

    def _cmd_track(self):
        try:
            from src.common.db import get_strategy_performance_by_track
            stats = get_strategy_performance_by_track()
            lines = ["*Triple Track stats*"]
            for label, key in [('M5 (A)', 'track_a_m5'), ('M15 (B)', 'track_b_m15'), ('H1 (C)', 'track_c_h1')]:
                t = stats.get(key, {})
                pf = t.get('profit_factor', 0)
                pf_str = '∞' if pf >= 999 else f"{pf:.2f}" if pf else '-'
                pnl = t.get('sum_pnl', 0)
                lines.append(
                    f"\n*{label}*: {t.get('total', 0)} trades, WR {t.get('win_rate', 0):.0f}%, "
                    f"PF {pf_str}, PnL ${pnl:+.2f}"
                )
            self._send("\n".join(lines))
        except Exception as e:
            self._send(f"Error: {e}")

    def _cmd_recent(self):
        try:
            from src.common.db import DB_PATH
            conn = sqlite3.connect(DB_PATH, timeout=15.0)
            cur = conn.cursor()
            cur.execute("""
                SELECT id, direction, status, mt5_pnl, trigger_type, created_at
                FROM auto_strategies
                ORDER BY id DESC LIMIT 5
            """)
            rows = cur.fetchall()
            conn.close()
            if not rows:
                self._send("Sin estrategias recientes.")
                return
            # v3.30.3 — Telegram Markdown parser interpreta '_' como italic delim.
            # status='auto_win'/'auto_loss' rompia parsing (HTTP 400). Escapamos.
            def esc(s):
                return str(s or '').replace('_', '\\_').replace('*', '\\*')
            lines = ["*Ultimas 5 estrategias:*"]
            for r in rows:
                rid, direction, status, pnl, trigger, created = r
                pnl_str = f"${pnl:+.2f}" if pnl is not None else "..."
                trig_short = esc((trigger or '?')[:14])
                lines.append(f"#{rid} `{trig_short}` {esc(direction)} {esc(status)} {pnl_str}")
            self._send("\n".join(lines))
        except Exception as e:
            self._send(f"Error: {e}")

    def _cmd_pause(self):
        try:
            mt5_exec = self.mt5_provider() if self.mt5_provider else None
            if mt5_exec:
                mt5_exec.kill_switch = True
                self._send("⏸ Trading PAUSADO (kill switch ON). Usa /resume para reanudar.")
            else:
                self._send("MT5 executor no disponible.")
        except Exception as e:
            self._send(f"Error: {e}")

    def _cmd_resume(self):
        try:
            mt5_exec = self.mt5_provider() if self.mt5_provider else None
            if mt5_exec:
                mt5_exec.kill_switch = False
                self._send("▶️ Trading REANUDADO (kill switch OFF).")
            else:
                self._send("MT5 executor no disponible.")
        except Exception as e:
            self._send(f"Error: {e}")

    def _cmd_kill(self):
        """Boton de panico. v3.53.0 — ANTES NO CERRABA NADA.

        La version previa hacia `mt5_exec.kill_switch = True` y RECIEN DESPUES exigia
        `if mt5_exec.is_ready()`, que es `connected and not kill_switch` => siempre False
        => las ~25 lineas de cierre eran codigo INALCANZABLE. El mensaje respondia
        "0 posicion(es) cerrada(s)", que se lee como "no habia posiciones" cuando en
        realidad quedaban abiertas, sin trailing y sin Position Manager (los dos filtran
        por mt5_status='filled', que nadie habia actualizado).

        Ahora delega en toggle(False), que cierra PRIMERO y levanta el flag despues — el
        mismo camino que ya usaba el kill switch del dashboard, que si funcionaba. De paso
        se borra la duplicacion del armado de ordenes y sus `except: pass`.
        """
        try:
            mt5_exec = self.mt5_provider() if self.mt5_provider else None
            if not mt5_exec:
                self._send("⚠️ *EMERGENCY KILL*\nMT5 executor no disponible: el kill switch "
                           "NO se pudo aplicar y las posiciones (si hay) siguen abiertas.")
                return

            closed, found = mt5_exec.toggle(False)

            if found == 0:
                detalle = "No habia posiciones abiertas."
            elif closed == found:
                detalle = f"{closed} posicion(es) cerrada(s)."
            else:
                detalle = (f"⚠️ Se cerraron {closed} de {found}. "
                           f"*{found - closed} SIGUEN ABIERTAS* — cerralas a mano en MT5.")
            self._send(f"🚨 *EMERGENCY KILL*\nKill switch ON. {detalle}")
        except Exception as e:
            # El flag pudo quedar sin aplicar: decirlo en vez de un "Error:" pelado.
            self._send(f"🚨 *EMERGENCY KILL — FALLO*\n`{e}`\n"
                       f"Verifica el estado en MT5 y en el dashboard.")
