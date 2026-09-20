# SVAC-Concurrency: A Step-Verification Benchmark for Large Language Model Reasoning on Operating System Concurrency Algorithms

> **IEEE Conference Research Paper Draft**  
> Formatted according to standard IEEE two-column conference template specifications (`IEEEtran.cls`).

---

## TITLE
**SVAC-Concurrency: A Step-Verification Benchmark for Large Language Model Reasoning on Operating System Concurrency Algorithms**

---

## AUTHORS
**[Author Name]¹**, **[Advisor / Co-Author Name]¹**  
¹Department of Computer Science and Engineering, [Institution / University Name], [City, State, Country]  
*Email: {author.name, advisor.name}@university.edu*

---

## ABSTRACT

While Large Language Models (LLMs) demonstrate remarkable competence in natural language understanding and high-level source code synthesis, their ability to faithfully track deterministic, multi-step algorithmic state transitions remains fundamentally unverified. Concurrency control and resource allocation algorithms in Operating Systems (OS) represent a rigorous, safety-critical testbed for mechanistic reasoning, demanding strict invariant preservation, vector/matrix state updates, and topological cycle detection. In this paper, we present **SVAC-Concurrency**, an open-source, reproducible evaluation benchmark comprising **125 parameterized problem instances** (generating 375 evaluation traces per model across 3 prompting regimes) spanning five canonical OS algorithms: Wait-For Graph (WFG) deadlock detection, Banker’s safety algorithm, Buddy System memory allocation, counting Semaphores, and Mutex lock simulations.

Rather than relying solely on coarse outcome correctness (Verdict Accuracy), SVAC-Concurrency introduces a deterministic ground-truth verification framework to evaluate execution traces across four diagnostic dimensions: **Step Accuracy (SA)**, **First Error Position (FEP)**, **Error Cascade Rate (ECR)**, and **Equivalence-Aware Invariant Validity**. We conduct an extensive cross-architectural investigation evaluating **Google Gemini-3.5-Flash-Lite**, **OpenAI GPT-OSS-20B**, **NVIDIA Nemotron-3-Super-120B**, and **Liquid AI LFM-2.6B** across Zero-Shot, Few-Shot, and Chain-of-Thought (CoT) prompting strategies.

Our empirical findings reveal:
1. **Procedural Fidelity vs. Outcome Illusion:** Across balanced 50/50 decision distributions (majority baseline = 50.0%), Gemini-3.5-Flash-Lite achieves 72.8% Verdict Accuracy on parsed responses but only 56.1% Step Accuracy—collapsing to **36.98% SA** on non-saturating state-tracking tasks (WFG, Banker's, Buddy)—demonstrating widespread "right verdict for flawed reasons" behavior.
2. **Prompt-Priming vs. Invariant Divergence in Graph Reasoning:** Under strict positional matching, WFG cycle detection exhibits an apparent collapse from 85.4% SA in Few-Shot to 7.5% in CoT (and 4.4% in Zero-Shot). Crucially, equivalence-aware invariant verification reveals that CoT maintains **93.2% valid step accuracy** and **93.3% verdict accuracy** (comparable to Few-Shot's 100.0% valid SA and 100.0% VA). The collapse in strict positional SA is driven by prompt-primed canonical tie-breaking (in-context DFS exemplars serializing neighbor traversal order) rather than algorithmic incapacity, demonstrating that rigid sequential benchmarks risk measuring format compliance rather than reasoning.
3. **Failure Horizon Dichotomy:** Analysis of First Error Positions demonstrates that WFG errors under strict matching occur at Step 1 in 100% of Zero-Shot and CoT failure cases due to branch tie-breaking divergence, whereas Buddy allocation exhibits true intermediate state corruption (mean $\text{FEP} = 6.6\text{--}7.6$ steps).
4. **Equivalence vs. Strict Positional Bias:** Invariant-based scoring reveals that strict positional matching severely underestimates model competence: when alternative valid execution paths are honored, valid step accuracy increases to 74.3% in Banker's ($\Delta = +32.8\%$) and 95.6% in WFG ($\Delta = +64.3\%$).
5. **Format Brittleness in Open Architectures:** Severe schema compliance degradation in open-weight models (19.7% parse success for Nemotron-120B) demonstrates that raw parameter scale does not guarantee structured state-machine adherence.

The complete benchmark suite, deterministic reference solvers, prompt templates, and evaluation pipelines are publicly available at: `https://github.com/Bethegnt/SVAC-Concurrency`.

**Index Terms** — Large Language Models, Algorithmic Reasoning, Operating Systems, Concurrency Control, Deadlock Detection, Banker's Algorithm, Step-level Verification, Benchmark.

---

## I. INTRODUCTION

Large Language Models (LLMs) are increasingly integrated into modern software engineering pipelines, automated code review tools, and operating systems pedagogy [1], [2]. Despite remarkable empirical gains on functional coding benchmarks such as HumanEval [3], MBPP [4], and APPS [5], conventional benchmarks evaluate programs almost exclusively via black-box input-output test cases. They fail to assess whether an auto-regressive model maintains a coherent, mechanically faithful simulation of intermediate program states during execution [6], [7], [8].

In operating systems and systems programming, procedural correctness is non-negotiable. Concurrency control algorithms—such as deadlock detection, resource allocation safety, and dynamic physical memory partitioning—are governed by rigorous theoretical properties:
1. **Strict Discrete State Tracking:** Every transition must update resource availability vectors, process allocation matrices, or block allocation trees without state drift or phantom resource generation.
2. **Topological and Relational Invariants:** Identifying deadlocks requires systematic traversal of directed Wait-For Graphs to detect closed cycles without hallucinating non-existent dependency edges.
3. **Catastrophic Error Cascades:** A single state corruption at step $t$ invalidates all subsequent state assertions at $t+k$, converting downstream execution into an unfaithful hallucination.

```
       ┌─────────────────────────────────────────────────────────┐
       │                Problem Instance Prompt                  │
       │    (Matrix Allocations, Process Traces, WFG Edges)      │
       └────────────────────────────┬────────────────────────────┘
                                    │
                                    ▼
       ┌─────────────────────────────────────────────────────────┐
       │             LLM Step-by-Step Response Trace             │
       │        (State Transitions at t_1, t_2, ..., t_m)        │
       └────────────────────────────┬────────────────────────────┘
                                    │
                  ┌─────────────────┴─────────────────┐
                  ▼                                   ▼
       ┌────────────────────┐               ┌────────────────────┐
       │  Ground-Truth Trace │               │  Automated Scorer  │
       │ (Reference Solvers)│               │  (SA, FEP, ECR,    │
       │                    │               │   Invariant Valid) │
       └────────────────────┘               └────────────────────┘
```

When evaluating LLMs on such procedural tasks, standard outcome-based metrics (e.g., binary classification of whether a system is deadlocked or safe) introduce massive evaluation noise. On balanced datasets, an LLM can easily guess the correct binary verdict through statistical heuristics or shallow token correlations while executing an entirely invalid sequence of intermediate states.

To resolve this evaluation gap, we introduce **SVAC-Concurrency** (*Step-Verification of Algorithmic Concurrency*), a comprehensive, parameter-controlled benchmark designed to evaluate intermediate LLM reasoning traces across five foundational OS concurrency algorithms. Each instance is paired with an exact ground-truth execution trace computed by deterministic reference solvers, unit-tested against textbook worked examples [18] and, for WFG and Banker's algorithms (60 of 125 instances), validated via independent brute-force differential testing.

### Research Questions
We structure our empirical investigation around four central research questions:
- **RQ1 (Procedural Fidelity vs. Outcome Correctness):** Do LLMs produce faithful intermediate state transitions, or do high verdict accuracies mask severe intermediate state-tracking failures on balanced decision distributions?
- **RQ2 (Complexity Scaling & Failure Horizons):** How do increasing state-space bounds affect step accuracy, and at what execution horizon ($\text{FEP}$) do cascading errors initiate across different algorithmic structures?
- **RQ3 (Prompting Dynamics & Serialization Artifacts):** Does step-by-step verbalization (Chain-of-Thought) assist or destabilize discrete graph-traversal and matrix-tracking algorithms, and to what extent does few-shot prompting act as format serialization priming?
- **RQ4 (Equivalence & Architectural Robustness):** To what extent does strict positional scoring underestimate valid alternative execution paths, and how do open-weight models adhere to strict intermediate state schemas compared to instruction-tuned frontier APIs?

### Primary Contributions:
- **Comprehensive Benchmark Suite:** 125 unique instances across 5 core OS algorithms (Wait-For Graphs, Banker's Algorithm, Buddy System, Semaphores, and Mutexes) parameterized across 5 distinct complexity tiers ($N=375$ evaluations per model across 3 prompt strategies).
- **Multi-Dimensional Metric Taxonomy:** Formalization of Step Accuracy ($\text{SA}$), First Error Position ($\text{FEP}$), Error Cascade Rate ($\text{ECR}$), and Equivalence-Aware Invariant Validity to capture reasoning dynamics beyond binary verdicts.
- **Cross-Architectural Empirical Investigation:** Systematic comparison of four distinct model families: Google Gemini-3.5-Flash-Lite, OpenAI GPT-OSS-20B, NVIDIA Nemotron-3-Super-120B, and Liquid AI LFM-2.6B.
- **Deconstruction of the CoT Inversion Effect:** Discovery and formal characterization showing that the apparent collapse of CoT in graph cycle detection (85.4% Few-Shot vs. 7.5% CoT strict SA) is primarily driven by serialization tie-breaking divergence, while invariant-aware step validity remains robust at 93.2% with 93.3% verdict accuracy.
- **Equivalence-Aware Invariant Evaluation:** Demonstration that rigid positional matching under-reports valid algorithmic execution by 32.8% in Banker's and 64.3% in WFG, establishing the necessity of invariant-based semantic scoring.

---

## II. RELATED WORK

### A. Benchmarking Code Generation and Execution Reasoning
Early LLM code evaluation benchmarks such as HumanEval [3], MBPP [4], and APPS [5] established input-output testing as the standard paradigm for evaluating program synthesis. However, these benchmarks treat execution as an opaque black box. Recent efforts have shifted toward evaluating *execution reasoning*—whether an LLM can predict intermediate runtime variables or trace program flow. CRUXEval [19] evaluated code execution reasoning by testing input/output prediction across short Python snippets. REval [20] and CodeMind [21] introduced state-level execution tracing for general imperative code. While these benchmarks test arbitrary code snippets, they do not systematically probe canonical discrete algorithms where formal invariants, resource constraints, and topological cycles dictate correctness. SVAC-Concurrency provides precisely this specialized, parameter-controlled algorithmic framework.

### B. Mechanistic State Tracking in Transformers
A growing body of literature investigates whether transformer architectures maintain coherent internal world models during sequential tasks. Toshniwal et al. [10] demonstrated that auto-regressive language models track board state representations in chess games despite receiving only move sequences. Strobl et al. [9] surveyed the theoretical boundaries of what formal languages and state machines transformer architectures can express. Wang et al. [11] investigated graph traversal algorithms in natural language. In the systems domain, the precursor SVAC technical report [12] evaluated step-level reasoning in virtual memory page replacement policies (FIFO, LRU, Optimal, Clock). Additionally, the CONCUR benchmark by Huang et al. [13] evaluated LLMs on *synthesizing* concurrent synchronization primitives. Our work explicitly contrasts with CONCUR: rather than evaluating concurrent code synthesis, we evaluate *execution-trace verification*, isolating whether models accurately track concurrent state transitions and deadlock invariants.

### C. Prompting Dynamics and CoT Unfaithfulness
Chain-of-Thought (CoT) prompting [14] is widely documented to boost arithmetic and multi-hop reasoning. However, recent empirical studies reveal significant limits and pathology in verbalized reasoning. Lanham et al. [22] and Turpin et al. [23] demonstrated that CoT explanations are frequently unfaithful, serving as post-hoc rationalizations rather than causal computation drivers. Shi et al. [15] demonstrated that LLMs are easily distracted by irrelevant reasoning context, while Liu et al. [24] observed degradation in multi-step planning tasks when natural language narration exceeds formal state-space capacity. In graph-theoretic tasks, Agrawal et al. [17] investigated the structural limitations of language models on graph reasoning. Our work grounds these phenomena in operating systems concurrency, providing quantitative evidence of how serialization tie-breaks and verbalized narration interact with discrete state tracking.

---

## III. BENCHMARK ARCHITECTURE AND METHODOLOGY

```
+-----------------------------------------------------------------------------------------------+
|                                  SVAC-Concurrency Suite                                       |
+-------------------+-----------------------+-----------+--------------------+------------------+
| Algorithm Family  | State Representation  | Instances | Complexity Bounds  | Class Balance    |
+-------------------+-----------------------+-----------+--------------------+------------------+
| Wait-For Graph    | Directed Adjacency    | 30        | |V| in [2,6],      | 50% Deadlock (15)|
| (WFG)             | & Recursion Stack     |           | |E| in [1,8]       | 50% Acyclic (15) |
+-------------------+-----------------------+-----------+--------------------+------------------+
| Banker's          | Available Vector,     | 30        | P in [2,6],        | 50% Safe (15)    |
| Algorithm         | Allocation/Need Mtx   |           | R in [2,4]         | 50% Unsafe (15)  |
+-------------------+-----------------------+-----------+--------------------+------------------+
| Buddy System      | Free-list Binary      | 25        | 512 KB - 4096 KB,  | Deterministic    |
| Memory Allocation | Tree & Blocks         |           | Requests in [4,10] | Partition Trace  |
+-------------------+-----------------------+-----------+--------------------+------------------+
| Counting          | S.value & FIFO        | 20        | S in [1,3],        | Deterministic    |
| Semaphore         | Blocked Queue List    |           | Ops in [4,10]      | State Sequence   |
+-------------------+-----------------------+-----------+--------------------+------------------+
| Mutex Lock        | Owner ID & Lock       | 20        | Threads in [2,5],  | Deterministic    |
| Synchronization   | State Flag            |           | Ops in [4,8]       | Transition Trace |
+-------------------+-----------------------+-----------+--------------------+------------------+
| Total / Baseline  |                       | 125       | 5 Complexity Tiers | 50.0% Maj. Base  |
+-------------------+-----------------------+-----------+--------------------+------------------+
```

### A. Problem Formulations & Ground-Truth Verification

All problem instances are deterministically synthesized across five calibrated complexity tiers (Levels 1–5). Ground-truth execution traces are produced by reference Python solvers (`solvers/`) unit-tested against textbook worked examples from Silberschatz et al. [18]. Additionally, WFG and Banker's Algorithm solvers (60 of 125 instances) were independently cross-verified via brute-force differential testing against alternative reference implementations (3-color DFS oracle for WFG; exhaustive permutation search for Banker's).

1. **Wait-For Graph (WFG) Deadlock Detection:** Given a set of processes $P = \{P_0, \dots, P_{n-1}\}$ and directed wait edges $E \subseteq P \times P$, where $(P_i, P_j) \in E$ indicates $P_i$ is blocked waiting for a resource held by $P_j$. The model must execute depth-first search (DFS), tracking the active recursion stack and visited set at each step, identifying back-edges, reporting the cycle subgraph if present, and emitting a final verdict $\text{deadlock} \in \{\text{true}, \text{false}\}$. The dataset is strictly balanced: 15 instances contain cycles and 15 are directed acyclic graphs (DAGs), balanced evenly (3 positive, 3 negative) across all 5 complexity tiers.
2. **Banker's Algorithm for Deadlock Avoidance:** Given an Available resource vector $A \in \mathbb{N}^m$, Allocation matrix $\mathbf{Alloc} \in \mathbb{N}^{n \times m}$, and Max demand matrix $\mathbf{Max} \in \mathbb{N}^{n \times m}$. The model must compute $\mathbf{Need} = \mathbf{Max} - \mathbf{Alloc}$, iteratively identify an executable candidate process $P_i$ such that $\mathbf{Need}_i \le \text{Work}$, simulate resource reclamation $\text{Work} \leftarrow \text{Work} + \mathbf{Alloc}_i$, update the $\text{Finish}$ boolean array, and determine whether a complete safe sequence exists ($\text{safe} \in \{\text{true}, \text{false}\}$). The dataset is strictly balanced: 15 safe and 15 unsafe instances (3 per complexity tier).
3. **Buddy System Memory Allocation:** Given total memory size $M = 2^K$ and a sequential stream of allocation and deallocation operations. The model must track recursive block splits, power-of-two alignments, and buddy coalescing on free operations, returning the exact block partition state at each operation. Instances feature adversarial fragmentation requests where total free memory is sufficient but contiguous power-of-two blocks are unavailable, probing whether the model respects split/coalesce invariants.
4. **Counting Semaphore Simulation:** Given initial counter $S \ge 0$ and an interleaved execution stream of concurrent $\text{wait}(S)$ and $\text{signal}(S)$ calls from multiple threads. The model must track the integer value of $S$ and the FIFO blocked thread queue at every transition.
5. **Mutex Lock Simulation:** Evaluates mutual exclusion lock acquisition, priority ownership, contention blocking, and release transitions across concurrent threads.

### B. Mathematical Evaluation Framework

Let an evaluation instance $I$ have ground-truth trace $\mathbf{Y}^* = (y_1^*, y_2^*, \dots, y_{T^*}^*)$ of length $T^*$, and model-generated trace $\mathbf{\hat{Y}} = (\hat{y}_1, \hat{y}_2, \dots, \hat{y}_m)$ of length $m$.

#### 1. Formal Step Equality Specification
A step $\hat{y}_t$ matches ground truth $y_t^*$ ($\hat{y}_t = y_t^*$) if and only if all task-specific state attributes match under canonical normalization:
- **WFG Deadlock:**
  $$\hat{y}_t = y_t^* \iff \left(\hat{y}_t.\text{action} = y_t^*.\text{action}\right) \land \left(\hat{y}_t.\text{node} = y_t^*.\text{node}\right) \land \left(\text{sort}(\hat{y}_t.\text{visited}) = \text{sort}(y_t^*.\text{visited})\right) \land \left(\hat{y}_t.\text{stack} = y_t^*.\text{stack}\right)$$
  Visited nodes are compared as canonical sorted sets (order-insensitive), while the recursion stack is compared as an ordered sequence (order-sensitive).
- **Banker's Algorithm:**
  $$\hat{y}_t = y_t^* \iff \left(\hat{y}_t.\text{candidate} = y_t^*.\text{candidate}\right) \land \left(\hat{y}_t.\text{work\_before} = y_t^*.\text{work\_before}\right) \land \left(\hat{y}_t.\text{work\_after} = y_t^*.\text{work\_after}\right) \land \left(\hat{y}_t.\text{finish} = y_t^*.\text{finish}\right)$$
- **Buddy System:** Exact equality across all allocated block address-size tuples and free-list lists.
- **Semaphore / Mutex:** Exact equality of counter/owner state and blocked thread list order.

#### 2. Diagnostic Trace Metrics
1. **Step Accuracy ($\text{SA}$):** The proportion of ground-truth state transition steps where all structural state variables match identically:
   $$\text{SA} = \frac{1}{T^*} \sum_{t=1}^{\min(T^*, m)} \mathbb{I}(\hat{y}_t = y_t^*)$$
2. **First Error Position ($\text{FEP}$):** The earliest discrete step at which the model trace diverges from ground truth:
   $$\text{FEP} = \min \left( \{ t \in \{1, \dots, T^*\} \mid \hat{y}_t \ne y_t^* \} \cup \{ \infty \} \right)$$
3. **Error Cascade Rate ($\text{ECR}$):** The proportion of subsequent steps that remain incorrect following the initial point of failure:
   $$\text{ECR} = \begin{cases} \frac{1}{T^* - \text{FEP}} \sum_{t=\text{FEP}+1}^{T^*} \mathbb{I}(\hat{y}_t \ne y_t^*), & \text{if } \text{FEP} < T^* \\ 0, & \text{if } \text{FEP} \ge T^* \text{ or } \text{FEP} = \infty \end{cases}$$
4. **Verdict Accuracy ($\text{VA}$):** Binary correctness of the high-level conclusion. To prevent conflating parse failures with reasoning errors, we report both **$\text{VA}_{\text{parsed}}$** (computed conditionally over successfully formatted outputs) and **$\text{VA}_{\text{all}}$** (treating unparsed outputs as incorrect):
   $$\text{VA}_{\text{parsed}} = \frac{1}{N_{\text{parsed}}} \sum_{i=1}^{N_{\text{parsed}}} \mathbb{I}(\widehat{\text{verdict}}_i = \text{verdict}_i^*), \quad \text{VA}_{\text{all}} = \frac{1}{N_{\text{total}}} \sum_{i=1}^{N_{\text{total}}} \mathbb{I}(\text{parsed}_i \land \widehat{\text{verdict}}_i = \text{verdict}_i^*)$$

#### 3. Equivalence-Aware Invariant Scoring
Strict positional matching ($\hat{y}_t = y_t^*$) penalizes models when multiple valid execution paths exist (e.g., Banker's instances where multiple processes have $\mathbf{Need}_i \le \text{Work}$, or graph traversals with alternative neighbor ordering). We therefore formulate **Equivalence-Aware Invariant Validity ($\text{SA}_{\text{valid}}$)**:
- At each step $t$, verify that $\hat{y}_t.\text{candidate}$ is unfinished and satisfies $\mathbf{Need}_{\text{candidate}} \le \text{Work}_{t-1}$.
- Verify that $\text{Work}_t = \text{Work}_{t-1} + \mathbf{Alloc}_{\text{candidate}}$ and only the candidate process finishes.
- If safe, verify that $\hat{y}.\text{safe\_sequence}$ is an executable permutation under initial resources.

---

## IV. EXPERIMENTAL SETUP

All evaluations were executed under strict deterministic parameters ($\text{temperature} = 0.0$, $\text{top\_p} = 1.0$) across three prompt configurations: **Zero-Shot (ZS)** (direct JSON schema specification), **Few-Shot (FS)** (in-context exemplars of step-by-step execution), and **Chain-of-Thought (CoT)** (verbalized rationale preceding structured JSON emission). 

We evaluated four diverse foundation models:
1. **Google Gemini-3.5-Flash-Lite:** High-throughput dense instruction-tuned reasoning model evaluated via Google AI Studio API endpoints across all 125 instances ($N=375$).
2. **OpenAI GPT-OSS-20B:** Open-weight model evaluated via Groq high-speed LPU inference acceleration, scoped to WFG deadlock detection ($N=81$ scored attempts) due to upstream API rate-limits.
3. **NVIDIA Nemotron-3-Super-120B:** 120B-parameter open-weight foundation model evaluated via OpenRouter endpoints across all 125 instances ($N=375$ attempts).
4. **Liquid AI LFM-2.6B:** Non-transformer dynamical state-space architecture evaluated via OpenRouter endpoints, scoped to WFG ($N=39$ scored attempts).

---

## V. RESULTS AND EMPIRICAL ANALYSIS

```
+----------------------------------------------------------------------------------------------------------------------------+
|                                TABLE I: Multi-Provider Cross-Architecture Benchmark Results                                |
+-----------------------+--------------------+------------+------------+------------+------------+-------------+-------------+
| Model Architecture    | Organization / Lab | Attempted  | Parse Rate | Step Acc   | Error Casc | Verdict Acc | Verdict Acc |
|                       |                    | (N)        | (% JSON OK)| (Mean SA)  | (Mean ECR) | (VA parsed) | (VA all)    |
+-----------------------+--------------------+------------+------------+------------+------------+-------------+-------------+
| Gemini-3.5-Flash-Lite | Google DeepMind    | 375        | 99.2%      | 56.1%      | 36.9%      | 72.8%       | 72.3%       |
| GPT-OSS-20B           | OpenAI             |  81†       | 58.0%      | 53.1%*     | 45.3%*     | 100.0%*     | 58.0%       |
| Nemotron-3-Super-120B | NVIDIA             | 375        | 19.7%      | 48.5%*     | 41.3%*     | 95.9%*      | 18.9%       |
| Liquid LFM-2.6B       | Liquid AI          |  39†       | 69.2%      | 14.4%*     | 86.1%*     | 96.3%*      | 66.7%       |
+-----------------------+--------------------+------------+------------+------------+------------+-------------+-------------+
| Majority Baseline     | Random / Majority  | 375        | 100.0%     |  0.0%      | 100.0%     | 50.0%       | 50.0%       |
+-----------------------+--------------------+------------+------------+------------+------------+-------------+-------------+
* Computed conditionally over successfully parsed JSON outputs. 
† Open-weight runs scoped to WFG task subset due to upstream provider rate-limiting and connection resets. Nemotron was evaluated across the full suite via OpenRouter batching.
Note: Parse Rate = N_parsed / N_attempted. VA (parsed) measures semantic verdict correctness on parsed responses; VA (all) conflates parse failure as incorrect verdict.
```

```
+-----------------------------------------------------------------------------------------------+
|                 TABLE II: Per-Task Step Accuracy (%) Across Prompt Strategies                 |
|             (Evaluated on Gemini-3.5-Flash-Lite, N = 20-30 instances per cell)                |
+-----------------------------+--------------------+--------------------+-----------------------+
| Task Domain                 | Zero-Shot (ZS)     | Few-Shot (FS)      | Chain-of-Thought (CoT)|
+-----------------------------+--------------------+--------------------+-----------------------+
| WFG Deadlock Detection      |  4.4% (95% CI: 1-18)| 85.4% (95% CI: 69-94)|  7.5% (95% CI: 2-22)  |
| Banker's Safety Algorithm   | 32.9% (95% CI: 19-51)| 41.9% (95% CI: 25-60)| 49.7% (95% CI: 33-67) |
| Buddy System Allocation     | 30.5% (95% CI: 15-51)| 31.5% (95% CI: 16-52)| 49.1% (95% CI: 31-68) |
| Counting Semaphore Sync     | 91.2% (95% CI: 77-97)| 96.2% (95% CI: 84-99)| 95.0% (95% CI: 82-99) |
| Mutex Lock Synchronization  | 100.0%             | 100.0%             | 100.0%                |
+-----------------------------+--------------------+--------------------+-----------------------+
| Non-Saturated Subset Mean   | 22.6%              | 52.9%              | 35.4%                 |
| (WFG + Banker's + Buddy)    | (Overall Non-Saturated SA across all variants: 36.98%)        |
+-----------------------------+--------------------+--------------------+-----------------------+
| Instance-Weighted Mean      | 45.6%              | 68.2%              | 54.7%                 |
| (Headline Suite SA: 56.1%)  | *(N-weighted across 125 instances: 30,30,25,20,20; strategy mean 56.2% reconciles to headline)*  ||
+-----------------------------+--------------------+--------------------+-----------------------+
```

### A. The "Right Verdict for Wrong Reasons" Gap
A primary finding from our benchmark is the stark divergence between Verdict Accuracy and Step Accuracy. As shown in Table I, Gemini-3.5-Flash-Lite achieves an overall **Verdict Accuracy of 72.8%** on parsed responses, yet exhibits a mean **Step Accuracy of only 56.1%**.

Crucially, the 56.1% suite mean is heavily inflated by trivial state saturation in Mutex (100.0% SA) and Semaphore tasks (94.2% SA), which involve short, low-branching execution paths. When isolating the **non-saturating algorithmic tasks (WFG, Banker's, and Buddy System)**, mean Step Accuracy drops to **36.98%**. Because the decision tasks are strictly 50/50 balanced (majority baseline = 50.0%), the gap between 72.8% VA and 37.0% non-saturated SA demonstrates that outcome accuracy vastly overstates procedural competence: models routinely guess the correct outcome while executing flawed or hallucinated intermediate states.

### B. Deconstructing the CoT Inversion Effect: Priming vs. Invariants
Table II appears to show an extreme prompting anomaly:
- In linear-procedural tasks (Banker's and Buddy allocation), CoT prompting provides substantial gains (+16.8% and +18.6% SA over Zero-Shot, respectively).
- In Wait-For Graph cycle detection, strict positional matching reports an apparent collapse: Few-Shot prompting attains **85.4% SA**, whereas CoT plunges to **7.5% SA** (and Zero-Shot is 4.4% SA).

```
       Strict Positional SA on WFG Deadlock:
       Few-Shot (Structured Examples) : [███████████████████████████████] 85.4%
       Zero-Shot (Direct JSON)        : [██                            ]  4.4%
       Chain-of-Thought (Verbalized)  : [███                           ]  7.5%

       Equivalence-Aware Invariant SA on WFG Deadlock:
       Few-Shot (Structured Examples) : [████████████████████████████████] 100.0%
       Zero-Shot (Direct JSON)        : [██████████████████████████████  ]  93.7%
       Chain-of-Thought (Verbalized)  : [██████████████████████████████  ]  93.2%
```

A superficial reading would conclude that Chain-of-Thought verbalization causes general topological reasoning breakdown. However, cross-examining **Error Taxonomy (Table III)** and **Invariant Scoring (Table IV)** reveals a much deeper, nuanced scientific truth:

```
+-----------------------------------------------------------------------------------------------+
|             TABLE III: WFG Empirical Error Taxonomy & Accuracy Breakdown (Gemini)             |
+------------------------------------+--------------------+--------------------+----------------+
| Metric / Error Category            | Zero-Shot (N=30)   | Few-Shot (N=30)    | CoT (N=30)     |
+------------------------------------+--------------------+--------------------+----------------+
| Visited Set Corruption             | 30 (100.0%)        |  7 (23.3%)         | 30 (100.0%)    |
| Recursion Stack Corruption         | 14 (46.7%)         | 12 (40.0%)         |  8 (26.7%)     |
| Wrong Traversal Node               | 20 (66.7%)         | 12 (40.0%)         | 18 (60.0%)     |
| Step Count Mismatch                | 16 (53.3%)         | 13 (43.3%)         | 12 (40.0%)     |
| False Cycle Hallucination          |  3 (10.0%)         |  0 (0.0%)          |  2 (6.7%)      |
| Missed Cycle (False Negative)      |  0 (0.0%)          |  0 (0.0%)          |  0 (0.0%)      |
+------------------------------------+--------------------+--------------------+----------------+
| Verdict Accuracy (VA)              | 27 / 30 (90.0%)    | 28 / 28 (100.0%)   | 28 / 30 (93.3%)|
| Strict Positional Step Accuracy    |  4.4%              | 85.4%              |  7.5%          |
| Invariant-Based Valid Step Accuracy| 93.7%              | 100.0%             | 93.2%          |
+------------------------------------+--------------------+--------------------+----------------+
```

As demonstrated in Table III:
1. **High Invariant Validity and Verdict Accuracy:** Under invariant checking, Zero-Shot achieves **93.7% valid SA** (90.0% VA), Few-Shot achieves **100.0% valid SA** (100.0% VA), and CoT achieves **93.2% valid SA** (93.3% VA). Models across all three strategies execute sound DFS traversals.
2. **Why Strict SA Collapses (The Serialization Priming Effect):** In Few-Shot prompting, the in-context exemplar explicitly demonstrates the solver's canonical tie-breaking convention (alphabetical neighbor selection). Without this formatting prompt, Zero-Shot and CoT models explore valid neighbors in non-canonical order. Because strict positional matching requires step $t$ to match identically, a single non-canonical branch at Step 1 invalidates every subsequent positional comparison, resulting in FEP = 1 in 100% of cases and depressing strict SA to 4.4%–7.5%.
3. **The Residual CoT Tracking Drift:** Although CoT maintains 93.2% invariant validity, Table III confirms that verbalization induces subtle tracking drift: `visited_set_corruption` occurs in 100% of CoT traces (versus 23.3% in Few-Shot), and false cycle hallucination rises from 0% in Few-Shot to 6.7% in CoT. In long verbalized traces, models occasionally conflate backtracked nodes with active recursion path elements.

**Case Study: Localized CoT Backtrack Drift (Instance `wfg_3ceec919261d`)**  
Ground truth for this instance is `deadlock=False` (DAG). At step 9, the model's trace correctly backtracks P4 out of the recursion stack (`"recursion_stack": ["P0"]`), marking P4 as fully explored. However, 12 steps later at step 21, the model re-asserts P4 as being "in the recursion stack" and declares a false cycle—contradicting its own step-9 state. This demonstrates how unconstrained natural language tokens can induce localized state-binding drift at terminal steps.

### C. First Error Position (FEP) Dynamics
Evaluating the discrete point of first failure ($\text{FEP}$) reveals fundamentally distinct degradation dynamics across algorithmic domains (visualized in Figure 5):
- **Immediate Topological Divergence (WFG):** Under strict matching, **$\text{FEP} = 1$ in 100.0% of error cases** for ZS and CoT (mean $\text{FEP} = 1.00$) due to branch tie-break divergence at the initial node. Under Few-Shot, format priming aligns canonical order, delaying initial failure to mean $\text{FEP} = 8.38$ (median 7.0).
- **Early Matrix Misalignment (Banker's):** For Banker's algorithm, $\text{FEP} = 1$ occurs in 76.0% (ZS), 59.1% (FS), and 82.4% (CoT) of error instances (mean $\text{FEP} \in [1.28, 1.55]$), driven by candidate process selection divergence.
- **Gradual Multi-Step State Drift (Buddy System):** In contrast to WFG and Banker's, Buddy allocation exhibits true intermediate degradation: $\text{FEP} = 1$ occurs in only 22.7%–34.8% of errors, with a mean $\text{FEP}$ of **6.96 steps (ZS), 7.57 steps (FS), and 6.55 steps (CoT)** (median $\text{FEP} = 4.0\text{--}5.0$). Models correctly perform initial block splits, but accumulate arithmetic fragmentation errors over long horizons.

### D. Equivalence-Aware Invariant Scoring vs. Strict Positional Matching
A critical methodological insight is that rigid positional comparison ($\hat{y}_t = y_t^*$) severely under-reports model reasoning capabilities when algorithms admit multiple valid execution paths.

```
+-----------------------------------------------------------------------------------------------+
|              TABLE IV: Invariant-Based Valid SA vs. Strict Positional SA (Gemini)             |
+-----------------------------+--------------------+--------------------+-----------------------+
| Task Family                 | Strict Positional  | Invariant-Based    | Delta (Valid - Strict)|
|                             | Step Accuracy (SA) | Valid SA           |                       |
+-----------------------------+--------------------+--------------------+-----------------------+
| Banker's Safety (N=90)      | 41.5%              | 74.3%              | +32.8%                |
|   - Zero-Shot               | 32.9%              | 74.4%              | +41.6%                |
|   - Few-Shot                | 41.9%              | 78.9%              | +37.1%                |
|   - Chain-of-Thought        | 49.7%              | 69.5%              | +19.8%                |
+-----------------------------+--------------------+--------------------+-----------------------+
| WFG Deadlock (N=88)         | 31.2%              | 95.6%              | +64.3%                |
|   - Zero-Shot               |  4.4%              | 93.7%              | +89.4%                |
|   - Few-Shot                | 85.4%              | 100.0%             | +14.6%                |
|   - Chain-of-Thought        |  7.5%              | 93.2%              | +85.8%                |
+-----------------------------+--------------------+--------------------+-----------------------+
```

As detailed in Table IV:
1. **Banker's Algorithm:** When verifying that each chosen candidate process satisfies $\mathbf{Need}_i \le \text{Work}$ and properly reclaims resources under the model's own state, valid step accuracy reaches **74.3%** (+32.8% over positional SA). In 7 out of 90 instances, models executed a sound safe sequence that prioritized a different candidate process than the reference solver's deterministic tie-break.
2. **WFG Cycle Detection:** Under invariant checking (valid neighbor traversal and backtracking), WFG valid step accuracy reaches **95.6%** (+64.3% over positional SA).
3. **Trace Length Alignment Sensitivity:** Evaluating monotonic Longest Common Subsequence (LCS) alignment reveals that trace length disparity ($m / T^* \approx 1.3\text{--}2.8$) creates substantial artificial cascade penalties: aligned SA increases Banker's CoT from 49.7% to 63.5% (+13.8%) and WFG Few-Shot from 85.4% to 97.7% (+12.3%).

### E. Cross-Model Schema Fragility and Formatting Brittleness
Table I underscores a profound divergence between proprietary instruction-tuned models and open-weight architectures. While Gemini-3.5 achieved 99.2% parse success, **NVIDIA Nemotron-3-Super-120B achieved only 19.7% parse success**, with the remaining 80.3% of outputs failing JSON decoding due to missing closing delimiters, extraneous conversational preambles, or unescaped tokens. 

Crucially, auditing the parsed subset reveals that Nemotron achieved **95.9% Verdict Accuracy** and **48.5% Step Accuracy**. Prior naive evaluations reported Nemotron's VA as 18.9% by treating parse failures as incorrect verdicts ($71 / 375 = 18.9\%$). Our dual-metric decomposition ($\text{VA}_{\text{parsed}}$ vs $\text{VA}_{\text{all}}$) establishes that open-weight models suffer not from semantic reasoning deficits, but from strict output-channel schema adherence failures.

---

## VI. DISCUSSION AND PRACTICAL IMPLICATIONS

### A. Token-Level Format Following vs. Algorithmic Competence
Our findings highlight that raw parameter count does not ensure procedural fidelity. Nemotron-120B contains 120B total parameters, yet failed schema parsing on 80.3% of tasks where Gemini-3.5-Flash-Lite parsed cleanly. For practical systems verification pipelines, constrained decoding (e.g., grammar-based sampling via outlines or JSON schemas) is essential before open-weight models can be reliably deployed.

### B. Implications for Automated Verification and Systems Pedagogy
1. **Never rely on unverified verdicts:** On balanced 50/50 concurrency distributions, LLMs exhibit a 35.8% divergence between outcome correctness and procedural fidelity. Downstream systems tools must verify intermediate execution traces.
2. **Distinguish between format compliance and procedural validity:** In graph and state-machine problems, few-shot exemplars serve primarily to prime arbitrary serialization conventions (tie-breaks). Automated benchmarks must adopt equivalence-aware verifiers to avoid mistaking valid alternative traversals for reasoning failures.
3. **Constrain generative freedom in topological tasks:** Unstructured verbalization in CoT increases state-binding drift on recursion stacks. Structured schema emission should be enforced.

---

## VII. LIMITATIONS

This empirical investigation is bounded by several methodology considerations:
1. **Single-Run Deterministic Sampling:** Inferences were performed at $\text{temperature} = 0.0$. We did not evaluate temperature-swept self-consistency or majority voting across multiple runs.
2. **Per-Cell Sample Size:** With 125 instances spanning 5 tasks and 5 complexity levels, individual task-complexity sub-cells contain $N = 4\text{--}6$ instances, though each prompt strategy evaluates $N = 20\text{--}30$ instances per algorithm family.
3. **Partial Evaluation of Open Models:** Upstream API rate-limiting on open-router endpoints restricted open-weight evaluations (GPT-OSS-20B and LFM-2.6B) to WFG subsets, necessitating conditional reporting over parsed subsets.
4. **Synthetic Problem Horizons:** Instances model canonical textbook concurrency algorithms ($P \le 6, R \le 4$) rather than production-scale distributed systems traces.
5. **Static Prompting Regimes:** We evaluated static ZS, FS, and CoT prompts without dynamic tool feedback, external Python interpreter execution, or self-correction loops.
6. **Tie-Breaking Sensitivity:** While invariant-aware scoring resolves alternative valid sequences, strict positional SA remains sensitive to canonical solver ordering.

---

## VIII. FUTURE WORK

Future extensions of SVAC-Concurrency will investigate:
1. **Grammar-Constrained Decoding:** Evaluating whether formal context-free grammars (CFGs) eliminate open-weight formatting collapse.
2. **Reinforcement Learning with Step Verifiers:** Utilizing SVAC's intermediate step verifiers as dense process reward models (PRMs) to train reasoning models on discrete concurrency invariants.
3. **Kernel-Level Concurrency Traces:** Extending problem instances to real Linux kernel eBPF trace logs and lockdep synchronization graphs.

---

## IX. CONCLUSION

We presented **SVAC-Concurrency**, a fine-grained, open-source benchmark for evaluating LLM intermediate reasoning traces on Operating System concurrency algorithms. Through multi-dimensional metrics ($\text{SA}$, $\text{FEP}$, $\text{ECR}$, and Equivalence-Aware Validity), we showed that high outcome accuracy masks severe intermediate state failures, deconstructed the CoT Inversion Effect in topological deadlock detection as serialization tie-breaking priming, and demonstrated the critical impact of invariant-aware scoring. All benchmark datasets, reference solvers, and evaluation harnesses are made publicly available to advance verifiable algorithmic reasoning.

---

## REFERENCES

1. T. Brown et al., "Language Models are Few-Shot Learners," *Adv. Neural Inf. Process. Syst. (NeurIPS)*, vol. 33, pp. 1877–1901, 2020.
2. S. Bubeck et al., "Sparks of Artificial General Intelligence: Early experiments with GPT-4," *arXiv:2303.12712*, 2023.
3. M. Chen et al., "Evaluating Large Language Models Trained on Code," *arXiv:2107.03374*, 2021.
4. J. Austin et al., "Program Synthesis with Large Language Models," *arXiv:2108.07732*, 2021.
5. D. Hendrycks et al., "Measuring Coding Challenge Competence With APPS," in *Proc. NeurIPS*, 2021.
6. K. Cobbe et al., "Training Verifiers to Solve Math Word Problems," *arXiv:2110.14168*, 2021.
7. D. Hendrycks et al., "Measuring Mathematical Problem Solving with the MATH Dataset," in *Proc. NeurIPS*, 2021.
8. H. Lightman et al., "Let's Verify Step by Step," in *Proc. Int. Conf. Learn. Represent. (ICLR)*, 2024.
9. L. Strobl, W. Merrill, G. Weiss, D. Chiang, and D. Angluin, "What Formal Languages Can Transformers Express? A Survey," *Trans. Assoc. Comput. Linguist. (TACL)*, vol. 12, pp. 543–561, 2024.
10. S. Toshniwal et al., "Chess as a Testbed for Language Model State Tracking," in *Proc. AAAI Conf. Artif. Intell.*, vol. 36, no. 10, pp. 11385–11393, 2022.
11. H. Wang et al., "Can Language Models Solve Graph Problems in Natural Language?," in *Proc. NeurIPS*, 2023.
12. J. M. Kumar, J. S. Chakri, Y. Kothari, M. Mandal, Y. Sinha, and D. Kumar, "Evaluating LLM Reasoning on Operating System Algorithms via Step-Level Verification," in *Proc. ICML Workshop on Complex Task Benchmarks (CTB)*, 2026.
13. J. Huang, T. Mahmud, C. Pasareanu, and G. Yang, "CONCUR: Benchmarking LLMs for Concurrent Code Generation," *arXiv preprint arXiv:2603.03683*, 2026.
14. J. Wei et al., "Chain-of-Thought Prompting Elicits Reasoning in Large Language Models," in *Proc. NeurIPS*, 2022.
15. F. Shi et al., "Large Language Models Can Be Easily Distracted by Irrelevant Context," in *Proc. ICML*, 2023.
16. Z. Chu et al., "A Survey of Chain of Thought Reasoning: Advances, Frontiers and Challenges," *IEEE Trans. Knowl. Data Eng.*, 2024.
17. P. Agrawal, S. Vasania, and C. Tan, "Exploring the Limitations of Graph Reasoning in Large Language Models," *arXiv preprint arXiv:2402.01805*, Feb. 2024.
18. A. Silberschatz, P. B. Galvin, and G. Gagne, *Operating System Concepts*, 10th ed. Hoboken, NJ, USA: Wiley, 2018.
19. A. Gu et al., "CRUXEval: A Benchmark for Code Reasoning, Understanding and Execution," in *Proc. ICML*, 2024.
20. J. Chen et al., "Reasoning Runtime Behavior of a Program with LLM: How Far Are We?," in *Proc. 47th IEEE/ACM Int. Conf. Softw. Eng. (ICSE)*, 2025. arXiv:2403.16437.
21. C. Liu, S. D. Zhang, A. R. Ibrahimzada, and R. Jabbarvand, "CodeMind: A Framework to Challenge Large Language Models for Code Reasoning," in *Proc. 62nd Annu. Meeting Assoc. Comput. Linguist. (ACL)*, 2024. arXiv:2402.09664.
22. T. Lanham et al., "Measuring Faithfulness in Chain-of-Thought Reasoning," *arXiv:2307.13702*, 2023.
23. M. Turpin et al., "Language Models Don't Always Say What They Think: Unfaithful Explanations in Chain-of-Thought Prompting," in *Proc. NeurIPS*, 2023.
24. R. Liu, J. Geng, A. J. Wu, I. Sucholutsky, T. Lombrozo, and T. L. Griffiths, "Mind Your Step (by Step): Chain-of-Thought Can Reduce Performance on Tasks Where Thinking Makes Humans Worse," *arXiv preprint arXiv:2410.21333*, 2024. (ICML 2025)
