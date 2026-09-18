"""Charts and a summary table for a vLLM replay run (results from harness_lab.replay).

    uv run --extra analysis python analysis/replay_report.py results/replay-kaggle-t4

Expects <dir>/<config>/levels.json for each server config (prefix-cache-on, prefix-cache-off).
"""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from report import PX, THEMES, grid, new_figure, save  # noqa: E402

CONFIG_ORDER = ["prefix-cache-on", "prefix-cache-off"]
CONFIG_LABEL = {"prefix-cache-on": "Prefix caching on", "prefix-cache-off": "Prefix caching off"}


def load(root: Path) -> list[dict]:
    levels = []
    for config in CONFIG_ORDER:
        path = root / config / "levels.json"
        if path.exists():
            for level in json.loads(path.read_text()):
                level["config"] = config
                level["variant"] = level["label"].split("/", 1)[-1]
                levels.append(level)
    return levels


def chart(levels: list[dict], metric: str, ylabel: str, title: str, log: bool, out: Path, name: str) -> None:
    variants = list(dict.fromkeys(lv["variant"] for lv in levels))
    for mode, theme in THEMES.items():
        fig, axes = new_figure(theme, 7, 3.3, ncols=len(variants))
        fig.subplots_adjust(left=0.1, right=0.98, top=0.7, bottom=0.17, wspace=0.28)
        handles = {}
        for ax, variant in zip(axes, variants):
            grid(ax, theme, "y")
            for k, config in enumerate(CONFIG_ORDER):
                pts = sorted((lv["concurrency"], lv[metric]) for lv in levels
                             if lv["variant"] == variant and lv["config"] == config and lv[metric] is not None)
                if not pts:
                    continue
                xs, ys = zip(*pts)
                (line,) = ax.plot(xs, ys, color=theme["series"][k], linewidth=2 * PX, marker="o",
                                  markersize=8 * PX, markeredgecolor=theme["surface"], markeredgewidth=2 * PX,
                                  solid_capstyle="round", zorder=2)
                handles[config] = line
            if log:
                ax.set_yscale("log")
                ax.yaxis.set_major_locator(matplotlib.ticker.LogLocator(base=10, subs=(1, 2, 5), numticks=12))
                ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
                ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:,.0f}"))
            ax.set_xscale("log", base=2)
            ax.xaxis.set_major_formatter(matplotlib.ticker.ScalarFormatter())
            ax.set_xticks(sorted({lv["concurrency"] for lv in levels}))
            ax.set_title(variant, loc="left", color=theme["primary"], fontsize=9, pad=8)
            ax.set_xlabel("Concurrent agent sessions")
        # One shared scale across panels, so the panels can be compared directly.
        values = [lv[metric] for lv in levels if lv[metric] is not None]
        if values:
            low, high = min(values), max(values)
            for ax in axes:
                ax.set_ylim(low * 0.7 if log else 0, high * 1.3)
        for ax in axes[1:]:
            ax.tick_params(labelleft=False)
        axes[0].set_ylabel(ylabel)
        leg = fig.legend([handles[c] for c in CONFIG_ORDER if c in handles],
                         [CONFIG_LABEL[c] for c in CONFIG_ORDER if c in handles],
                         loc="upper left", bbox_to_anchor=(0.1, 0.87), ncol=2, frameon=False)
        for text in leg.get_texts():
            text.set_color(theme["secondary"])
        fig.suptitle(title, x=0.1, ha="left", y=0.96, color=theme["primary"], fontsize=10, fontweight="bold")
        save(fig, out, name, mode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    levels = load(args.root)
    if not levels:
        raise SystemExit(f"No levels.json under {args.root}")
    chart(levels, "ttft_p50_ms", "TTFT p50 (ms, log scale)",
          "Replayed agent sessions on vLLM: median time to first token", True, args.root, "replay_ttft")
    chart(levels, "output_tokens_per_s", "Output tokens / s",
          "Replayed agent sessions on vLLM: output throughput", False, args.root, "replay_throughput")
    print(f"Wrote charts to {args.root}")


if __name__ == "__main__":
    main()
