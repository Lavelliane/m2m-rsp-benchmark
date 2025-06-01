"""
Plot CPU and memory usage metrics collected by the mock M2M RSP server.

Run this script after your k6 load-test has finished while the mock server is still
running:

    python plot_metrics.py --url http://localhost:8080 --output ./plots

This will fetch the metrics from /metrics endpoint added to the mock server and
save two png files (cpu_percent_by_operation.png and memory_mb_by_operation.png)
into the chosen output directory.
"""

import argparse
import os
from typing import Dict, List, Any

import requests
import pandas as pd
import matplotlib.pyplot as plt


def fetch_metrics(base_url: str) -> Dict[str, List[dict]]:
    """Fetch JSON metrics from the running mock server."""
    resp = requests.get(base_url.rstrip('/') + '/metrics', timeout=10)
    resp.raise_for_status()
    return resp.json()


def plot_metric(metrics: Dict[str, List[dict]], metric_key: str, out_dir: str) -> None:
    """Generate a bar-chart showing **average** resource usage per operation.

    X-axis   → operation / process name
    Y-axis   → average CPU-% or average Memory-MB
    """

    if not metrics:
        print("No metrics returned – did you run any tests?")
        return

    # Aggregate
    operations, values = [], []
    for operation, records in metrics.items():
        if not records:
            continue
        df = pd.DataFrame(records)
        operations.append(operation.replace('_', ' ').title())
        # For memory show peak (max); for CPU show average
        if metric_key == 'memory_mb':
            values.append(df[metric_key].max())
        else:
            values.append(df[metric_key].mean())

    if not operations:
        print("Metrics structure was empty – nothing to plot.")
        return

    plt.figure(figsize=(12, 6))
    y_label = 'Average CPU %' if metric_key == 'cpu_percent' else 'Average Memory (MB)'

    bar_container = plt.bar(operations, values, color='#69b3a2')
    plt.ylabel(y_label)
    plt.title(y_label + ' per Operation')
    plt.xticks(rotation=45, ha='right')

    # Annotate bars with their value
    for rect, val in zip(bar_container, values):
        height = rect.get_height()
        plt.annotate(f'{val:.2f}',
                     xy=(rect.get_x() + rect.get_width() / 2, height),
                     xytext=(0, 3),  # 3 points vertical offset
                     textcoords="offset points",
                     ha='center', va='bottom', fontsize=8)

    plt.tight_layout()

    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f'{metric_key}_bar_by_operation.png')
    plt.savefig(out_path)
    plt.close()
    print(f'Saved {out_path}')


def main():
    parser = argparse.ArgumentParser(description='Plot CPU and memory metrics collected by the mock server.')
    parser.add_argument('--url', default='http://localhost:8080', help='Base URL where the mock server is listening.')
    parser.add_argument('--output', default='.', help='Directory to store generated plots.')
    args = parser.parse_args()

    metrics = fetch_metrics(args.url)

    for key in ('cpu_percent', 'memory_mb'):
        plot_metric(metrics, key, args.output)


if __name__ == '__main__':
    main() 