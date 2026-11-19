"""A process-local, shared administrator sandbox with an isolated exposure ledger."""
import copy
import random
import secrets
import sqlite3
import tempfile
import threading
from collections import Counter, deque
from datetime import date, timedelta
from pathlib import Path

from distribution import recommendations

DAY = 86400
DEFAULTS = dict(start_date='2025-01-01', days=365, seed=42, customers=100,
                daily_requests=24, window_days=3, max_per_symbol=10, max_per_sector=18,
                cooldown_days=7, utility_tolerance=2, speed=7)
LIMITS = dict(days=(1, 730), seed=(0, 2147483647), customers=(1, 100000),
              daily_requests=(1, 100), window_days=(1, 30), max_per_symbol=(1, 10000),
              max_per_sector=(1, 10000), cooldown_days=(1, 365),
              utility_tolerance=(0, 10), speed=(1, 60))
TUNABLE = {'daily_requests', 'window_days', 'max_per_symbol', 'max_per_sector',
           'cooldown_days', 'utility_tolerance', 'speed'}
UNIVERSE = [('SIM_A', 'Technology', 90), ('SIM_B', 'Technology', 89.5),
            ('SIM_C', 'Industry', 89), ('SIM_D', 'Consumer', 88.5),
            ('SIM_E', 'Health', 88), ('SIM_LOW', 'Other', 30)]


class Conflict(ValueError):
    """A command is stale, or incompatible with the current run state."""


def validate(config):
    for key, (lo, hi) in LIMITS.items():
        value = config[key]
        types = (int, float) if key == 'utility_tolerance' else (int,)
        if type(value) not in types or not lo <= value <= hi:
            raise ValueError(f'{key} phải nằm trong khoảng {lo}–{hi}.')
    try:
        start = date.fromisoformat(config['start_date'])
        if not 2000 <= start.year <= 2099:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Chọn ngày bắt đầu từ năm 2000 đến 2099.') from None


class Run:
    def __init__(self, config):
        self.config = config
        self.id = secrets.token_hex(12)
        self.directory = tempfile.TemporaryDirectory(prefix='pasion-admin-lab-')
        self.db = Path(self.directory.name) / 'synthetic.sqlite3'
        self.start = date.fromisoformat(config['start_date'])
        self.status = 'paused'
        self.day = 0
        self.revision = self.policy_version = 1
        self.totals = Counter(requests=0, selected=0, redirected=0, withheld=0)
        self.symbols = dict.fromkeys((symbol for symbol, _, _ in UNIVERSE), 0)
        self.reasons = Counter()
        self.history = []
        self.events = deque(maxlen=20)
        self.changes = [dict(day=1, config=config.copy())]
        self.error = None

    def advance(self):
        config = self.config
        # Independent daily streams make wall-clock speed and pausing irrelevant.
        rng = random.Random(config['seed'] * 1000 + self.day)
        volume = rng.randint(max(1, config['daily_requests'] // 2), config['daily_requests'])
        offsets = sorted(rng.sample(range(DAY), volume))
        day = self.start + timedelta(days=self.day)
        midnight = (day - date(1970, 1, 1)).days * DAY
        policy = dict(version=f'lab-{self.policy_version}', window_seconds=config['window_days'] * DAY,
                      max_per_symbol=config['max_per_symbol'], max_per_sector=config['max_per_sector'],
                      customer_cooldown_seconds=config['cooldown_days'] * DAY,
                      utility_tolerance=config['utility_tolerance'])
        counts = Counter(requests=volume, selected=0, redirected=0, withheld=0)
        symbols, reasons, events = Counter(), Counter(), []
        with recommendations.decision_transaction(self.db) as db:
            for i, offset in enumerate(offsets):
                customer = rng.randrange(1, config['customers'] + 1)
                # Some synthetic profiles exclude a sector, and utility varies by request.
                excluded = ('', '', 'Technology', 'Consumer', 'Health')[customer % 5]
                candidates = [
                    dict(symbol=symbol, sector=sector, utility=base + rng.choice((-0.5, 0, 0.5)),
                         suitable=sector != excluded, data_status='READY', horizon='30 sessions',
                         utility_definition='synthetic score', utility_version='v1')
                    for symbol, sector, base in UNIVERSE
                ]
                first = min((c for c in candidates if c['suitable']),
                            key=lambda c: (-c['utility'], c['symbol']))['symbol']
                result = recommendations.decide_in_transaction(
                    db, f'{self.day}/{i}', f'SIM-{customer}', candidates, policy, midnight + offset)
                symbol = result['symbol']
                if symbol:
                    symbols[symbol] += 1
                    counts['selected'] += 1
                    counts['redirected'] += int(symbol != first)
                else:
                    counts['withheld'] += 1
                reasons.update({reason for blocked in result['blocked'].values() for reason in blocked})
                events.append(dict(date=day.isoformat(), second=offset, customer=f'SIM-{customer}',
                                   preferred=first, symbol=symbol, reasons=result['blocked'].get(first, [])))
        self.day += 1
        self.totals.update(counts)
        for symbol, total in symbols.items():
            self.symbols[symbol] += total
        self.reasons.update(reasons)
        self.events.extend(events)
        self.history.append(dict(day=self.day, date=day.isoformat(), customers=config['customers'],
                                 policy_version=self.policy_version, **counts))
        if self.day == config['days']:
            self.status = 'completed'

    def snapshot(self):
        return copy.deepcopy(dict(id=self.id, revision=self.revision, config=self.config, day=self.day,
                                  status=self.status, totals=dict(self.totals), symbols=self.symbols,
                                  reasons=dict(self.reasons), history=self.history, events=list(reversed(self.events)),
                                  changes=self.changes, error=self.error))


class Lab:
    def __init__(self):
        self.lock = threading.Lock()
        self.run = None
        self.stop = None

    def _snapshot(self):
        return dict(engine=recommendations.VERSION, defaults=DEFAULTS, limits=LIMITS,
                    run=self.run.snapshot() if self.run else None)

    def state(self):
        with self.lock:
            return self._snapshot()

    def _advance(self, run):
        try:
            run.advance()
        except (OSError, sqlite3.Error, ValueError):
            run.status = 'failed'
            run.error = 'Không thể hoàn tất ngày mô phỏng. Có thể xuất các ngày đã hoàn tất.'

    def _work(self, run, stop):
        while not stop.is_set():
            with self.lock:
                if stop.is_set() or self.run is not run or run.status != 'running':
                    return
                self._advance(run)
                delay = 1 / run.config['speed']
                if run.status != 'running':
                    return
            stop.wait(delay)

    def command(self, body):
        if not isinstance(body, dict):
            raise ValueError('Lệnh không hợp lệ.')
        with self.lock:
            run = self.run
            if body.get('run_id') != (run.id if run else None) or body.get('revision') != (run.revision if run else 0):
                raise Conflict('Lượt mô phỏng đã thay đổi. Hãy xem lại các giá trị mới.')
            action = body.get('action')
            values = body.get('values', {})
            if not isinstance(values, dict):
                raise ValueError('Thông số không hợp lệ.')
            if action == 'create':
                if run and run.status == 'running':
                    raise Conflict('Tạm dừng trước khi tạo lượt khác.')
                if values.keys() - DEFAULTS.keys():
                    raise ValueError('Thông số không hợp lệ.')
                config = {**DEFAULTS, **values}
                validate(config)
                replacement = Run(config)
                if run:
                    run.directory.cleanup()
                self.run = replacement
            elif not run or run.status in ('completed', 'failed'):
                raise Conflict('Tạo lượt mô phỏng mới để tiếp tục.')
            elif action == 'update':
                if not values or values.keys() - (TUNABLE | {'add_customers'}):
                    raise ValueError('Thông số điều chỉnh không hợp lệ.')
                additions = values.get('add_customers', 0)
                if type(additions) is not int or additions < 0:
                    raise ValueError('Số khách thêm phải là số nguyên không âm.')
                config = {**run.config, **{k: v for k, v in values.items() if k in TUNABLE},
                          'customers': run.config['customers'] + additions}
                validate(config)
                if config != run.config:
                    run.config = config
                    run.policy_version += 1
                    run.changes.append(dict(day=run.day + 1, config=config.copy()))
                run.revision += 1
            elif action == 'start' and run.status == 'paused':
                self.stop = threading.Event()
                run.status = 'running'
                run.revision += 1
                threading.Thread(target=self._work, args=(run, self.stop), daemon=True).start()
            elif action == 'pause' and run.status == 'running':
                self.stop.set()
                run.status = 'paused'
                run.revision += 1
            elif action == 'step' and run.status == 'paused':
                self._advance(run)
                run.revision += 1
            else:
                raise Conflict('Lệnh không phù hợp với trạng thái hiện tại.')
            return self._snapshot()


lab = Lab()
