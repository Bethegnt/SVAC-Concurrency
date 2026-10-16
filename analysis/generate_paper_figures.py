"""
Generate all publication-quality figures for SVAC-Concurrency paper.
All numbers sourced directly from verified scorer output (Oct 2026 re-score).
Output: analysis/figures/paper_fig*.pdf (for LaTeX) and .png (preview)
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import os

OUT_DIR = os.path.join(os.path.dirname(__file__), 'figures')
os.makedirs(OUT_DIR, exist_ok=True)

# ── Color palette (colorblind-friendly, IEEE-print safe) ──────────────────────
C_GEMINI   = '#1A73E8'   # Google blue
C_GPT      = '#34A853'   # green
C_NEMOTRON = '#E37400'   # amber
C_LIQUID   = '#9C27B0'   # purple
C_BASELINE = '#757575'   # grey

C_ZS  = '#2563EB'   # blue
C_FS  = '#16A34A'   # green
C_COT = '#DC2626'   # red

FONT = {'family': 'DejaVu Sans', 'size': 10}
matplotlib.rc('font', **FONT)
matplotlib.rc('axes', titlesize=11, labelsize=10)
matplotlib.rc('xtick', labelsize=9)
matplotlib.rc('ytick', labelsize=9)
matplotlib.rc('legend', fontsize=9)

# ══════════════════════════════════════════════════════════════════════════════
# FIG 1 — Per-Task SA Heatmap (Prompt Strategy × Task)
# Source: svac_run_evaluation.py → Gemini-3.5-Flash-Lite AGGREGATE BY TASK x PROMPT VARIANT
# Verified Oct 2026 re-score.
# ══════════════════════════════════════════════════════════════════════════════
def fig1_task_heatmap():
    tasks = ['WFG\nDeadlock', "Banker's\nSafety", 'Buddy\nSystem',
             'Counting\nSemaphore', 'Mutex\nLock']
    strategies = ['Zero-Shot', 'Few-Shot', 'CoT']

    # Gemini-3.5-Flash-Lite per-task SA by variant
    data = np.array([
        [4.4,  85.4, 7.5 ],   # WFG
        [32.9, 41.9, 49.7],   # Banker's
        [30.5, 31.5, 49.1],   # Buddy
        [91.2, 96.2, 95.0],   # Semaphore
        [100.0,100.0,100.0],  # Mutex
    ])

    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    im = ax.imshow(data, cmap='RdYlGn', vmin=0, vmax=100, aspect='auto')

    ax.set_xticks(range(3))
    ax.set_xticklabels(strategies, fontweight='bold')
    ax.set_yticks(range(5))
    ax.set_yticklabels(tasks)
    ax.set_title('Per-Task Step Accuracy (%) by Prompt Strategy\n'
                 '(Gemini-3.5-Flash-Lite, N=20–30 instances/cell)',
                 pad=8, fontweight='bold')

    # Annotate cells
    for i in range(5):
        for j in range(3):
            v = data[i, j]
            color = 'white' if v < 20 or v > 85 else 'black'
            ax.text(j, i, f'{v:.1f}%', ha='center', va='center',
                    fontsize=10, fontweight='bold', color=color)

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label('Step Accuracy (%)', rotation=270, labelpad=12)

    # Highlight non-saturated zone
    rect = plt.Rectangle((-0.5, -0.5), 3, 3, linewidth=2,
                          edgecolor='#1A73E8', facecolor='none',
                          linestyle='--', label='Non-saturated tasks')
    ax.add_patch(rect)
    ax.legend(loc='lower right', framealpha=0.85)

    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'paper_fig1_heatmap.pdf'), dpi=300, bbox_inches='tight')
    fig.savefig(os.path.join(OUT_DIR, 'paper_fig1_heatmap.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('✓ Fig 1 (heatmap) saved')

# ══════════════════════════════════════════════════════════════════════════════
# FIG 2 — Cross-Model WFG-Only Comparison (grouped bar)
# WFG is the only task where all 4 models have N=90 for fair comparison.
# Source: svac_run_evaluation.py WFG task rows for each model (Oct 2026 re-score)
# ══════════════════════════════════════════════════════════════════════════════
def fig2_cross_model_bar():
    models = ['Gemini\n3.5-Flash-Lite\n(88/90)', 'GPT-OSS\n20B\n(53/90)',
              'Nemotron\n120B\n(48/90)', 'Liquid\nLFM-2.6B\n(27/90)',
              'Majority\nBaseline']
    colors = [C_GEMINI, C_GPT, C_NEMOTRON, C_LIQUID, C_BASELINE]

    # WFG-only numbers (verified from scorer output)
    sa         = [31.2, 48.1, 43.2, 14.4, 0.0  ]
    ecr        = [73.8, 50.4, 56.6, 86.1, 100.0]
    va_parsed  = [94.3, 100.0, 100.0, 96.3, 50.0]
    va_all     = [92.2, 58.9, 53.3, 28.9, 50.0]

    metrics = ['Step Acc.\n(SA)*', 'Error Cascade\nRatio (ECR)*', 'Verdict Acc.\n(Parsed)*', 'Verdict Acc.\n(All)']

    x   = np.arange(len(metrics))
    w   = 0.14
    fig, ax = plt.subplots(figsize=(7.5, 4.2))

    for i, (model, color) in enumerate(zip(models, colors)):
        vals = [sa[i], ecr[i], va_parsed[i], va_all[i]]
        offset = (i - 2) * w
        ax.bar(x + offset, vals, w, label=model, color=color,
               edgecolor='white', linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, fontweight='bold')
    ax.set_ylabel('Score (%)')
    ax.set_ylim(0, 115)
    ax.set_title('Cross-Architecture WFG Deadlock Detection (N=90 per model)\n'
                 '*SA, ECR, VA(Parsed) computed over parsed responses only',
                 fontweight='bold', pad=8, fontsize=10)
    ax.axhline(50, color='#757575', linewidth=0.8, linestyle=':', label='Majority baseline (50%)')
    ax.legend(loc='upper right', ncol=2, framealpha=0.9, fontsize=7.5)

    # Note about ECR: lower is better
    ax.annotate('↓ ECR: lower = better', xy=(1, 108), ha='center',
                fontsize=8, color='#555555', style='italic')

    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'paper_fig2_cross_model.pdf'), dpi=300, bbox_inches='tight')
    fig.savefig(os.path.join(OUT_DIR, 'paper_fig2_cross_model.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('✓ Fig 2 (cross-model WFG bar) saved')

# ══════════════════════════════════════════════════════════════════════════════
# FIG 3 — WFG Error Taxonomy Stacked Bar
# Source: Gemini WFG error taxonomy (unchanged, Gemini-only analysis)
# ══════════════════════════════════════════════════════════════════════════════
def fig3_wfg_taxonomy():
    categories = ['Visited Set\nCorruption', 'Recursion Stack\nCorruption',
                  'Wrong Traversal\nNode', 'Step Count\nMismatch',
                  'False Cycle\nHallucination']
    zs  = [100.0, 46.7, 66.7, 53.3, 10.0]
    fs  = [23.3,  40.0, 40.0, 43.3, 0.0 ]
    cot = [100.0, 26.7, 60.0, 40.0, 6.7 ]

    x = np.arange(len(categories))
    w = 0.24

    fig, ax = plt.subplots(figsize=(7.5, 4.0))

    b1 = ax.bar(x - w, zs,  w, label='Zero-Shot', color=C_ZS,  edgecolor='white')
    b2 = ax.bar(x,     fs,  w, label='Few-Shot',  color=C_FS,  edgecolor='white')
    b3 = ax.bar(x + w, cot, w, label='CoT',       color=C_COT, edgecolor='white')

    # Value labels on bars
    for bars in [b1, b2, b3]:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width()/2, h + 1.5,
                        f'{h:.0f}%', ha='center', va='bottom', fontsize=7.5, fontweight='bold')

    ax.set_xticks(x)
    ax.set_xticklabels(categories, fontsize=9)
    ax.set_ylabel('Instances with Error (%)')
    ax.set_ylim(0, 118)
    ax.set_title('WFG Error Taxonomy by Prompt Strategy\n(Gemini-3.5-Flash-Lite, N=30 per strategy)',
                 fontweight='bold', pad=8)
    ax.legend(framealpha=0.9)
    ax.axhline(100, color='#CC0000', linewidth=0.7, linestyle='--', alpha=0.5)

    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'paper_fig3_wfg_taxonomy.pdf'), dpi=300, bbox_inches='tight')
    fig.savefig(os.path.join(OUT_DIR, 'paper_fig3_wfg_taxonomy.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('✓ Fig 3 (WFG taxonomy) saved')

# ══════════════════════════════════════════════════════════════════════════════
# FIG 4 — Strict SA vs Invariant-Based Valid SA (the "gap" figure)
# Source: validity_checker.py output (Gemini, Banker's + WFG)
# ══════════════════════════════════════════════════════════════════════════════
def fig4_invariant_gap():
    labels   = ["Banker's\nZS", "Banker's\nFS", "Banker's\nCoT",
                "WFG\nZS", "WFG\nFS", "WFG\nCoT"]
    strict   = [32.9, 41.9, 49.7,  4.4, 85.4,  7.5]
    valid_sa = [74.4, 78.9, 69.5, 93.7, 100.0, 93.2]
    deltas   = [v - s for v, s in zip(valid_sa, strict)]

    x = np.arange(len(labels))
    w = 0.35

    fig, ax = plt.subplots(figsize=(7.0, 4.0))

    bars_s = ax.bar(x - w/2, strict,   w, label='Strict Positional SA',
                    color='#DC2626', edgecolor='white', alpha=0.85)
    bars_v = ax.bar(x + w/2, valid_sa, w, label='Invariant Valid SA\n(action-level legality)',
                    color='#16A34A', edgecolor='white', alpha=0.85)

    # Delta arrows / annotations
    for i, (s, v, d) in enumerate(zip(strict, valid_sa, deltas)):
        mid = (x[i] - w/2 + x[i] + w/2) / 2
        ax.annotate('', xy=(mid + w/2, v), xytext=(mid - w/2, s),
                    arrowprops=dict(arrowstyle='->', color='#1A73E8', lw=1.5))
        ax.text(mid + w/2 + 0.02, (s + v)/2, f'+{d:.1f}%',
                fontsize=7.5, color='#1A73E8', fontweight='bold', va='center')

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=9)
    ax.set_ylabel('Step Accuracy (%)')
    ax.set_ylim(0, 115)
    ax.set_title('Strict vs. Invariant-Based Step Accuracy\n'
                 '(Serialization Priming Effect — Banker\'s & WFG)',
                 fontweight='bold', pad=8)
    ax.legend(framealpha=0.9)

    # Separator between Banker's and WFG groups
    ax.axvline(2.5, color='#555555', linewidth=1, linestyle='--', alpha=0.5)
    ax.text(1.0, 108, "Banker's Algorithm", ha='center', fontsize=8.5,
            color='#333333', fontweight='bold')
    ax.text(4.0, 108, 'WFG Deadlock', ha='center', fontsize=8.5,
            color='#333333', fontweight='bold')

    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'paper_fig4_invariant_gap.pdf'), dpi=300, bbox_inches='tight')
    fig.savefig(os.path.join(OUT_DIR, 'paper_fig4_invariant_gap.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('✓ Fig 4 (invariant gap) saved')

# ══════════════════════════════════════════════════════════════════════════════
# FIG 5 — Benchmark Architecture Overview (schematic)
# ══════════════════════════════════════════════════════════════════════════════
def fig5_architecture():
    fig, ax = plt.subplots(figsize=(7.0, 3.8))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 6)
    ax.axis('off')
    ax.set_title('SVAC-Concurrency Benchmark Pipeline Overview',
                 fontweight='bold', fontsize=12, pad=10)

    def box(x, y, w, h, text, color, fontsize=8.5):
        rect = mpatches.FancyBboxPatch((x, y), w, h,
            boxstyle='round,pad=0.12', linewidth=1.4,
            edgecolor='#333333', facecolor=color, zorder=3)
        ax.add_patch(rect)
        ax.text(x + w/2, y + h/2, text, ha='center', va='center',
                fontsize=fontsize, fontweight='bold', color='white',
                wrap=True, zorder=4, multialignment='center')

    def arrow(x1, y1, x2, y2):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
            arrowprops=dict(arrowstyle='->', color='#333333', lw=1.5))

    # Row 1: Algorithm families
    box(0.1, 4.3, 1.7, 1.2, 'WFG\nDeadlock\n(N=30)',    '#1A73E8')
    box(2.0, 4.3, 1.7, 1.2, "Banker's\nSafety\n(N=30)", '#0F9D58')
    box(3.9, 4.3, 1.7, 1.2, 'Buddy\nSystem\n(N=25)',    '#E37400')
    box(5.8, 4.3, 1.7, 1.2, 'Semaphore\n(N=20)',        '#9C27B0')
    box(7.7, 4.3, 1.7, 1.2, 'Mutex\nLock\n(N=20)',      '#E53935')

    # Row 2: Prompting
    box(1.5, 2.8, 7.0, 0.9, '3 Prompt Strategies: Zero-Shot │ Few-Shot │ Chain-of-Thought', '#37474F')

    # Row 3: LLM
    box(1.5, 1.6, 7.0, 0.9, 'LLM Inference  (Gemini · GPT-OSS · Nemotron · Liquid LFM)', '#1565C0')

    # Row 4: Verifier + Metrics
    box(0.3, 0.2, 4.2, 1.0, 'Equivalence-Aware\nStep Verifier (Oracle)', '#2E7D32')
    box(5.2, 0.2, 4.5, 1.0, 'Metrics: SA · ECR · FEP\nVA · Invariant Valid SA', '#6A1B9A')

    # Arrows
    for xc in [1.0, 2.85, 4.75, 6.65, 8.55]:
        arrow(xc, 4.3, xc, 3.7)
    arrow(5.0, 2.8, 5.0, 2.5)
    arrow(5.0, 1.6, 5.0, 1.2)
    arrow(3.0, 1.2, 2.7, 1.0)
    arrow(7.0, 1.2, 7.5, 1.0)

    plt.tight_layout()
    fig.savefig(os.path.join(OUT_DIR, 'paper_fig5_architecture.pdf'), dpi=300, bbox_inches='tight')
    fig.savefig(os.path.join(OUT_DIR, 'paper_fig5_architecture.png'), dpi=150, bbox_inches='tight')
    plt.close()
    print('✓ Fig 5 (architecture) saved')


if __name__ == '__main__':
    print('Generating all paper figures...')
    fig1_task_heatmap()
    fig2_cross_model_bar()
    fig3_wfg_taxonomy()
    fig4_invariant_gap()
    fig5_architecture()
    print(f'\nAll figures saved to: {OUT_DIR}')
    for f in sorted(os.listdir(OUT_DIR)):
        if f.startswith('paper_fig'):
            path = os.path.join(OUT_DIR, f)
            print(f'  {f}  ({os.path.getsize(path)//1024} KB)')
