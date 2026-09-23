"""Questbond / Mendigo — quantitative system benchmark.

A separate, repeatable evaluation framework. It reads versioned synthetic
fixtures and modular ground truth, runs the product's deterministic APIs, and
writes quantitative result artifacts. Benchmark ground truth is never read by
runtime decision logic.
"""

BENCHMARK_VERSION = "1.0.0"
