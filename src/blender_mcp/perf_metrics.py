# metrics.py - Métricas detalhadas para performance e integração
import logging
from collections import defaultdict

class PerfMetrics:
    """Coleta métricas detalhadas de latência, uso e erros."""
    def __init__(self):
        self.counters = defaultdict(int)
        self.timings = defaultdict(list)
        self.logger = logging.getLogger("PerfMetrics")

    def inc(self, name):
        self.counters[name] += 1
        self.logger.debug(f"Métrica {name} incrementada: {self.counters[name]}")

    def observe(self, name, value):
        self.timings[name].append(value)
        self.logger.debug(f"Métrica {name} observada: {value}")

    @staticmethod
    def _percentile(values, percentile):
        """Return percentile value using linear interpolation."""
        if not values:
            return 0
        if percentile <= 0:
            return min(values)
        if percentile >= 100:
            return max(values)

        sorted_values = sorted(values)
        position = (len(sorted_values) - 1) * (percentile / 100)
        lower = int(position)
        upper = min(lower + 1, len(sorted_values) - 1)
        weight = position - lower
        return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight

    def report(self):
        return {
            "counters": dict(self.counters),
            "timings": {
                k: {
                    "min": min(v),
                    "max": max(v),
                    "avg": sum(v) / len(v),
                    "p50": self._percentile(v, 50),
                    "p95": self._percentile(v, 95),
                    "count": len(v),
                }
                for k, v in self.timings.items()
                if v
            },
        }

perf_metrics = PerfMetrics()
