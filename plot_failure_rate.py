"""Plot failure rates from k6 summary JSON.

Usage:
    k6 run mock/parallel-load-test.js --summary-export results.json
    python plot_failure_rate.py --summary results.json --output ./plots
"""

import argparse
import json
import os
import re
from typing import Dict

import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter


def parse_failure_rate_by_vu(metrics: Dict) -> Dict[int, float]:
    pattern = re.compile(r'^failure_rate\{[^}]*bucket:([^,}]+)[^}]*\}$')
    by_vu: Dict[int, float] = {}
    for name, data in metrics.items():
        m = pattern.match(name)
        if not m:
            continue
        bucket_val = m.group(1).strip('"')
        if not bucket_val.isdigit():
            # Skip wildcard or non-numeric bucket entries like "*"
            continue
        vu = int(bucket_val)
        by_vu[vu] = data['values']['rate']
    return dict(sorted(by_vu.items()))


def parse_failure_by_operation(metrics: Dict) -> Dict[str, float]:
    # http_req_failed metric has operation tags we set via 'name'
    pattern = re.compile(r'^http_req_failed\{.*name:([^,}]+).*}$')
    op_rates: Dict[str, float] = {}
    for name, data in metrics.items():
        m = pattern.match(name)
        if not m:
            continue
        op = m.group(1)
        op_rates[op] = data['values']['rate']
    return op_rates


def plot_combined(by_vu: Dict[int, float], by_op: Dict[str, float], out_path: str):
    """Create a single figure visualising both (1) overall failure-rate vs load and
    (2) per-operation failure-rates.

    * x-axis of the first subplot: increasing load buckets (active VUs)
    * y-axis: failure-rate (0-1) formatted as percentage
    """
    # Make sure output directory exists
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    # ----- Sub-plot 1: failure-rate vs load (line) ----- #
    if by_vu:
        x_vals = list(by_vu.keys())
        y_vals = list(by_vu.values())
        ax1.plot(x_vals, y_vals, marker="o", color="#264653")
        ax1.set_title("Failure Rate vs Active VUs (Load)")
        ax1.set_xlabel("VU Bucket (load)")
        ax1.set_ylabel("Failure Rate")
        ax1.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax1.grid(True, axis="y", linestyle="--", alpha=0.4)
    else:
        ax1.text(0.5, 0.5, "No failure_rate metrics found", ha="center", va="center")
        ax1.axis("off")

    # ----- Sub-plot 2: per-operation failure-rates (bar) ----- #
    if by_op:
        ops = list(by_op.keys())
        rates = [by_op[o] for o in ops]
        ax2.bar(ops, rates, color="#e76f51")
        ax2.set_title("Failure Rate per Operation")
        ax2.set_xlabel("Operation")
        ax2.set_ylabel("Failure Rate")
        ax2.yaxis.set_major_formatter(PercentFormatter(1.0))
        ax2.set_xticklabels(ops, rotation=45, ha="right", fontsize=8)
        for idx, rate in enumerate(rates):
            ax2.text(idx, rate + 0.002, f"{rate:.2%}", ha="center", va="bottom", fontsize=7)
    else:
        ax2.text(0.5, 0.5, "No per-operation metrics found", ha="center", va="center")
        ax2.axis("off")

    fig.tight_layout()
    plt.savefig(out_path)
    plt.close()
    print(f"Saved {out_path}")


def main():
    parser = argparse.ArgumentParser(description="Plot failure rates from k6 summary JSON")
    parser.add_argument('--summary', required=True, help='Path to k6 summary-export JSON file')
    parser.add_argument('--output', default='.', help='Directory to save plots')
    args = parser.parse_args()

    with open(args.summary) as f:
        data = json.load(f)

    metrics = data.get('metrics', {})
    by_vu = parse_failure_rate_by_vu(metrics)
    by_op = parse_failure_by_operation(metrics)

    # Generate combined figure
    plot_combined(by_vu, by_op, os.path.join(args.output, 'failure_rate_combined.png'))


if __name__ == '__main__':
    main() 