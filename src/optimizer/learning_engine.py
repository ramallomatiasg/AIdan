"""
Learning Engine: continuous self-improvement for AIdan.
- Online mode (market open): lightweight metric snapshots every 30min
- Offline mode (market closed): deep analysis every 4 hours
  - SL/TP optimization
  - Session analysis
  - Confidence calibration
  - News category learning
  - Pattern mining
  - Self-evaluation reports
"""
import json
import time
import sqlite3
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev

TZ_AR = timezone(timedelta(hours=-3))
TZ_UTC = timezone.utc

# Forex market hours
MARKET_CLOSE_HOUR_UTC = 22  # Friday 22:00 UTC
MARKET_OPEN_HOUR_UTC = 22   # Sunday 22:00 UTC
# Major holidays when forex is closed (month, day)
FOREX_HOLIDAYS = [
    (1, 1),   # New Year
    (12, 25), # Christmas
]

MIN_TRADES_FOR_ANALYSIS = 3


def _wcount(trades):
    """Weighted trade count (shared trades count as 0.5)."""
    return sum(t.get('_weight', 1.0) for t in trades)


def _wwins(trades):
    """Weighted win count."""
    return sum(t.get('_weight', 1.0) for t in trades if t.get('result') == 'win')
MIN_IMPROVEMENT_PCT = 2.0


class LearningEngine:
    def __init__(self, logger, tuner=None):
        self.logger = logger
        self.tuner = tuner
        self._last_online_tick = 0
        self._last_offline_tick = 0
        self._online_interval = 1800   # 30 min
        self._offline_interval = 14400  # 4 hours
        self._last_mode = None
        self._shared = None
        # Initialize shared learning (lazy — only connects if configured)
        try:
            from src.cloud.shared_learning import SharedLearning
            self._shared = SharedLearning(logger)
        except Exception as e:
            self.logger.warning(f"Shared Learning init skipped: {e}")

    def is_market_open(self):
        """Check if forex market is currently open."""
        now = datetime.now(TZ_UTC)
        weekday = now.weekday()  # 0=Mon, 4=Fri, 5=Sat, 6=Sun
        hour = now.hour

        # Check holidays
        if (now.month, now.day) in FOREX_HOLIDAYS:
            return False

        # Good Friday (dynamic — approximate: check if it's a Friday in March/April near Easter)
        # Simple heuristic: rely on the main check below

        # Saturday: always closed
        if weekday == 5:
            return False
        # Sunday: closed until 22:00 UTC
        if weekday == 6 and hour < MARKET_OPEN_HOUR_UTC:
            return False
        # Friday: closed after 22:00 UTC
        if weekday == 4 and hour >= MARKET_CLOSE_HOUR_UTC:
            return False

        return True

    def tick(self):
        """Called every iteration of the main loop. Decides what to run."""
        now = time.time()
        market_open = self.is_market_open()

        if self._last_mode != market_open:
            mode_str = "ONLINE (mercado abierto)" if market_open else "OFFLINE (mercado cerrado)"
            self.logger.info(f"Learning Engine: modo {mode_str}")
            self._last_mode = market_open

        if market_open:
            # Online: lightweight snapshots every 30 min
            if now - self._last_online_tick >= self._online_interval:
                self._last_online_tick = now
                try:
                    self._snapshot_metrics()
                except Exception as e:
                    self.logger.error(f"Learning snapshot error: {e}")
            # Online deep analysis every 2 hours (7200s) to keep insights fresh
            if now - self._last_offline_tick >= 7200:
                self._last_offline_tick = now
                try:
                    self.logger.info("Learning Engine: running online deep analysis (every 2h)")
                    self._run_deep_analysis()
                except Exception as e:
                    self.logger.error(f"Learning online deep analysis error: {e}")
        else:
            # Offline: deep analysis every 4 hours
            if now - self._last_offline_tick >= self._offline_interval:
                self._last_offline_tick = now
                try:
                    self._run_deep_analysis()
                except Exception as e:
                    self.logger.error(f"Learning deep analysis error: {e}")

        # Shared Learning: sync trades & fetch remote insights
        if self._shared:
            try:
                self._shared.tick()
            except Exception as e:
                self.logger.warning(f"Shared Learning tick error: {e}")

    def get_shared_learning(self):
        """Get the SharedLearning instance (for API endpoints)."""
        return self._shared

    def get_status(self):
        """Return current learning status for API/dashboard."""
        from src.common.db import get_archive_stats, get_learning_insights
        market_open = self.is_market_open()
        stats = get_archive_stats()
        recent_insights = get_learning_insights(5)
        return {
            'mode': 'online' if market_open else 'offline',
            'market_open': market_open,
            'archive_total': stats['total'],
            'overall_wr': stats['win_rate'],
            'avg_pips': stats['avg_pips'],
            'total_pips': stats['total_pips'],
            'last_online_tick': self._last_online_tick,
            'last_offline_tick': self._last_offline_tick,
            'recent_insights_count': len(recent_insights),
        }

    # ── Online Mode: Metric Snapshots ──

    def _snapshot_metrics(self):
        """Take a lightweight snapshot of current performance metrics."""
        from src.common.db import get_archive_stats, save_learning_metric
        stats = get_archive_stats()
        if stats['total'] == 0:
            return

        save_learning_metric('overall_wr', stats['win_rate'])
        save_learning_metric('avg_pips', stats['avg_pips'])
        save_learning_metric('total_trades', stats['total'])
        save_learning_metric('total_pips', stats['total_pips'])
        self.logger.info(f"Learning snapshot: WR={stats['win_rate']}% avg={stats['avg_pips']}p trades={stats['total']}")

    # ── Offline Mode: Deep Analysis ──

    def _run_deep_analysis(self):
        """Run comprehensive analysis when market is closed."""
        from src.common.db import get_trade_archive, get_shared_trade_cache
        local_trades = get_trade_archive(500)
        shared_trades = get_shared_trade_cache(500)

        # Tag with weight: local=1.0, shared=0.5
        for t in local_trades:
            t['_weight'] = 1.0
        for t in shared_trades:
            t['_weight'] = 0.5

        trades = local_trades + shared_trades
        effective_count = _wcount(trades)
        if effective_count < MIN_TRADES_FOR_ANALYSIS:
            self.logger.info(f"Learning: not enough trades for deep analysis ({effective_count:.0f}/{MIN_TRADES_FOR_ANALYSIS})")
            return

        self.logger.info(f"Learning Engine: starting deep analysis ({len(local_trades)} local + {len(shared_trades)} shared = {effective_count:.0f} effective trades)")

        analysis_steps = [
            ('sl_tp', self._analyze_sl_tp),
            ('sessions', self._analyze_sessions),
            ('confidence', self._calibrate_confidence),
            ('news_categories', self._analyze_news_categories),
            ('patterns', self._mine_patterns),
            ('report', self._generate_report),
        ]
        completed = 0
        for name, func in analysis_steps:
            try:
                func(trades)
                completed += 1
            except Exception as e:
                self.logger.error(f"Learning analysis '{name}' failed: {e}")

        self.logger.info(f"Learning Engine: deep analysis complete ({completed}/{len(analysis_steps)} steps OK)")

    def _analyze_sl_tp(self, trades):
        """Analyze SL/TP effectiveness by setup type and volatility."""
        from src.common.db import save_learning_insight

        # Group by trigger_type + volatility
        groups = {}
        for t in trades:
            if not t.get('trigger_type') or t['result'] not in ('win', 'loss'):
                continue
            key = f"{t['trigger_type']}|{t.get('volatility', 'unknown')}"
            groups.setdefault(key, []).append(t)

        insights = []
        for key, group in groups.items():
            wc = _wcount(group)
            if wc < MIN_TRADES_FOR_ANALYSIS:
                continue

            trigger, vol = key.split('|')
            sl_hits = [t for t in group if t.get('sl_hit')]
            tp_hits = [t for t in group if t.get('tp_hit')]
            sl_hit_rate = _wcount(sl_hits) / wc * 100

            # Average SL/TP distances
            sl_dists = [t['sl_pips'] for t in group if t.get('sl_pips') and t['sl_pips'] > 0]
            tp_dists = [t['tp_pips'] for t in group if t.get('tp_pips') and t['tp_pips'] > 0]

            if not sl_dists:
                continue

            avg_sl = mean(sl_dists)
            avg_tp = mean(tp_dists) if tp_dists else 0

            # SL too tight? If SL hit rate > 60% and avg SL < 5 pips
            if sl_hit_rate > 60 and avg_sl < 5:
                insight = f"SL en {trigger} ({vol} vol): SL promedio {avg_sl:.1f}p se activa {sl_hit_rate:.0f}% del tiempo. Recomendacion: aumentar SL minimo."
                save_learning_insight('sl_tp', insight, {
                    'trigger_type': trigger, 'volatility': vol,
                    'sl_hit_rate': round(sl_hit_rate, 1),
                    'avg_sl_pips': round(avg_sl, 1),
                    'avg_tp_pips': round(avg_tp, 1),
                    'sample_size': round(wc),
                    'recommendation': 'increase_sl',
                }, f"SL hit rate {sl_hit_rate:.0f}% para {trigger}/{vol}")
                insights.append(insight)

            # TP too ambitious? If TP hit rate < 30% and avg TP > 15 pips
            tp_hit_rate = _wcount(tp_hits) / wc * 100
            if tp_hit_rate < 30 and avg_tp > 15:
                insight = f"TP en {trigger} ({vol} vol): TP promedio {avg_tp:.1f}p se alcanza solo {tp_hit_rate:.0f}%. Recomendacion: reducir TP."
                save_learning_insight('sl_tp', insight, {
                    'trigger_type': trigger, 'volatility': vol,
                    'tp_hit_rate': round(tp_hit_rate, 1),
                    'avg_tp_pips': round(avg_tp, 1),
                    'sample_size': round(wc),
                    'recommendation': 'decrease_tp',
                }, f"TP hit rate {tp_hit_rate:.0f}% para {trigger}/{vol}")
                insights.append(insight)

        if insights:
            self.logger.info(f"Learning SL/TP: {len(insights)} insights generados")

    def _analyze_sessions(self, trades):
        """Analyze win rate by trading session and hour."""
        from src.common.db import save_learning_insight

        # By session
        sessions = {}
        for t in trades:
            if t['result'] not in ('win', 'loss'):
                continue
            w = t.get('_weight', 1.0)
            s = t.get('session', 'unknown')
            sessions.setdefault(s, {'wins': 0, 'losses': 0, 'total': 0})
            sessions[s]['total'] += w
            if t['result'] == 'win':
                sessions[s]['wins'] += w
            else:
                sessions[s]['losses'] += w

        for session, data in sessions.items():
            if data['total'] < MIN_TRADES_FOR_ANALYSIS:
                continue
            wr = data['wins'] / data['total'] * 100
            if wr < 35:
                insight = f"Sesion {session}: WR {wr:.0f}% ({data['wins']:.0f}W/{data['losses']:.0f}L, {data['total']:.0f} trades). Rendimiento pobre."
                save_learning_insight('session', insight, {
                    'session': session, 'win_rate': round(wr, 1),
                    'total': round(data['total']),
                    'recommendation': 'avoid_session',
                }, f"WR bajo en sesion {session}")
            elif wr > 65:
                insight = f"Sesion {session}: WR {wr:.0f}% ({data['wins']:.0f}W/{data['losses']:.0f}L). Mejor horario para operar."
                save_learning_insight('session', insight, {
                    'session': session, 'win_rate': round(wr, 1),
                    'total': round(data['total']),
                    'recommendation': 'prefer_session',
                }, f"WR alto en sesion {session}")

        # By hour
        hours = {}
        for t in trades:
            if t['result'] not in ('win', 'loss'):
                continue
            w = t.get('_weight', 1.0)
            h = t.get('hour_utc', 0)
            hours.setdefault(h, {'wins': 0, 'losses': 0, 'total': 0})
            hours[h]['total'] += w
            if t['result'] == 'win':
                hours[h]['wins'] += w
            else:
                hours[h]['losses'] += w

        self.logger.info(f"Learning sessions: analyzed {len(sessions)} sessions, {len(hours)} hours")

    def _calibrate_confidence(self, trades):
        """Compare predicted confidence vs actual win rates by bracket."""
        from src.common.db import save_learning_insight

        brackets = {
            '50-60': [], '60-70': [], '70-80': [], '80+': []
        }
        for t in trades:
            if t['result'] not in ('win', 'loss'):
                continue
            conf = t.get('confidence', 0)
            if conf >= 80:
                brackets['80+'].append(t)
            elif conf >= 70:
                brackets['70-80'].append(t)
            elif conf >= 60:
                brackets['60-70'].append(t)
            elif conf >= 50:
                brackets['50-60'].append(t)

        calibration = {}
        for bracket, group in brackets.items():
            wc = _wcount(group)
            if wc < MIN_TRADES_FOR_ANALYSIS:
                continue
            wins = _wwins(group)
            actual_wr = wins / wc * 100
            # Expected WR is roughly the confidence bracket midpoint
            expected_wr = {'50-60': 55, '60-70': 65, '70-80': 75, '80+': 85}[bracket]
            calibration[bracket] = {
                'expected_wr': expected_wr,
                'actual_wr': round(actual_wr, 1),
                'trades': round(wc),
                'deviation': round(actual_wr - expected_wr, 1),
            }

            if abs(actual_wr - expected_wr) > 15:
                direction = "sobreestima" if actual_wr < expected_wr else "subestima"
                insight = f"Confidence {bracket}%: WR real {actual_wr:.0f}% vs esperado ~{expected_wr}% ({round(wc)} trades). El modelo {direction} la confianza."
                save_learning_insight('confidence', insight, calibration[bracket],
                    f"Calibracion: {bracket}% → WR real {actual_wr:.0f}%")

        if calibration:
            self.logger.info(f"Learning confidence calibration: {json.dumps(calibration)}")

    def _analyze_news_categories(self, trades):
        """Analyze which news categories produce best/worst results."""
        from src.common.db import save_learning_insight

        # Keyword-based categorization
        categories = {
            'fed_rate': ['fed', 'rate', 'fomc', 'powell', 'interest rate', 'federal reserve'],
            'employment': ['employment', 'nonfarm', 'payroll', 'jobs', 'unemployment', 'labor'],
            'gdp_growth': ['gdp', 'growth', 'recession', 'economy', 'economic'],
            'inflation': ['inflation', 'cpi', 'ppi', 'consumer price', 'producer price'],
            'geopolitical': ['war', 'conflict', 'iran', 'tariff', 'sanction', 'geopolit'],
            'oil_energy': ['oil', 'crude', 'opec', 'energy', 'gas', 'petroleum'],
            'central_bank': ['ecb', 'boe', 'boj', 'central bank', 'monetary policy'],
            'market_sentiment': ['stock', 'equity', 's&p', 'nasdaq', 'dow', 'market', 'rally', 'crash'],
        }

        cat_results = {}
        for t in trades:
            if t['result'] not in ('win', 'loss'):
                continue
            w = t.get('_weight', 1.0)
            matched_cats = []

            # Shared trades have pre-categorized news_category
            if t.get('news_category') and t['news_category'] in categories:
                matched_cats.append(t['news_category'])
            # Local trades: match by news_title keywords
            elif t.get('news_title'):
                title_lower = t['news_title'].lower()
                for cat, keywords in categories.items():
                    if any(kw in title_lower for kw in keywords):
                        matched_cats.append(cat)
            else:
                continue

            for cat in matched_cats:
                cat_results.setdefault(cat, {'wins': 0, 'losses': 0, 'total': 0})
                cat_results[cat]['total'] += w
                if t['result'] == 'win':
                    cat_results[cat]['wins'] += w
                else:
                    cat_results[cat]['losses'] += w

        for cat, data in cat_results.items():
            if data['total'] < 3:
                continue
            wr = data['wins'] / data['total'] * 100
            if wr > 65 or wr < 35:
                quality = "excelente" if wr > 65 else "pobre"
                insight = f"Noticias '{cat}': WR {wr:.0f}% ({data['wins']:.0f}W/{data['losses']:.0f}L, {data['total']:.0f} trades). Rendimiento {quality}."
                save_learning_insight('news_category', insight, {
                    'category': cat, 'win_rate': round(wr, 1),
                    'total': round(data['total']),
                }, f"News cat '{cat}' WR={wr:.0f}%")

        if cat_results:
            self.logger.info(f"Learning news categories: {len(cat_results)} categorias analizadas")

    def _mine_patterns(self, trades):
        """Cross-correlate dimensions to find winning/losing patterns."""
        from src.common.db import save_learning_insight

        # Build pattern keys: direction × htf_bias × session × trigger_type
        patterns = {}
        for t in trades:
            if t['result'] not in ('win', 'loss'):
                continue
            w = t.get('_weight', 1.0)
            direction = t.get('direction', '?')
            htf = t.get('htf_bias', 'unknown') or 'unknown'
            session = t.get('session', 'unknown') or 'unknown'
            trigger = t.get('trigger_type', 'unknown') or 'unknown'

            key = f"{direction}|{htf}|{session}|{trigger}"
            patterns.setdefault(key, {'wins': 0, 'losses': 0, 'total': 0, 'pips': []})
            patterns[key]['total'] += w
            patterns[key]['pips'].append(t.get('pips', 0))
            if t['result'] == 'win':
                patterns[key]['wins'] += w
            else:
                patterns[key]['losses'] += w

        best_patterns = []
        worst_patterns = []
        for key, data in patterns.items():
            if data['total'] < MIN_TRADES_FOR_ANALYSIS:
                continue
            wr = data['wins'] / data['total'] * 100
            avg_pips = mean(data['pips']) if data['pips'] else 0
            parts = key.split('|')
            pattern_info = {
                'direction': parts[0], 'htf_bias': parts[1],
                'session': parts[2], 'trigger': parts[3],
                'win_rate': round(wr, 1), 'avg_pips': round(avg_pips, 2),
                'trades': round(data['total']),
            }

            if wr >= 70:
                best_patterns.append(pattern_info)
            elif wr <= 30:
                worst_patterns.append(pattern_info)

        for p in best_patterns:
            insight = f"Patron ganador: {p['direction']} + HTF {p['htf_bias']} + {p['session']} + {p['trigger']} → WR {p['win_rate']}% ({p['trades']} trades, avg {p['avg_pips']}p)"
            save_learning_insight('pattern', insight, p, "Patron identificado como ganador")

        for p in worst_patterns:
            insight = f"Patron perdedor: {p['direction']} + HTF {p['htf_bias']} + {p['session']} + {p['trigger']} → WR {p['win_rate']}% ({p['trades']} trades, avg {p['avg_pips']}p)"
            save_learning_insight('pattern', insight, p, "Patron identificado como perdedor — considerar bloquear")

        if best_patterns or worst_patterns:
            self.logger.info(f"Learning patterns: {len(best_patterns)} ganadores, {len(worst_patterns)} perdedores")

    def _generate_report(self, trades):
        """Generate a self-evaluation report."""
        from src.common.db import save_learning_insight, get_archive_stats

        stats = get_archive_stats()
        if stats['total'] == 0:
            return

        # WR by direction (local stats for report display)
        dir_stats = {}
        for t in trades:
            if t['result'] not in ('win', 'loss'):
                continue
            w = t.get('_weight', 1.0)
            d = t.get('direction', '?')
            dir_stats.setdefault(d, {'wins': 0, 'losses': 0})
            if t['result'] == 'win':
                dir_stats[d]['wins'] += w
            else:
                dir_stats[d]['losses'] += w

        # WR by trigger (combined local + shared for insights)
        trigger_stats = {}
        for t in trades:
            if t['result'] not in ('win', 'loss'):
                continue
            w = t.get('_weight', 1.0)
            tr = t.get('trigger_type', 'unknown') or 'unknown'
            trigger_stats.setdefault(tr, {'wins': 0, 'losses': 0})
            if t['result'] == 'win':
                trigger_stats[tr]['wins'] += w
            else:
                trigger_stats[tr]['losses'] += w

        # Save trigger_type insights for confidence adjustments
        for tr, s in trigger_stats.items():
            total = s['wins'] + s['losses']
            if total < MIN_TRADES_FOR_ANALYSIS:
                continue
            wr = s['wins'] / total * 100
            save_learning_insight('trigger_type',
                f"Trigger {tr}: WR {wr:.0f}% ({s['wins']:.0f}W/{s['losses']:.0f}L, {total:.0f} trades)",
                {'trigger_type': tr, 'win_rate': round(wr, 1), 'total': round(total)},
                f"Trigger WR: {tr}={wr:.0f}%")

        # Build report
        lines = []
        lines.append(f"=== REPORTE DE AUTO-EVALUACION ===")
        lines.append(f"Fecha: {datetime.now(TZ_AR).strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Trades analizados: {stats['total']} ({stats['wins']}W / {stats['losses']}L)")
        lines.append(f"Win Rate global: {stats['win_rate']}%")
        lines.append(f"Pips promedio: {stats['avg_pips']}")
        lines.append(f"Pips totales: {stats['total_pips']}")
        lines.append("")

        lines.append("Por direccion:")
        for d, s in dir_stats.items():
            total = s['wins'] + s['losses']
            wr = s['wins'] / total * 100 if total else 0
            lines.append(f"  {d}: {wr:.0f}% ({s['wins']:.0f}W/{s['losses']:.0f}L)")

        lines.append("")
        lines.append("Por tipo de señal:")
        for tr, s in sorted(trigger_stats.items(), key=lambda x: x[1]['wins'] + x[1]['losses'], reverse=True):
            total = s['wins'] + s['losses']
            wr = s['wins'] / total * 100 if total else 0
            emoji = "✅" if wr >= 60 else ("⚠️" if wr >= 40 else "❌")
            lines.append(f"  {emoji} {tr}: {wr:.0f}% ({s['wins']:.0f}W/{s['losses']:.0f}L, {total:.0f} trades)")

        # Top pips contributors (weighted)
        pips_by_trigger = {}
        for t in trades:
            if t['result'] not in ('win', 'loss'):
                continue
            w = t.get('_weight', 1.0)
            tr = t.get('trigger_type', 'unknown') or 'unknown'
            pips_by_trigger.setdefault(tr, 0)
            pips_by_trigger[tr] += t.get('pips', 0) * w

        lines.append("")
        lines.append("Pips netos por tipo:")
        for tr, pips in sorted(pips_by_trigger.items(), key=lambda x: x[1], reverse=True):
            sign = "+" if pips >= 0 else ""
            lines.append(f"  {tr}: {sign}{pips:.1f}p")

        report = "\n".join(lines)

        save_learning_insight('report', report, {
            'stats': stats,
            'direction_stats': {d: {'wr': round(s['wins'] / max(s['wins'] + s['losses'], 1) * 100, 1), **s}
                                for d, s in dir_stats.items()},
            'trigger_stats': {tr: {'wr': round(s['wins'] / max(s['wins'] + s['losses'], 1) * 100, 1), **s}
                              for tr, s in trigger_stats.items()},
        }, "Reporte semanal generado")

        self.logger.info(f"Learning report generated: WR={stats['win_rate']}% total={stats['total']} pips={stats['total_pips']}")

    # ── Data for Dashboard ──

    def get_session_heatmap(self):
        """Get setup × session win rate matrix for dashboard heatmap."""
        from src.common.db import get_trade_archive
        trades = get_trade_archive(500)

        matrix = {}
        for t in trades:
            if t['result'] not in ('win', 'loss'):
                continue
            trigger = t.get('trigger_type', 'unknown') or 'unknown'
            session = t.get('session', 'unknown') or 'unknown'
            key = f"{trigger}|{session}"
            matrix.setdefault(key, {'wins': 0, 'losses': 0, 'total': 0})
            matrix[key]['total'] += 1
            if t['result'] == 'win':
                matrix[key]['wins'] += 1
            else:
                matrix[key]['losses'] += 1

        result = {}
        for key, data in matrix.items():
            trigger, session = key.split('|')
            result.setdefault(trigger, {})
            wr = data['wins'] / data['total'] * 100 if data['total'] else 0
            result[trigger][session] = {
                'wr': round(wr, 1),
                'trades': data['total'],
            }
        return result

    def get_sl_tp_analysis(self):
        """Get SL/TP analysis data for dashboard."""
        from src.common.db import get_trade_archive
        trades = get_trade_archive(500)

        analysis = {}
        for t in trades:
            if t['result'] not in ('win', 'loss'):
                continue
            trigger = t.get('trigger_type', 'unknown') or 'unknown'
            analysis.setdefault(trigger, {
                'sl_hit_count': 0, 'tp_hit_count': 0, 'total': 0,
                'sl_dists': [], 'tp_dists': [], 'pips_win': [], 'pips_loss': [],
            })
            a = analysis[trigger]
            a['total'] += 1
            if t.get('sl_hit'):
                a['sl_hit_count'] += 1
            if t.get('tp_hit'):
                a['tp_hit_count'] += 1
            if t.get('sl_pips') and t['sl_pips'] > 0:
                a['sl_dists'].append(t['sl_pips'])
            if t.get('tp_pips') and t['tp_pips'] > 0:
                a['tp_dists'].append(t['tp_pips'])
            if t['result'] == 'win':
                a['pips_win'].append(t.get('pips', 0))
            else:
                a['pips_loss'].append(t.get('pips', 0))

        result = {}
        for trigger, a in analysis.items():
            result[trigger] = {
                'total': a['total'],
                'sl_hit_rate': round(a['sl_hit_count'] / max(a['total'], 1) * 100, 1),
                'tp_hit_rate': round(a['tp_hit_count'] / max(a['total'], 1) * 100, 1),
                'avg_sl_pips': round(mean(a['sl_dists']), 1) if a['sl_dists'] else 0,
                'avg_tp_pips': round(mean(a['tp_dists']), 1) if a['tp_dists'] else 0,
                'avg_pips_win': round(mean(a['pips_win']), 2) if a['pips_win'] else 0,
                'avg_pips_loss': round(mean(a['pips_loss']), 2) if a['pips_loss'] else 0,
            }
        return result
