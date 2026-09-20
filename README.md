# SVAC-Concurrency: A Step-Verification Benchmark for Large Language Model Reasoning on Operating System Concurrency Algorithms

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-green.svg)](https://www.python.org/)

**SVAC-Concurrency** is an open-source evaluation benchmark designed to rigorously assess the procedural fidelity and internal state-tracking capabilities of Large Language Models (LLMs) on canonical Operating System (OS) concurrency and resource allocation algorithms.

Unlike conventional black-box benchmarks that score only the final output verdict, SVAC-Concurrency pairs **125 parameter-controlled problem instances** with deterministic reference solvers to evaluate full execution traces across four diagnostic dimensions:
- **Step Accuracy (SA)**: Proportion of discrete intermediate state transitions matching ground truth.
- **First Error Position (FEP)**: Discrete execution step at which the trace first diverges.
- **Error Cascade Rate (ECR)**: Frequency of persistent errors downstream of the first divergence.
- **Equivalence-Aware Invariant Validity**: Semantic step verification accounting for alternative valid safe paths and non-deterministic graph traversal orders.

---

## Benchmark Suite Overview

| Algorithm Family | State Representation | Instances | Complexity Bounds | Class Balance |
| :--- | :--- | :---: | :--- | :---: |
| **Wait-For Graph (WFG)** | Directed Adjacency & Recursion Stack | 30 | $\|V\| \in [2, 6]$, $\|E\| \in [1, 8]$ | 50% Deadlock (15) / 50% Acyclic (15) |
| **Banker's Algorithm** | Available Vector, Allocation & Need Mtx | 30 | $P \in [2, 6]$, $R \in [2, 4]$ | 50% Safe (15) / 50% Unsafe (15) |
| **Buddy System Allocation** | Free-list Binary Tree & Partition Blocks | 25 | 512 KB – 4096 KB, Ops $\in [4, 10]$ | Adversarial Fragmentation |
| **Counting Semaphore** | Integer Counter & FIFO Blocked Queue | 20 | $S \in [1, 3]$, Ops $\in [4, 10]$ | Interleaved Concurrency |
| **Mutex Lock Simulation** | Owner ID & Lock Contention Queue | 20 | Threads $\in [2, 5]$, Ops $\in [4, 8]$ | Multi-Threaded Contention |
| **Total Benchmark** | | **125** | **5 Calibrated Complexity Tiers** | **50.0% Majority Baseline** |

---

## Key Empirical Discoveries

1. **The "Right Verdict for Wrong Reasons" Gap**: Across balanced 50/50 decision distributions (50% majority baseline), Gemini-3.5-Flash-Lite achieves **72.8% Verdict Accuracy** but only **56.1% Step Accuracy**—collapsing to **36.98% SA** on non-saturating algorithmic tasks (WFG, Banker's, Buddy).
2. **The CoT Inversion Effect**: In topological cycle detection (WFG), Chain-of-Thought verbalization causes catastrophic failure: Few-Shot prompting achieves **85.4% SA**, whereas CoT plunges to **7.5% SA**, caused by narration conflating globally visited nodes with the active DFS recursion stack.
3. **Failure Horizons**: WFG errors occur at Step 1 in 100% of Zero-Shot and CoT failures, whereas Buddy allocation exhibits gradual multi-step arithmetic drift (mean FEP = 6.6–7.6 steps).
4. **Equivalence-Aware Scoring**: Strict positional matching artificially depresses scores; semantic invariant checking increases valid SA to **74.3% in Banker's** ($\Delta = +32.8\%$) and **95.6% in WFG** ($\Delta = +64.3\%$).
5. **Schema Brittleness in Open Weights**: NVIDIA Nemotron-3-Super-120B (hybrid Mamba-MoE) experienced an 80.3% format failure rate under strict JSON schema enforcement, while achieving 95.9% Verdict Accuracy on the parsed subset.

---

## Repository Structure

```
SVAC_Concurrency/
├── README.md                           # Master documentation
├── LICENSE                             # MIT License
├── requirements.txt                    # Python dependencies
├── ieee_paper_draft.md                 # Complete IEEE conference paper manuscript
│
├── data/
│   ├── instances/                      # 125 problem instances (JSON)
│   │   ├── svac_wfg_instances.json
│   │   ├── svac_bankers_instances.json
│   │   ├── svac_buddy_instances.json
│   │   ├── svac_semaphore_instances.json
│   │   └── svac_mutex_instances.json
│   └── prompts/                        # 15 prompt templates (5 tasks x 3 strategies)
│
├── solvers/                            # Deterministic reference solvers
│   ├── svac_deadlock_solvers.py        # WFG DFS & Banker's Safety solvers
│   ├── svac_buddy_solver.py            # Power-of-two Buddy allocator
│   ├── svac_sync_solvers.py            # Semaphore & Mutex discrete simulators
│   └── differential_tests.py           # Differential brute-force cross-validation tests
│
├── evaluation/                         # Step-verification evaluation harnesses
│   ├── svac_deadlock_scorer.py         # Deadlock step & verdict scorer
│   ├── svac_buddy_scorer.py            # Buddy system step scorer
│   ├── svac_sync_scorer.py             # Semaphore & Mutex scorer
│   ├── svac_run_evaluation.py          # Master batch evaluation pipeline
│   ├── validity_checker.py             # Invariant-based equivalence-aware verifier
│   └── alignment_sensitivity.py        # Sequence-alignment (LCS) sensitivity evaluator
│
├── analysis/                           # Analysis & visualization scripts
│   ├── class_balance_analysis.py       # Ground-truth label balance & Wilson CIs
│   ├── reconcile_table2.py             # Table II reconciliation & denominator audit
│   ├── error_taxonomy_report.py        # WFG error type distribution extractor
│   ├── parse_failure_analysis.py       # Complexity-dependent format compliance analysis
│   ├── fep_analysis.py                 # First Error Position statistical analyzer
│   ├── generate_tables_csv.py          # Exports all paper tables as CSVs
│   ├── svac_plot_results.py            # Publication-quality figure generator (300 DPI)
│   └── figures/                        # Generated high-resolution figures (PNG)
│
├── results/
│   ├── scores/                         # JSON score files across all evaluated models
│   ├── reports/                        # Detailed diagnostic JSON / text reports
│   └── csvs/                           # Structured CSV tables matching the manuscript
│
└── svac_llm_responses/                 # Raw model outputs (Gemini, GPT-OSS, Nemotron, LFM)
```

---

## Quickstart & Installation

Clone the repository and install the minimal dependencies:

```bash
git clone https://github.com/Bethegnt/SVAC-Concurrency.git
cd SVAC-Concurrency
pip install -r requirements.txt
```

---

## Reproducing Paper Results & Figures

### 1. Run Solver Differential Validation Tests
Verifies reference solvers against independent brute-force implementations on all 60 deadlock instances:
```bash
python3 solvers/differential_tests.py
```
*(Expected output: 60/60 instances pass with 0 discrepancies).*

### 2. Run Equivalence-Aware Invariant Scoring
Computes semantic invariant validity versus strict positional matching:
```bash
python3 evaluation/validity_checker.py
```

### 3. Run Trace Alignment Sensitivity Analysis
Computes sequence-aligned (LCS) step accuracy to assess step-offset penalties:
```bash
python3 evaluation/alignment_sensitivity.py
```

### 4. Analyze First Error Positions (FEP)
Extracts FEP distributions across tasks and generates Figure 5:
```bash
python3 analysis/fep_analysis.py
```

### 5. Export All Manuscript Tables as CSVs
Generates Tables I through V in `results/csvs/`:
```bash
python3 analysis/generate_tables_csv.py
```

### 6. Regenerate All Publication Figures (300 DPI)
Produces high-resolution figures matching the paper in `analysis/figures/`:
```bash
python3 analysis/svac_plot_results.py \
  --scores results/scores/gemini-3-5-flash-lite_20260819_203106_scores.json \
  --compare results/scores/openai_gpt-oss-20b_20260821_203228_scores.json \
            results/scores/nvidia_nemotron-3-super-120b-a12b_free_20260820_141907_scores.json \
            results/scores/liquid_lfm-2.5-2.6b_free_20260821_203235_scores.json
```

---

## Citation

```bibtex
@inproceedings{svac_concurrency_2026,
  title     = {SVAC-Concurrency: A Step-Verification Benchmark for Large Language Model Reasoning on Operating System Concurrency Algorithms},
  author    = {Anonymous Authors},
  booktitle = {Proceedings of the IEEE International Conference on Computer Communications and Networks (ICCCN)},
  year      = {2026}
}
```

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
