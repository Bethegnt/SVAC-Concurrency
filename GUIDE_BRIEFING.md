# GUIDE BRIEFING: SVAC-Concurrency

**Document Purpose:** Guide-facing verification package for the research paper *SVAC-Concurrency: A Step-Verification Benchmark for Large Language Model Reasoning on Operating System Concurrency Algorithms*.  
**Workspace Path:** `/Users/bethegnt/Downloads/SVAC_Concurrency`  
**Primary Manuscript Files:** `latex/main.tex`, `ieee_paper_draft.md`  

---

## 1. One-Paragraph Summary

*Source: `latex/main.tex` (Lines 64–85); `ieee_paper_draft.md` (Lines 22–25)*

While Large Language Models (LLMs) demonstrate remarkable competence in natural language understanding and high-level source code synthesis, their ability to faithfully track deterministic, multi-step algorithmic state transitions remains fundamentally unverified. Concurrency control and resource allocation algorithms in Operating Systems (OS) represent a rigorous, safety-critical testbed for mechanistic reasoning, demanding strict invariant preservation, vector/matrix state updates, and topological cycle detection. In this paper, we present SVAC-Concurrency, an open-source, reproducible evaluation benchmark comprising 125 parameterized problem instances (generating 375 evaluation traces per model across 3 prompting regimes) spanning five canonical OS algorithms: Wait-For Graph (WFG) deadlock detection, Banker's safety algorithm, Buddy System memory allocation, counting Semaphores, and Mutex lock simulations. Rather than relying solely on coarse outcome correctness (Verdict Accuracy), SVAC-Concurrency introduces a deterministic ground-truth verification framework to evaluate execution traces across four diagnostic dimensions: Step Accuracy (SA), First Error Position (FEP), Error Cascade Rate (ECR), and Equivalence-Aware Invariant Validity. We conduct an extensive cross-architectural investigation evaluating Google Gemini-3.5-Flash-Lite, OpenAI GPT-OSS-20B, NVIDIA Nemotron-3-Super-120B, and Liquid AI LFM-2.6B across Zero-Shot, Few-Shot, and Chain-of-Thought (CoT) prompting strategies.

---

## 2. Novelty Statement vs. Closest Prior Work

*Source: `latex/main.tex` (Section I, Lines 188–207; Section II, Lines 236–244); `ieee_paper_draft.md` (Section I, Lines 76–86; Section II, Lines 94–96); `latex/references.bib` (Entries `anon2024svac` [12] and `huang2026concur` [13])*

* **Extension Beyond Sequential OS Policies vs. Kumar et al. [12]:** The precursor technical report by Kumar et al. ([12], *Evaluating LLM Reasoning on Operating System Algorithms via Step-Level Verification*, ICML Workshop on Complex Task Benchmarks, 2026) evaluated step-level reasoning exclusively on sequential virtual memory page replacement policies (FIFO, LRU, Optimal, Clock). SVAC-Concurrency moves beyond single-pointer linear replacement buffers to multi-threaded concurrency, directed graph cycle detection under DFS recursion stacks (Wait-For Graph), multi-dimensional matrix/vector invariant preservation (Banker's safety), and dynamic power-of-two binary tree partitioning (Buddy System).
* **Execution Trace Verification vs. Concurrent Code Synthesis in CONCUR [13]:** The CONCUR benchmark by Huang et al. ([13], *CONCUR: Benchmarking LLMs for Concurrent Code Generation*, arXiv:2603.03683, 2026) evaluated LLMs on *synthesizing* concurrent synchronization primitives. SVAC-Concurrency explicitly contrasts with CONCUR: rather than evaluating concurrent code synthesis, it evaluates *execution-trace verification*, isolating whether auto-regressive models maintain faithful intermediate state transitions and preserve concurrency invariants during discrete execution.
* **Multi-Dimensional Failure Diagnostics ($\SA, \FEP, \ECR$):** Moving beyond coarse binary verdicts and single scalar accuracies, the benchmark formalizes Step Accuracy ($\SA$), First Error Position ($\FEP$), and Error Cascade Rate ($\ECR$). This diagnostic framework proves that on balanced 50/50 decision distributions, a high Verdict Accuracy (72.3% across all responses, 72.8% on parsed responses) masks an underlying state-tracking collapse (36.98% Step Accuracy on non-saturating algorithmic tasks: WFG, Banker's, Buddy).
* **Equivalence-Aware Semantic Invariant Verification:** Standard execution benchmarks rely on rigid exact-position matching that penalizes models when valid alternative paths exist (e.g., candidate process tie-breaking in Banker's or alternative valid neighbor order in DFS). SVAC-Concurrency introduces invariant-based verification, showing that rigid positional matching under-reports valid algorithmic execution by 32.8% in Banker's ($41.5\% \rightarrow 74.3\%$) and 64.3% in WFG ($31.2\% \rightarrow 95.6\%$).

---

## 3. Experimental Validity Summary

### A. Total Instances (125) and Per-Task Breakdown
* **Source Files:**
  * `data/instances/svac_bankers_instances.json`
  * `data/instances/svac_buddy_instances.json`
  * `data/instances/svac_mutex_instances.json`
  * `data/instances/svac_semaphore_instances.json`
  * `data/instances/svac_wfg_instances.json`
* **Command to run live:**
  ```bash
  python3 -c "import json, glob; [print(f'{f}: {len(json.load(open(f)))} instances') for f in sorted(glob.glob('data/instances/*.json'))]; print('Total:', sum(len(json.load(open(f))) for f in glob.glob('data/instances/*.json')))"
  ```
* **Raw Command Output:**
  ```
  data/instances/svac_bankers_instances.json: 30 instances
  data/instances/svac_buddy_instances.json: 25 instances
  data/instances/svac_mutex_instances.json: 20 instances
  data/instances/svac_semaphore_instances.json: 20 instances
  data/instances/svac_wfg_instances.json: 30 instances
  Total: 125
  ```

### B. Gemini-3.5-Flash-Lite 375/375 Completion
* **Source Directory:** `svac_llm_responses/gemini-3-5-flash-lite/`
* **Breakdown:** 125 instances $\times$ 3 prompt variants (zero_shot, few_shot, cot) = 375 response JSON files.
* **Command to run live:**
  ```bash
  find svac_llm_responses/gemini-3-5-flash-lite -type f -name "*.json" | wc -l
  ```
* **Raw Command Output:**
  ```
       375
  ```

### C. Core Metrics for Gemini-3.5-Flash-Lite
* **Source Report:** `results/reports/gemini-3-5-flash-lite_20261004_225956_report.txt` (and matching latest report generated by evaluation pipeline)
* **Command to run live:**
  ```bash
  python3 evaluation/svac_run_evaluation.py --model gemini-3-5-flash-lite
  ```
* **Extracted Metric Values:**
  * Total Scored Responses ($N$): **375**
  * Parse Success: **99.2%** (372 / 375 parsed)
  * Mean Step Accuracy ($\SA$): **56.1%** (Suite mean across all 5 tasks)
  * Non-Saturating Tasks Mean $\SA$ (WFG, Banker's, Buddy): **36.98%** (Source: `latex/main.tex` Line 91, Line 494)
  * Mean Error Cascade Rate ($\ECR$): **36.9%**
  * Verdict Accuracy (parsed responses): **72.8%**
  * Verdict Accuracy (all 375 responses): **72.3%**
  * Per-Task Mean $\FEP$: Banker's = **1.4**, Buddy = **7.0**, Mutex = **-** (no errors, 100% SA), Semaphore = **3.8**, WFG = **2.3**

### D. The CoT Inversion Finding (85.4% Few-Shot $\rightarrow$ 7.5% CoT)
* **Exact Source File and Line References:**
  * `latex/main.tex`: Lines 94–95, Line 485 (`Table II`), Lines 517–518, Line 536 (`Table III`)
  * `ieee_paper_draft.md`: Line 28, Line 84, Line 211 (`Table II`), Line 233, Line 263 (`Table III`)
  * `results/csvs/table2_task_by_prompt_strategy.csv`: Line 2 (`WFG Deadlock Detection,4.4%,85.4%,7.5%,31.2%`)
  * `results/reports/gemini-3-5-flash-lite_20261004_225956_report.txt`: Lines 34–36
* **Command to run live:**
  ```bash
  python3 evaluation/svac_run_evaluation.py --model gemini-3-5-flash-lite | grep -E "wfg \| (few_shot|cot|zero_shot)"
  ```
* **Raw Command Output:**
  ```
  wfg | cot | 30 | 100.0% | 7.5% | 0.0% | 33.3% | 1.0 | 91.4% | 93.3%
  wfg | few_shot | 30 | 93.3% | 85.4% | 31.2% | 100.0% | 8.4 | 32.1% | 93.3%
  wfg | zero_shot | 30 | 100.0% | 4.3% | 0.0% | 33.3% | 1.0 | 95.0% | 90.0%
  ```

### E. Step-9 / Step-21 Case Study
* **Source Paper Text:** `latex/main.tex` (Lines 569–576); `ieee_paper_draft.md` (Lines 273–275)
* **Exact Raw JSON File Path:** `svac_llm_responses/gemini-3-5-flash-lite/wfg__cot__wfg_3ceec919261d.json`
* **Instance ID:** `wfg_3ceec919261d` (Ground truth: `deadlock: false`)
* **Command to inspect live:**
  ```bash
  python3 -c "import json; d=json.load(open('svac_llm_responses/gemini-3-5-flash-lite/wfg__cot__wfg_3ceec919261d.json')); resp=json.loads(d['response_text']); s9=[s for s in resp['steps'] if s['step']==9][0]; s21=[s for s in resp['steps'] if s['step']==21][0]; print('Step 9:', s9['node'], s9['action'], s9['recursion_stack']); print('Step 21:', s21['node'], s21['action'], s21['recursion_stack']); print('Final Verdict emitted:', resp['deadlock'])"
  ```
* **Raw Command Output:**
  ```
  Step 9: P4 backtrack ['P0']
  Step 21: P4 cycle_detected ['P0', 'P2', 'P4']
  Final Verdict emitted: True
  ```

---

## 4. Honest Limitations

*Verbatim copy from `latex/main.tex` Section VII (Lines 687–705) and `ieee_paper_draft.md` Section VII (Lines 331–336):*

1. **Single-Run Deterministic Sampling:** Inferences were performed at $\text{temperature} = 0.0$. We did not evaluate temperature-swept self-consistency or majority voting across multiple runs.
2. **Per-Cell Sample Size:** With 125 instances spanning 5 tasks and 5 complexity levels, individual task-complexity sub-cells contain $N = 4\text{--}6$ instances, though each prompt strategy evaluates $N = 20\text{--}30$ instances per algorithm family.
3. **Partial Evaluation of Open Models:** Upstream API rate-limiting on open-router endpoints restricted open-weight evaluations (GPT-OSS-20B and LFM-2.6B) to WFG subsets, necessitating conditional reporting over parsed subsets.
4. **Synthetic Problem Horizons:** Instances model canonical textbook concurrency algorithms ($P \le 6, R \le 4$) rather than production-scale distributed systems traces.
5. **Static Prompting Regimes:** We evaluated static ZS, FS, and CoT prompts without dynamic tool feedback, external Python interpreter execution, or self-correction loops.
6. **Tie-Breaking Sensitivity:** While invariant-aware scoring resolves alternative valid sequences, strict positional SA remains sensitive to canonical solver ordering.

---

## 5. Full Verified Reference List

*Source: `latex/references.bib` (all 24 entries in order of appearance)*

1. T. B. Brown et al., "Language Models are Few-Shot Learners," in *Advances in Neural Information Processing Systems (NeurIPS)*, vol. 33, pp. 1877–1901, 2020. [https://proceedings.neurips.cc/paper/2020/hash/1457c0d6bfcb4967418bfb8ac142f64a-Abstract.html](https://proceedings.neurips.cc/paper/2020/hash/1457c0d6bfcb4967418bfb8ac142f64a-Abstract.html)
2. S. Bubeck et al., "Sparks of Artificial General Intelligence: Early experiments with GPT-4," *arXiv preprint arXiv:2303.12712*, 2023. [https://arxiv.org/abs/2303.12712](https://arxiv.org/abs/2303.12712)
3. M. Chen et al., "Evaluating Large Language Models Trained on Code," *arXiv preprint arXiv:2107.03374*, 2021. [https://arxiv.org/abs/2107.03374](https://arxiv.org/abs/2107.03374)
4. J. Austin et al., "Program Synthesis with Large Language Models," *arXiv preprint arXiv:2108.07732*, 2021. [https://arxiv.org/abs/2108.07732](https://arxiv.org/abs/2108.07732)
5. D. Hendrycks et al., "Measuring Coding Challenge Competence with APPS," in *Advances in Neural Information Processing Systems (NeurIPS)*, 2021. [https://arxiv.org/abs/2105.09938](https://arxiv.org/abs/2105.09938)
6. K. Cobbe et al., "Training Verifiers to Solve Math Word Problems," *arXiv preprint arXiv:2110.14168*, 2021. [https://arxiv.org/abs/2110.14168](https://arxiv.org/abs/2110.14168)
7. D. Hendrycks et al., "Measuring Mathematical Problem Solving with the MATH Dataset," in *Advances in Neural Information Processing Systems (NeurIPS)*, 2021. [https://arxiv.org/abs/2103.03874](https://arxiv.org/abs/2103.03874)
8. H. Lightman et al., "Let's Verify Step by Step," in *Proceedings of the International Conference on Learning Representations (ICLR)*, 2024. [https://arxiv.org/abs/2305.20050](https://arxiv.org/abs/2305.20050)
9. L. Strobl, W. Merrill, G. Weiss, D. Chiang, and D. Angluin, "What Formal Languages Can Transformers Express? A Survey," *Transactions of the Association for Computational Linguistics (TACL)*, vol. 12, pp. 543–561, 2024. [https://doi.org/10.1162/tacl_a_00663](https://doi.org/10.1162/tacl_a_00663)
10. S. Toshniwal et al., "Chess as a Testbed for Language Model State Tracking," in *Proceedings of the AAAI Conference on Artificial Intelligence*, vol. 36, no. 10, pp. 11385–11393, 2022. [https://doi.org/10.1609/aaai.v36i10.21391](https://doi.org/10.1609/aaai.v36i10.21391)
11. H. Wang et al., "Can Language Models Solve Graph Problems in Natural Language?," in *Advances in Neural Information Processing Systems (NeurIPS)*, 2023. [https://arxiv.org/abs/2305.10037](https://arxiv.org/abs/2305.10037)
12. J. M. Kumar, J. S. Chakri, Y. Kothari, M. Mandal, Y. Sinha, and D. Kumar, "Evaluating LLM Reasoning on Operating System Algorithms via Step-Level Verification," in *ICML Workshop on Complex Task Benchmarks (CTB)*, 2026.
13. J. Huang, T. Mahmud, C. Pasareanu, and G. Yang, "CONCUR: Benchmarking LLMs for Concurrent Code Generation," *arXiv preprint arXiv:2603.03683*, 2026. [https://arxiv.org/abs/2603.03683](https://arxiv.org/abs/2603.03683)
14. J. Wei et al., "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models," in *Advances in Neural Information Processing Systems (NeurIPS)*, 2022. [https://arxiv.org/abs/2201.11903](https://arxiv.org/abs/2201.11903)
15. F. Shi et al., "Large Language Models Can Be Easily Distracted by Irrelevant Context," in *Proceedings of the International Conference on Machine Learning (ICML)*, 2023. [https://arxiv.org/abs/2302.00093](https://arxiv.org/abs/2302.00093)
16. Z. Chu et al., "A Survey of Chain of Thought Reasoning: Advances, Frontiers and Challenges," *IEEE Transactions on Knowledge and Data Engineering*, 2024. [https://doi.org/10.1109/TKDE.2024.3418520](https://doi.org/10.1109/TKDE.2024.3418520)
17. P. Agrawal, S. Vasania, and C. Tan, "Exploring the Limitations of Graph Reasoning in Large Language Models," *arXiv preprint arXiv:2402.01805*, Feb. 2024. [https://arxiv.org/abs/2402.01805](https://arxiv.org/abs/2402.01805)
18. A. Silberschatz, P. B. Galvin, and G. Gagne, *Operating System Concepts*, 10th ed. Hoboken, NJ, USA: Wiley, 2018.
19. A. Gu, B. Rozière, H. Leather, A. Solar-Lezama, G. Synnaeve, and S. I. Wang, "CRUXEval: A Benchmark for Code Reasoning, Understanding and Execution," in *Proceedings of the International Conference on Machine Learning (ICML)*, 2024. [https://arxiv.org/abs/2401.03065](https://arxiv.org/abs/2401.03065)
20. J. Chen, Z. Pan, X. Hu, Z. Li, G. Li, and X. Xia, "Reasoning Runtime Behavior of a Program with LLM: How Far Are We?," in *Proceedings of the 47th IEEE/ACM International Conference on Software Engineering (ICSE)*, 2025. [https://arxiv.org/abs/2403.16437](https://arxiv.org/abs/2403.16437)
21. C. Liu, S. D. Zhang, A. R. Ibrahimzada, and R. Jabbarvand, "CodeMind: A Framework to Challenge Large Language Models for Code Reasoning," in *Proceedings of the 62nd Annual Meeting of the Association for Computational Linguistics (ACL)*, 2024. [https://arxiv.org/abs/2402.09664](https://arxiv.org/abs/2402.09664)
22. T. Lanham et al., "Measuring Faithfulness in Chain-of-Thought Reasoning," *arXiv preprint arXiv:2307.13702*, 2023. [https://arxiv.org/abs/2307.13702](https://arxiv.org/abs/2307.13702)
23. M. Turpin et al., "Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting," in *Advances in Neural Information Processing Systems (NeurIPS)*, 2023. [https://arxiv.org/abs/2305.04388](https://arxiv.org/abs/2305.04388)
24. R. Liu, J. Geng, A. J. Wu, I. Sucholutsky, T. Lombrozo, and T. L. Griffiths, "Mind Your Step (by Step): Chain-of-Thought Can Reduce Performance on Tasks Where Thinking Makes Humans Worse," *arXiv preprint arXiv:2410.21333*, 2024. (Accepted at ICML 2025). [https://arxiv.org/abs/2410.21333](https://arxiv.org/abs/2410.21333)

---

## 6. Final Sanity Checks (Raw Unedited Outputs)

### Command A:
`python3 evaluation/svac_run_evaluation.py --model gemini-3-5-flash-lite`

```
Scoring responses for model: gemini-3-5-flash-lite
Scored 375 responses.

Per-instance scores written to: /Users/bethegnt/Downloads/SVAC_Concurrency/results/scores/gemini-3-5-flash-lite_20261004_231119_scores.json
Report written to: /Users/bethegnt/Downloads/SVAC_Concurrency/results/reports/gemini-3-5-flash-lite_20261004_231119_report.txt

==============================================================================
SVAC_Concurrency Evaluation Report
Model: gemini-3-5-flash-lite
Generated: 2026-10-04T23:11:19
Total scored responses: 375
==============================================================================

### AGGREGATE BY TASK ###

task | N | ParseOK | MeanSA | MinSA | MaxSA | MeanFEP | MeanECR | VerdictAcc
----------------------------------------------------------------------------
bankers | 90 | 100.0% | 41.5% | 0.0% | 100.0% | 1.4 | 23.1% | 58.9%
buddy | 75 | 98.7% | 36.9% | 0.0% | 100.0% | 7.0 | 61.4% | 28.0%
mutex | 60 | 100.0% | 100.0% | 100.0% | 100.0% | - | 0.0% | 100.0%
semaphore | 60 | 100.0% | 94.2% | 0.0% | 100.0% | 3.8 | 10.0% | 90.0%
wfg | 90 | 97.8% | 31.2% | 0.0% | 100.0% | 2.3 | 73.8% | 92.2%


### AGGREGATE BY TASK x PROMPT VARIANT ###

task | variant | N | ParseOK | MeanSA | MinSA | MaxSA | MeanFEP | MeanECR | VerdictAcc
--------------------------------------------------------------------------------------
bankers | cot | 30 | 100.0% | 49.7% | 0.0% | 100.0% | 1.4 | 20.8% | 66.7%
bankers | few_shot | 30 | 100.0% | 41.9% | 0.0% | 100.0% | 1.6 | 25.6% | 60.0%
bankers | zero_shot | 30 | 100.0% | 32.9% | 0.0% | 100.0% | 1.3 | 23.0% | 50.0%
buddy | cot | 25 | 96.0% | 49.1% | 0.0% | 100.0% | 6.5 | 41.4% | 36.0%
buddy | few_shot | 25 | 100.0% | 31.5% | 0.0% | 100.0% | 7.6 | 72.0% | 24.0%
buddy | zero_shot | 25 | 100.0% | 30.5% | 0.0% | 100.0% | 7.0 | 69.8% | 24.0%
mutex | cot | 20 | 100.0% | 100.0% | 100.0% | 100.0% | - | 0.0% | 100.0%
mutex | few_shot | 20 | 100.0% | 100.0% | 100.0% | 100.0% | - | 0.0% | 100.0%
mutex | zero_shot | 20 | 100.0% | 100.0% | 100.0% | 100.0% | - | 0.0% | 100.0%
semaphore | cot | 20 | 100.0% | 95.0% | 50.0% | 100.0% | 3.0 | 10.0% | 90.0%
semaphore | few_shot | 20 | 100.0% | 96.2% | 75.0% | 100.0% | 4.3 | 5.0% | 95.0%
semaphore | zero_shot | 20 | 100.0% | 91.2% | 0.0% | 100.0% | 3.7 | 15.0% | 85.0%
wfg | cot | 30 | 100.0% | 7.5% | 0.0% | 33.3% | 1.0 | 91.4% | 93.3%
wfg | few_shot | 30 | 93.3% | 85.4% | 31.2% | 100.0% | 8.4 | 32.1% | 93.3%
wfg | zero_shot | 30 | 100.0% | 4.3% | 0.0% | 33.3% | 1.0 | 95.0% | 90.0%


### AGGREGATE BY COMPLEXITY LEVEL ###

complexity_level | N | ParseOK | MeanSA | MinSA | MaxSA | MeanFEP | MeanECR | VerdictAcc
----------------------------------------------------------------------------------------
1 | 75 | 100.0% | 67.3% | 0.0% | 100.0% | 2.7 | 26.5% | 84.0%
2 | 75 | 100.0% | 59.4% | 0.0% | 100.0% | 3.3 | 33.9% | 77.3%
3 | 75 | 100.0% | 47.1% | 0.0% | 100.0% | 3.7 | 46.7% | 66.7%
4 | 75 | 100.0% | 50.7% | 0.0% | 100.0% | 3.8 | 42.4% | 66.7%
5 | 75 | 96.0% | 55.8% | 0.0% | 100.0% | 4.4 | 34.9% | 66.7%


### AGGREGATE BY TASK x COMPLEXITY LEVEL ###

task | complexity_level | N | ParseOK | MeanSA | MinSA | MaxSA | MeanFEP | MeanECR | VerdictAcc
-----------------------------------------------------------------------------------------------
bankers | 1 | 18 | 100.0% | 77.8% | 0.0% | 100.0% | 1.4 | 5.6% | 77.8%
bankers | 2 | 18 | 100.0% | 44.5% | 0.0% | 100.0% | 1.6 | 22.2% | 55.6%
bankers | 3 | 18 | 100.0% | 11.1% | 0.0% | 100.0% | 1.1 | 39.4% | 44.4%
bankers | 4 | 18 | 100.0% | 32.4% | 0.0% | 100.0% | 1.5 | 28.6% | 55.6%
bankers | 5 | 18 | 100.0% | 41.7% | 0.0% | 100.0% | 1.5 | 19.9% | 61.1%
buddy | 1 | 15 | 100.0% | 44.3% | 0.0% | 100.0% | 4.5 | 48.6% | 53.3%
buddy | 2 | 15 | 100.0% | 50.5% | 0.0% | 100.0% | 6.8 | 47.3% | 46.7%
buddy | 3 | 15 | 100.0% | 34.2% | 0.0% | 79.0% | 7.3 | 69.2% | 20.0%
buddy | 4 | 15 | 100.0% | 22.4% | 0.0% | 69.7% | 6.7 | 75.4% | 6.7%
buddy | 5 | 15 | 93.3% | 32.5% | 0.0% | 78.6% | 9.4 | 66.6% | 13.3%
mutex | 1 | 12 | 100.0% | 100.0% | 100.0% | 100.0% | - | 0.0% | 100.0%
mutex | 2 | 12 | 100.0% | 100.0% | 100.0% | 100.0% | - | 0.0% | 100.0%
mutex | 3 | 12 | 100.0% | 100.0% | 100.0% | 100.0% | - | 0.0% | 100.0%
mutex | 4 | 12 | 100.0% | 100.0% | 100.0% | 100.0% | - | 0.0% | 100.0%
mutex | 5 | 12 | 100.0% | 100.0% | 100.0% | 100.0% | - | 0.0% | 100.0%
semaphore | 1 | 12 | 100.0% | 91.7% | 0.0% | 100.0% | 1.0 | 8.3% | 91.7%
semaphore | 2 | 12 | 100.0% | 93.8% | 50.0% | 100.0% | 3.0 | 8.3% | 91.7%
semaphore | 3 | 12 | 100.0% | 89.6% | 50.0% | 100.0% | 5.0 | 25.0% | 75.0%
semaphore | 4 | 12 | 100.0% | 95.8% | 50.0% | 100.0% | 3.0 | 8.3% | 91.7%
semaphore | 5 | 12 | 100.0% | 100.0% | 100.0% | 100.0% | - | 0.0% | 100.0%
wfg | 1 | 18 | 100.0% | 38.0% | 0.0% | 100.0% | 1.7 | 58.9% | 100.0%
wfg | 2 | 18 | 100.0% | 31.9% | 0.0% | 100.0% | 2.1 | 73.8% | 100.0%
wfg | 3 | 18 | 100.0% | 30.1% | 0.0% | 100.0% | 2.6 | 80.8% | 100.0%
wfg | 4 | 18 | 100.0% | 29.7% | 0.0% | 100.0% | 3.2 | 79.4% | 88.9%
wfg | 5 | 18 | 88.9% | 25.8% | 0.0% | 100.0% | 1.8 | 76.2% | 72.2%


### OVERALL SUMMARY ###

N=375  ParseSuccess=99.2%  MeanSA=56.1%  MeanECR=36.9%  VerdictAccuracy=72.3%
```

### Command B:
`cd latex && pdflatex main.tex && pdflatex main.tex && grep -i "undefined\|error" main.log`

```
zsh:1: command not found: pdflatex
```
*(Note: Local terminal environment does not have TeXLive / pdflatex binary in system PATH. Online compiler such as Overleaf or local MacTeX installation is required to execute pdflatex on `latex/main.tex`)*

### Command C:
`git -C . ls-files | wc -l`

```
    2298
```

### Command D:
`git log --oneline -n 5`

```
2e871d7 (HEAD -> main, origin/main) changes in md files
fc2a3fd first commit
```

---

## 7. Turnitin Readiness Note

The experimental data in this repository is self-generated, comprising synthetic parameter-controlled problem instances paired with deterministic ground-truth execution traces computed by reference Python solvers (`solvers/`), rather than copied or collected from external published datasets. The raw LLM responses were gathered via authenticated API calls to Google AI Studio, Groq, and OpenRouter; provider timestamps, completion metadata, and token consumption logs stored across `svac_llm_responses/` and `results/logs/` establish empirical provenance. The manuscript text (`latex/main.tex` and `ieee_paper_draft.md`) was authored originally for this project. No specific plagiarism percentage is claimed, as that metric can only be definitively established through an official Turnitin scan against indexed academic repositories.

---

## 8. Data Reconciliation & Audit Disclosures

### A. Clarification on References [9], [10], and [17]
The references in Section 5 match the git repository's initial commit (`fc2a3fd`, committed 2026-09-20). The rationale and transition from earlier scratch drafts are documented here with full transparency:
* **Reference [9]:** 
  * *Earlier draft:* Valvoda et al., "What Can Transformers Learn In-Context?", ACL 2024.
  * *Committed in `references.bib`:* Strobl, Merrill, Weiss, Chiang, Angluin, "What Formal Languages Can Transformers Express? A Survey," TACL 2024.
  * *Reason:* Corrected from Valvoda et al. to Strobl et al. because Strobl et al. (TACL 2024) specifically surveys formal languages, state-machine expressivity, and automaton simulation in Transformers, directly supporting the mechanistic state-tracking claims in Section II-B.
* **Reference [10]:** 
  * *Earlier draft:* Toshniwal et al., "Chess as a Testbed for Language Model State Tracking," arXiv:2402.04494, 2024.
  * *Committed in `references.bib`:* Toshniwal et al., "Chess as a Testbed for Language Model State Tracking," AAAI 2022 (Vol. 36, No. 10, pp. 11385–11393).
  * *Reason:* Corrected from the arXiv preprint to the official peer-reviewed AAAI 2022 proceedings archival version with formal DOI (`10.1609/aaai.v36i10.21391`).
* **Reference [17]:**
  * *Earlier draft:* Agrawal et al., "Can LLMs Perform Structured Graph Reasoning Tasks?".
  * *Committed in `references.bib`:* Agrawal, Vasania, Tan, "Exploring the Limitations of Graph Reasoning in Large Language Models," arXiv:2402.01805, 2024.
  * *Reason:* Corrected title to match the exact published title of arXiv:2402.01805 as indexed in arXiv and Google Scholar.

### B. Verdict Accuracy (VA) Standardization: 72.3% vs. 72.8%
* **Headline Metric ($VA_{\text{all}} = 72.3\%$):** Computed over all $N=375$ evaluated attempts ($\frac{271}{375} = 72.266\% \approx 72.3\%$), treating unparsed JSON responses as incorrect verdicts.
* **Conditional Metric ($VA_{\text{parsed}} = 72.8\%$):** Computed conditionally over the 372 successfully parsed responses ($\frac{271}{372} = 72.849\% \approx 72.8\%$).
* **Standardization:** In the manuscript and briefing, $VA_{\text{all}} = 72.3\%$ represents the primary whole-suite outcome benchmark, while $VA_{\text{parsed}} = 72.8\%$ reflects the performance strictly on syntactically compliant outputs.

### C. Nemotron-3-Super-120B N-Count Resolution: 74 vs. 113
* **Empirical Counts on Disk:**
  * Total prompts dispatched to OpenRouter endpoint: **375** (spanning all 5 tasks).
  * Total non-empty HTTP response payloads received: **113** (the remaining 262 requests encountered upstream HTTP 429 rate-limiting or empty payloads).
  * Total successfully parsed JSON schemas: **74** (out of 113 received).
  * Total correct verdicts among parsed: **71** (out of 74).
* **Mathematical Reconciliation:**
  * Parse Rate over total suite attempts: $\frac{74}{375} = \mathbf{19.73\%} \approx \mathbf{19.7\%}$.
  * Parse Rate over received responses: $\frac{74}{113} = \mathbf{65.48\%} \approx \mathbf{65.5\%}$.
  * $VA_{\text{parsed}}$: $\frac{71}{74} = \mathbf{95.94\%} \approx \mathbf{95.9\%}$.
  * $VA_{\text{all}}$: $\frac{71}{375} = \mathbf{18.93\%} \approx \mathbf{18.9\%}$.
* **Audit Finding:** The historical notation "113/375 | 19.7%" mixed the numerator of received responses (113) with the parse rate computed over all attempts ($74/375 = 19.7\%$). The verified ground truth is **74 parsed instances** out of **375 attempted** instances.

### D. Scoping of the "WFG Subsets" Limitation
* Upstream rate limits on OpenRouter/Groq restricted **GPT-OSS-20B** ($N=81$, `tasks: {'wfg'}`) and **Liquid LFM-2.6B** ($N=39$, `tasks: {'wfg'}`) to the Wait-For Graph task only.
* **Nemotron-3-Super-120B was NOT restricted to WFG:** It attempted the complete 375-instance benchmark across all 5 tasks (`{'bankers', 'buddy', 'mutex', 'semaphore', 'wfg'}`), achieving $N=74$ parsed instances suite-wide.

### E. Arithmetic Reconciliation of Non-Saturating SA: 36.98% vs. 36.5%
* **Source of 36.98% (Macro-Strategy Average across Table II columns):**
  * Table II computes the non-saturating mean for each prompt strategy across WFG, Banker's, and Buddy:
    * Zero-Shot non-saturating mean: $\frac{4.4\% + 32.9\% + 30.5\%}{3} = \mathbf{22.60\%}$
    * Few-Shot non-saturating mean: $\frac{85.4\% + 41.9\% + 31.5\%}{3} = \mathbf{52.93\%}$
    * CoT non-saturating mean: $\frac{7.5\% + 49.7\% + 49.1\%}{3} = \mathbf{35.43\%}$
  * Macro-averaging across the three prompting strategies: $\frac{22.60\% + 52.93\% + 35.43\%}{3} = \mathbf{36.988\%} \approx \mathbf{36.98\%}$. This is the exact number reported in Table II footnote $\ddagger$ (`main.tex` Line 494).
* **Source of 36.5% (Macro-Task and Instance-Weighted Averages from Table I):**
  * Unweighted average across the 3 tasks directly from Command A: $\frac{31.2\% (\text{WFG}) + 41.5\% (\text{Bankers}) + 36.9\% (\text{Buddy})}{3} = \mathbf{36.53\%}$.
  * Instance-weighted average across all $N=255$ non-saturating attempts: $\frac{90 \times 31.21\% + 90 \times 41.48\% + 75 \times 36.90\%}{255} = \mathbf{36.51\%}$ (or $36.11\%$ if unparsed instances are assigned 0.0% SA).
* **Takeaway:** Both calculations are mathematically correct: $36.98\%$ is the unweighted macro-average across the 3 prompt regimes in Table II, while $36.5\%$ is the task-level aggregate. Both rigorously demonstrate that non-saturating procedural accuracy is collapsed well below the 72.3% verdict accuracy.


