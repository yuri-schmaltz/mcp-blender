# metrics.py - Instrumentação mínima de métricas para baseline
import logging
import time
from collections import defaultdict

class Metrics:
    """Coleta e expõe métricas simples de uso, erro e latência."""
    def __init__(self):
        self.counters = defaultdict(int)
        self.timings = defaultdict(list)
        self.logger = logging.getLogger("Metrics")

    def inc(self, name):
        self.counters[name] += 1
        self.logger.debug(f"Métrica {name} incrementada: {self.counters[name]}")

    def observe(self, name, value):
        self.timings[name].append(value)
        self.logger.debug(f"Métrica {name} observada: {value}")

    def report(self):
        return {
            "counters": dict(self.counters),
            "timings": {k: (min(v), max(v), sum(v)/len(v) if v else 0) for k, v in self.timings.items()}
        }

metrics = Metrics()
