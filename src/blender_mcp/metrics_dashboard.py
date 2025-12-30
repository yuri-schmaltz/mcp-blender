# metrics_dashboard.py - Exposição de métricas detalhadas para dashboards
from blender_mcp.perf_metrics import perf_metrics
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/metrics')
def metrics():
    return jsonify(perf_metrics.report())

if __name__ == '__main__':
    app.run(port=5001)
