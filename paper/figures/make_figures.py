"""The paper's figures, from the result files (via benchmarks.paper_stats) and the stats it saved.

    python paper/figures/make_figures.py    # needs matplotlib; writes the PDFs next to this file
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "backend"))
from benchmarks.paper_stats import load, outcome  # noqa: E402

STATS = HERE.parents[1] / "backend/benchmarks/results/stats/paper-stats-fresh.json"
WIDTH = 3.45  # one IEEE column, inches

# Light-mode slots from a colour-blind-checked categorical palette; text stays in ink, not series colour
INK, MUTED, GRID = "#0b0b0b", "#52514e", "#e4e3df"
NEUTRAL, BLUE, ORANGE = "#c9c8c2", "#2a78d6", "#eb6834"

plt.rcParams.update({
    "font.family": "serif", "font.serif": ["Times New Roman", "Nimbus Roman", "STIXGeneral"],
    "mathtext.fontset": "stix", "font.size": 7.5, "axes.labelsize": 7.5, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "pdf.fonttype": 42,
})


def failure_modes(bugs):
    """Each model alone: resolved, visible failures (the loop ends on failing tests), silent (accepted but wrong)."""
    tasks = sorted(bugs)
    rows = []
    for name, setup in (("Claude Haiku 5.5", "haiku"), ("Gemini Flash-Lite", "lite"), ("Claude Sonnet 5.5", "sonnet")):
        o = [outcome(bugs[t][setup]) for t in tasks]
        rows.append((name, o.count("solved"), o.count("failed"), o.count("wrong")))
    fig, ax = plt.subplots(figsize=(WIDTH, 1.55))
    for i, (name, solved, visible, silent) in enumerate(rows):
        left = 0
        for value, colour in ((solved, NEUTRAL), (visible, BLUE), (silent, ORANGE)):
            ax.barh(i, value, left=left, color=colour, height=0.62, edgecolor="white", linewidth=1)
            if value >= 40:
                ax.text(left + value / 2, i, str(value), ha="center", va="center", fontsize=6.5,
                        color=INK if colour == NEUTRAL else "white")
            elif value:
                ax.text(left + value / 2, i, str(value), ha="center", va="center", fontsize=5.3, color="white")
            left += value
        share = silent / (visible + silent)
        ax.text(left + 6, i, f"{share:.0%} silent", va="center", fontsize=6.5, color=MUTED)
    ax.set_yticks(range(len(rows)), [r[0] for r in rows])
    ax.invert_yaxis()
    ax.set_xlim(0, 530)
    ax.set_xticks([0, 100, 200, 300, 400])
    ax.set_xlabel("Bugs (of 436)")
    ax.tick_params(axis="y", length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in (NEUTRAL, BLUE, ORANGE)]
    ax.legend(handles, ["Resolved", "Visible (gate sees)", "Silent (gate misses)"], loc="lower center",
              bbox_to_anchor=(0.45, 1.02), ncol=3, frameon=False, fontsize=6.3, handlelength=1, columnspacing=0.9)
    fig.tight_layout(pad=0.3)
    fig.savefig(HERE / "failure-modes.pdf")


def cost_panels(stats):
    """(a) Resolved rate against cost per bug for the Claude setups; (b) the reviewed cascade's cost model."""
    fig, (ax, bx) = plt.subplots(1, 2, figsize=(7.1, 1.85), gridspec_kw={"width_ratios": [1.1, 1], "wspace": 0.28})

    labels = {"haiku": "Haiku alone", "cascade": "Test-gated cascade", "reviewed": "Reviewed cascade",
              "sonnet": "Sonnet alone"}
    offsets = {"haiku": (6, -9), "cascade": (6, -9), "reviewed": (6, -10), "sonnet": (-6, 5)}
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    for key, label in labels.items():
        st = stats["setups"][key]
        x, y = st["cost_per_bug"] * 100, st["solved"]["rate"] * 100
        lo, hi = (v * 100 for v in st["solved"]["ci95"])
        ax.errorbar(x, y, yerr=[[y - lo], [hi - y]], fmt="o", color=BLUE, markersize=5, capsize=2, elinewidth=0.8,
                    markeredgecolor="white", markeredgewidth=0.8)
        ax.annotate(label, (x, y), textcoords="offset points", xytext=offsets[key], fontsize=6.5, color=INK,
                    ha="right" if key == "sonnet" else "left")
    h, c, r = (stats["setups"][k] for k in ("haiku", "cascade", "reviewed"))
    y_arrow = h["solved"]["ci95"][1] * 100 + 1.2
    ax.annotate("", xy=(c["cost_per_bug"] * 100, y_arrow), xytext=(h["cost_per_bug"] * 100, y_arrow),
                arrowprops={"arrowstyle": "->", "color": ORANGE, "linewidth": 1})
    ax.text((h["cost_per_bug"] + c["cost_per_bug"]) * 50, y_arrow + 0.6, "5.7x cost, +1 bug", ha="center",
            fontsize=6.5, color=MUTED)
    ax.annotate("", xy=(r["cost_per_bug"] * 100 - 0.1, r["solved"]["rate"] * 100 - 1.5),
                xytext=(c["cost_per_bug"] * 100 + 0.25, c["solved"]["rate"] * 100 + 1.5),
                arrowprops={"arrowstyle": "->", "color": BLUE, "linewidth": 1, "linestyle": (0, (3, 2))})
    ax.text(4.6, 76.2, "add a reviewer: +30 bugs", fontsize=6.5, color=MUTED, ha="center")
    ax.set_xlabel("Cost per bug (US cents)")
    ax.set_ylabel("Resolved (%)")
    ax.set_xlim(-0.2, 7.2)
    ax.set_ylim(70, 90)
    ax.set_title("(a) Accuracy and cost, 436 bugs", fontsize=7.5, color=INK, loc="left")

    m = stats["cost_model"]
    fixed = m["haiku_per_bug"] + m["review_per_bug"]
    rates = [i / 100 for i in range(0, 61)]
    bx.grid(axis="y", color=GRID, linewidth=0.6)
    bx.set_axisbelow(True)
    bx.plot([q * 100 for q in rates], [(fixed + q * m["redo_per_escalation"]) * 100 for q in rates], color=BLUE,
            linewidth=2, label="Reviewed cascade")
    bx.axhline(m["sonnet_per_bug"] * 100, color=MUTED, linewidth=1.2, linestyle="--", label="Sonnet alone")
    e, star = m["escalation_rate"], m["break_even_escalation_rate"]
    bx.plot([e * 100], [(fixed + e * m["redo_per_escalation"]) * 100], "o", color=ORANGE, markersize=6,
            markeredgecolor="white", markeredgewidth=1, zorder=3)
    bx.annotate(f"measured: {e:.0%}", (e * 100, (fixed + e * m["redo_per_escalation"]) * 100),
                textcoords="offset points", xytext=(5, -12), fontsize=6.5, color=INK)
    bx.axvline(star * 100, color=GRID, linewidth=1, zorder=0)
    bx.annotate(f"break-even {star:.0%}", (star * 100, 0.4), textcoords="offset points", xytext=(-3, 0),
                ha="right", fontsize=6.5, color=MUTED)
    bx.set_xlabel("Bugs escalated (%)")
    bx.set_ylabel("Cost per bug (cents)")
    bx.set_xlim(0, 60)
    bx.set_ylim(0, 9)
    bx.legend(frameon=False, fontsize=6.5, loc="upper left", handlelength=1.8)
    bx.set_title("(b) When the reviewed cascade is cheaper", fontsize=7.5, color=INK, loc="left")
    fig.subplots_adjust(left=0.065, right=0.99, bottom=0.2, top=0.88)
    fig.savefig(HERE / "cost.pdf")


if __name__ == "__main__":
    stats = json.loads(STATS.read_text())
    bugs, _ = load()
    failure_modes(bugs)
    cost_panels(stats)
    print("wrote", ", ".join(p.name for p in sorted(HERE.glob("*.pdf"))))
