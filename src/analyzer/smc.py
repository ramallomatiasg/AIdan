"""
Smart Money Concepts (SMC) Engine for EUR/USD scalping.
Detects demand/supply zones, checks multi-timeframe alignment,
and provides entry confirmations based on LTF structure breaks.
"""
import json
import os
import time
from datetime import datetime

try:
    from src.common.db import get_setup_win_rates
except Exception:
    get_setup_win_rates = None


class ZoneDetector:
    """Detects demand and supply zones from candle data."""

    def __init__(self, min_impulse_multiplier=2.0, max_touches=3):
        self.min_impulse_multiplier = min_impulse_multiplier
        self.max_touches = max_touches

    def detect_zones(self, candles, timeframe='M5'):
        """
        Find demand and supply zones.
        Demand: last bullish candle before a strong impulse UP.
        Supply: last bearish candle before a strong impulse DOWN.
        Returns list of zone dicts.
        """
        if len(candles) < 10:
            return []

        zones = []
        # Calculate ATR for impulse threshold
        ranges = [(c['high'] - c['low']) for c in candles[-30:]]
        atr = sum(ranges) / len(ranges) if ranges else 0.0001

        for i in range(2, len(candles) - 3):
            c = candles[i]
            body = c['close'] - c['open']

            # Check for impulse AFTER this candle (next 2-3 candles)
            impulse_up = self._check_impulse(candles, i + 1, 'up', atr)
            impulse_down = self._check_impulse(candles, i + 1, 'down', atr)

            # Demand zone: bullish or small candle before impulse UP
            if impulse_up and body >= -atr * 0.5:  # not strongly bearish
                zone = {
                    'type': 'demand',
                    'top': max(c['open'], c['close']),
                    'bottom': c['low'],
                    'timeframe': timeframe,
                    'candle_index': i,
                    'strength': 3,  # starts at 3, decreases with touches
                    'touches': 0,
                    'time': c.get('datetime', ''),
                }
                zones.append(zone)

            # Supply zone: bearish or small candle before impulse DOWN
            if impulse_down and body <= atr * 0.5:  # not strongly bullish
                zone = {
                    'type': 'supply',
                    'top': c['high'],
                    'bottom': min(c['open'], c['close']),
                    'timeframe': timeframe,
                    'candle_index': i,
                    'strength': 3,
                    'touches': 0,
                    'time': c.get('datetime', ''),
                }
                zones.append(zone)

        # Count touches and filter mitigated zones
        zones = self._count_touches(zones, candles)

        # Keep only the closest zones (max 3 demand + 3 supply)
        if candles:
            price = candles[-1]['close']
            demand = [z for z in zones if z['type'] == 'demand']
            supply = [z for z in zones if z['type'] == 'supply']
            demand.sort(key=lambda z: abs(price - (z['top'] + z['bottom']) / 2))
            supply.sort(key=lambda z: abs(price - (z['top'] + z['bottom']) / 2))
            zones = demand[:3] + supply[:3]

        return zones

    def _check_impulse(self, candles, start_idx, direction, atr):
        """Check if there's an impulse move starting at start_idx."""
        if start_idx + 2 > len(candles):
            return False

        threshold = atr * self.min_impulse_multiplier
        total_move = 0

        for i in range(start_idx, min(start_idx + 3, len(candles))):
            c = candles[i]
            move = c['close'] - c['open']
            rng = c['high'] - c['low']

            if direction == 'up' and move > 0:
                total_move += move
            elif direction == 'down' and move < 0:
                total_move += abs(move)
            else:
                break  # opposite candle breaks the impulse

        return total_move > threshold

    def _count_touches(self, zones, candles):
        """Count how many times price revisited each zone."""
        active = []
        for zone in zones:
            touches = 0
            for c in candles[zone['candle_index'] + 3:]:
                # Price enters the zone
                if c['low'] <= zone['top'] and c['high'] >= zone['bottom']:
                    touches += 1

            zone['touches'] = touches
            zone['strength'] = max(0, 3 - touches)

            if touches < self.max_touches:
                active.append(zone)

        return active


class ConfirmationEngine:
    """
    Checks for entry confirmations based on SMC methodology:
    1. HTF trend must be clear (H1/M15)
    2. Price must be at a demand/supply zone
    3. LTF (M5) must show confirmation (new HH for CALL, new LL for PUT)
    """

    def __init__(self, logger, rules=None):
        self.logger = logger
        self.rules = rules or {}
        self._last_confirmation = {}  # prevent duplicate signals

    def check(self, mtf_state, zones_by_tf):
        """
        Check for confirmed setups.
        mtf_state: from MTFAnalyzer.get_mtf_state()
        zones_by_tf: {'H1': [...], 'M15': [...], 'M5': [...]}
        Returns list of confirmed setups.
        """
        setups = []

        h1 = mtf_state.get('H1', {})
        m15 = mtf_state.get('M15', {})
        m5 = mtf_state.get('M5', {})

        h1_trend = h1.get('trend', 'neutral')
        m15_trend = m15.get('trend', 'neutral')
        price = m5.get('price', 0)

        if not price:
            return []

        # Determine HTF bias
        htf_bias, bias_strength = self._get_htf_bias(h1_trend, m15_trend)
        if htf_bias == 'neutral':
            return []  # No clear HTF direction, no setup

        # Collect all zones from HTF (and M5 for weak bias)
        htf_zones = []
        scan_tfs = ['H1', 'M15'] if bias_strength != 'weak' else ['M15', 'M5']
        for tf in scan_tfs:
            for z in zones_by_tf.get(tf, []):
                z['source_tf'] = tf
                htf_zones.append(z)

        # Check if price is at a relevant zone
        active_zone = self._find_active_zone(price, htf_zones, htf_bias)
        # If no zone in preferred direction, try opposite (reversal from zone)
        if not active_zone:
            opposite_bias = 'bearish' if htf_bias == 'bullish' else 'bullish'
            active_zone = self._find_active_zone(price, htf_zones, opposite_bias)
            if active_zone:
                # Reverse direction: hitting supply in bullish → skip (not counter-trend)
                # Only allow if bias is weak (HTF disagree → zone is more important)
                if bias_strength != 'weak':
                    active_zone = None
                else:
                    # Flip bias to follow the zone
                    htf_bias = opposite_bias

        if not active_zone:
            return []

        # Check LTF confirmation
        confirmation = self._check_ltf_confirmation(m5, htf_bias)
        if not confirmation:
            return []

        # Build setup
        direction = 'CALL' if htf_bias == 'bullish' else 'PUT'

        # Dedup check
        dedup_key = f"{direction}_{active_zone['type']}_{round(active_zone['top'], 4)}"
        now = time.time()
        if dedup_key in self._last_confirmation:
            if now - self._last_confirmation[dedup_key] < 300:  # 5 min cooldown
                return []
        self._last_confirmation[dedup_key] = now

        zone_label = f"zona de {'demanda' if active_zone['type'] == 'demand' else 'oferta'}"
        conf = self._calc_confidence(htf_bias, active_zone, confirmation, h1, m15, m5)
        # Reduce confidence when bias is weak (HTF disagree)
        if bias_strength == 'weak':
            conf = max(conf - 12, 50)
        elif bias_strength == 'moderate':
            conf = max(conf - 5, 50)

        setup = {
            'direction': direction,
            'confidence': conf,
            'htf_trend': htf_bias,
            'zone': active_zone,
            'confirmation': confirmation,
            'reason': (
                f"SMC {direction}: {zone_label} {active_zone['source_tf']} "
                f"({active_zone['bottom']:.5f}-{active_zone['top']:.5f}), "
                f"confirmación en M5 ({confirmation['description']}). "
                f"H1 {h1_trend}, M15 {m15_trend}. "
                f"Fuerza HTF: {bias_strength}."
            ),
            'coaching_msg': self._build_coaching_msg(htf_bias, active_zone, confirmation),
        }
        setups.append(setup)

        self.logger.info(f"SMC: Confirmed {direction} setup [{bias_strength}] - {setup['reason']}")
        return setups

    def get_status(self, mtf_state, zones_by_tf):
        """
        Get current SMC status for dashboard display.
        Always returns a status dict even when no confirmation.
        """
        h1 = mtf_state.get('H1', {})
        m15 = mtf_state.get('M15', {})
        m5 = mtf_state.get('M5', {})
        price = m5.get('price', 0)

        h1_trend = h1.get('trend', 'neutral')
        m15_trend = m15.get('trend', 'neutral')
        htf_bias, bias_strength = self._get_htf_bias(h1_trend, m15_trend)

        # Find nearest zone
        htf_zones = []
        scan_tfs = ['H1', 'M15'] if bias_strength != 'weak' else ['M15', 'M5']
        for tf in scan_tfs:
            for z in zones_by_tf.get(tf, []):
                z['source_tf'] = tf
                htf_zones.append(z)

        active_zone = self._find_active_zone(price, htf_zones, htf_bias) if htf_bias != 'neutral' else None
        confirmation = self._check_ltf_confirmation(m5, htf_bias) if active_zone else None

        strength_label = {'strong': 'fuerte', 'moderate': 'moderada', 'weak': 'debil'}.get(bias_strength, '')

        if confirmation and active_zone:
            status = 'confirmed'
            direction = 'CALL' if htf_bias == 'bullish' else 'PUT'
            msg = f"CONFIRMADO - {direction} (fuerza {strength_label})"
        elif active_zone:
            status = 'waiting'
            msg = f"En zona {active_zone['type']} {active_zone.get('source_tf', '')} — esperando confirmación M5"
        elif htf_bias != 'neutral':
            status = 'scanning'
            msg = f"HTF {'alcista' if htf_bias == 'bullish' else 'bajista'} ({strength_label}) — buscando zona"
        else:
            status = 'no_setup'
            msg = "Sin tendencia HTF clara"

        # Nearest zones for display
        demand_zones = sorted(
            [z for z in htf_zones if z['type'] == 'demand'],
            key=lambda z: abs(price - z['top']) if price else 0
        )[:2]
        supply_zones = sorted(
            [z for z in htf_zones if z['type'] == 'supply'],
            key=lambda z: abs(price - z['bottom']) if price else 0
        )[:2]

        return {
            'status': status,
            'message': msg,
            'htf_bias': htf_bias,
            'h1_trend': h1_trend,
            'm15_trend': m15_trend,
            'm5_trend': m5.get('trend', 'neutral'),
            'price': price,
            'active_zone': active_zone,
            'nearest_demand': demand_zones,
            'nearest_supply': supply_zones,
            'h1_structure': h1.get('structure', [])[-3:],
            'm15_structure': m15.get('structure', [])[-3:],
            'm5_structure': m5.get('structure', [])[-3:],
            'h1_last_sh': h1.get('last_swing_high'),
            'h1_last_sl': h1.get('last_swing_low'),
            'm15_last_sh': m15.get('last_swing_high'),
            'm15_last_sl': m15.get('last_swing_low'),
            'm5_last_sh': m5.get('last_swing_high'),
            'm5_last_sl': m5.get('last_swing_low'),
            'm5_bos': m5.get('bos'),
        }

    def _get_htf_bias(self, h1_trend, m15_trend):
        """Determine overall HTF bias from H1 and M15.
        Returns (bias, strength) where strength is 'strong', 'moderate', or 'weak'.
        """
        # Both agree → strong
        if h1_trend == m15_trend and h1_trend != 'neutral':
            return h1_trend, 'strong'
        # H1 has direction, M15 neutral → moderate
        if h1_trend != 'neutral' and m15_trend == 'neutral':
            return h1_trend, 'moderate'
        # M15 has direction, H1 neutral → moderate
        if m15_trend != 'neutral' and h1_trend == 'neutral':
            return m15_trend, 'moderate'
        # H1 has direction, M15 agrees or is neutral → moderate
        if h1_trend != 'neutral' and m15_trend in (h1_trend, 'neutral'):
            return h1_trend, 'moderate'
        # They disagree (e.g., H1 bearish, M15 bullish)
        # H1 is the dominant timeframe — use it as bias but with weak confidence
        if h1_trend != 'neutral':
            return h1_trend, 'weak'
        if m15_trend != 'neutral':
            return m15_trend, 'weak'
        return 'neutral', 'none'

    def _find_active_zone(self, price, zones, htf_bias):
        """Find if price is currently at a relevant zone."""
        pip = 0.0001
        zone_proximity = 8 * pip  # within 8 pips of zone edge

        relevant_type = 'demand' if htf_bias == 'bullish' else 'supply'

        for zone in zones:
            if zone['type'] != relevant_type:
                continue
            if zone['strength'] <= 0:
                continue

            # Check if price is in or near the zone
            if zone['type'] == 'demand':
                # Price touching or near the demand zone (from above)
                if zone['bottom'] - zone_proximity <= price <= zone['top'] + zone_proximity:
                    return zone
            else:
                # Price touching or near the supply zone (from below)
                if zone['bottom'] - zone_proximity <= price <= zone['top'] + zone_proximity:
                    return zone

        return None

    def _check_ltf_confirmation(self, m5_state, htf_bias):
        """
        Check if M5 shows confirmation:
        - For bullish: BOS alcista OR last structure is HH
        - For bearish: BOS bajista OR last structure is LL
        """
        bos = m5_state.get('bos')
        structure = m5_state.get('structure', [])

        if htf_bias == 'bullish':
            # Check BOS
            if bos and bos['type'] == 'bullish':
                return {'type': 'bos', 'description': f"BOS alcista en M5 sobre {bos['level']:.5f}"}
            # Check last structure point is HH
            if structure:
                last = structure[-1]
                if last['type'] == 'HH':
                    return {'type': 'structure', 'description': f"Nuevo HH en M5: {last['price']:.5f}"}

        elif htf_bias == 'bearish':
            if bos and bos['type'] == 'bearish':
                return {'type': 'bos', 'description': f"BOS bajista en M5 bajo {bos['level']:.5f}"}
            if structure:
                last = structure[-1]
                if last['type'] == 'LL':
                    return {'type': 'structure', 'description': f"Nuevo LL en M5: {last['price']:.5f}"}

        return None

    def _calc_confidence(self, htf_bias, zone, confirmation, h1, m15, m5):
        """Calculate confidence for the confirmed setup, with historical adjustment."""
        conf = 65  # base

        # Dynamic adjustment from historical win rate for SMC setups
        if get_setup_win_rates:
            try:
                rates = get_setup_win_rates()
                stats = rates.get('smc', {})
                if stats.get('total', 0) >= 5:
                    historical = 50 + int(stats['win_rate'] / 100 * 40)
                    conf = int(conf * 0.6 + historical * 0.4)
            except Exception:
                pass

        # H1 and M15 agree
        if h1.get('trend') == m15.get('trend'):
            conf += 10

        # Zone strength
        conf += zone.get('strength', 0) * 3  # up to +9

        # Confirmation type
        if confirmation['type'] == 'bos':
            conf += 8  # BOS is stronger confirmation
        else:
            conf += 4  # structure point

        # HTF zone is stronger
        if zone.get('source_tf') == 'H1':
            conf += 5

        return min(conf, 92)

    def _build_coaching_msg(self, htf_bias, zone, confirmation):
        """Build a coaching message for the trader."""
        direction = 'ALCISTA' if htf_bias == 'bullish' else 'BAJISTA'
        zone_type = 'demanda' if zone['type'] == 'demand' else 'oferta'
        return (
            f"Tendencia HTF {direction}. "
            f"Precio en zona de {zone_type} {zone.get('source_tf', '')} "
            f"({zone['bottom']:.5f}-{zone['top']:.5f}). "
            f"Confirmación: {confirmation['description']}. "
            f"Operá a favor de la tendencia."
        )


class SMCEngine:
    """
    Main SMC orchestrator. Integrates MTFAnalyzer, ZoneDetector, and ConfirmationEngine.
    """

    def __init__(self, logger, mtf_analyzer):
        self.logger = logger
        self.mtf = mtf_analyzer
        self.rules = self._load_rules()
        self.zone_detector = ZoneDetector(
            min_impulse_multiplier=self.rules.get('min_impulse_multiplier', 2.0),
            max_touches=self.rules.get('max_zone_touches', 3)
        )
        self.confirmation = ConfirmationEngine(logger, self.rules)
        self._mtf_state = None
        self._zones_by_tf = {}

    def update(self):
        """Fetch fresh data and update analysis."""
        self._mtf_state = self.mtf.get_mtf_state()

        # Detect zones per timeframe
        self._zones_by_tf = {}
        for tf in ['H1', 'M15', 'M5']:
            candles = self.mtf.get_candles(tf)
            if candles:
                self._zones_by_tf[tf] = self.zone_detector.detect_zones(candles, tf)

    def check_confirmations(self):
        """Check for confirmed SMC setups. Call after update()."""
        if not self._mtf_state:
            return []
        return self.confirmation.check(self._mtf_state, self._zones_by_tf)

    def get_status(self):
        """Get current SMC status for display. Call after update()."""
        if not self._mtf_state:
            return {'status': 'no_data', 'message': 'Sin datos'}
        return self.confirmation.get_status(self._mtf_state, self._zones_by_tf)

    def get_mtf_state(self):
        """Get raw MTF state."""
        return self._mtf_state

    def get_zones(self):
        """Get all detected zones."""
        return self._zones_by_tf

    def get_chat_context(self):
        """
        Build text context for the AI chat with full SMC state.
        This is injected into every chat message so Groq/Ollama knows
        the multi-timeframe situation.
        """
        if not self._mtf_state:
            return ""

        status = self.get_status()
        lines = ["\n📊 ANÁLISIS MULTI-TEMPORALIDAD (Smart Money Concepts):"]

        for tf in ['H1', 'M15', 'M5']:
            s = self._mtf_state.get(tf, {})
            trend = s.get('trend', '?')
            arrow = {'bullish': 'ALCISTA ↑', 'bearish': 'BAJISTA ↓', 'neutral': 'LATERAL →'}.get(trend, '?')
            lsh = s.get('last_swing_high')
            lsl = s.get('last_swing_low')
            struct = s.get('structure', [])

            line = f"  - {tf}: Tendencia {arrow}"
            if lsh:
                line += f" | Último Swing High: {lsh:.5f}"
            if lsl:
                line += f" | Último Swing Low: {lsl:.5f}"
            if struct:
                last_structs = ', '.join([f"{p['type']} {p['price']:.5f}" for p in struct[-3:]])
                line += f" | Estructura: [{last_structs}]"

            bos = s.get('bos')
            if bos:
                line += f" | ⚡ {bos['description']}"

            lines.append(line)

        # Zones
        lines.append("  ZONAS ACTIVAS:")
        has_zones = False
        for tf in ['H1', 'M15']:
            for z in self._zones_by_tf.get(tf, []):
                emoji = '🟢' if z['type'] == 'demand' else '🔴'
                lines.append(
                    f"    {emoji} {z['type'].upper()} {tf}: {z['bottom']:.5f} - {z['top']:.5f} "
                    f"(fuerza: {z['strength']}/3, toques: {z['touches']})"
                )
                has_zones = True
        if not has_zones:
            lines.append("    Sin zonas activas cercanas")

        # Confirmation status
        lines.append(f"  ESTADO: {status['message']}")

        # Coaching reminder
        htf_bias = status.get('htf_bias', 'neutral')
        if htf_bias != 'neutral':
            direction = 'ALCISTA' if htf_bias == 'bullish' else 'BAJISTA'
            op = 'CALL' if htf_bias == 'bullish' else 'PUT'
            lines.append(f"  💡 RECORDATORIO: Tendencia HTF es {direction}. Solo operá {op} con confirmación en M5.")
        else:
            lines.append("  💡 RECORDATORIO: Sin tendencia HTF clara. NO OPERAR hasta que se defina.")

        return '\n'.join(lines)

    def _load_rules(self):
        """Load SMC rules from config file."""
        rules_path = os.path.join('config', 'smc_rules.json')
        try:
            if os.path.exists(rules_path):
                with open(rules_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return {
            'htf_timeframes': ['1h', '15m'],
            'ltf_timeframe': '5m',
            'require_ltf_confirmation': True,
            'require_zone_touch': True,
            'max_zone_touches': 3,
            'min_impulse_multiplier': 2.0,
        }
