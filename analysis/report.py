"""Summarize harness-lab runs from Harbor job directories.

    uv run --extra analysis python analysis/report.py jobs/exp-* --out results/local-qwen3-8b

Writes to --out:
  trials.csv, calls.csv      one row per task attempt / per model call
  summary.md                 per-variant table (also the table view for every chart)
  *.png, *-dark.png          charts for the README, light and dark
"""

import argparse
import json
import math
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.path import Path as MplPath  # noqa: E402
from matplotlib.patches import PathPatch  # noqa: E402

BASELINE = "full"
VARIANT_ORDER = ["full", "truncate", "rolling", "compaction", "bash-only", "reasoning"]

# --------------------------------------------------------------------------- loading


def load(job_dirs: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    trials, calls = [], []
    for job in job_dirs:
        for result_path in sorted(job.glob("*/result.json")):
            trace_path = result_path.parent / "agent" / "harness_trace.jsonl"
            if not trace_path.exists():
                continue
            result = json.loads(result_path.read_text())
            records = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
            start = records[0]
            end = next((r for r in reversed(records) if r["type"] == "run_end"), {})
            llm = [r for r in records if r["type"] == "llm_call"]
            rewards = (result.get("verifier_result") or {}).get("rewards") or {}
            trial = {
                "job": job.name,
                "trial": result["trial_name"],
                "task": result["task_name"],
                "variant": start["config"]["variant"],
                "model": start.get("model"),
                "reward": float(rewards.get("reward", 0.0)),
                "exception": result.get("exception_info") is not None,
                "stop_reason": end.get("stop_reason", "incomplete"),
                "steps": end.get("steps"),
                "llm_calls": len(llm),
                "prompt_tokens": sum(r["prompt_tokens"] or 0 for r in llm),
                "cached_tokens": sum(r["cached_tokens"] or 0 for r in llm),
                "prefill_computed": sum(r["prefill_tokens_computed"] or 0 for r in llm),
                "completion_tokens": sum(r["completion_tokens"] or 0 for r in llm),
                "prefill_s": sum(_prefill_ms(r) for r in llm) / 1000,
                "decode_s": sum(max(0.0, r["e2e_ms"] - _prefill_ms(r)) for r in llm) / 1000,
                "tool_s": sum(r["duration_ms"] for r in records if r["type"] == "tool_call") / 1000,
                "compactions": end.get("compactions", 0),
                "format_errors": end.get("format_errors", 0),
                "tool_errors": end.get("tool_errors", 0),
                "agent_wall_s": _seconds(result.get("agent_execution")),
            }
            trials.append(trial)
            for r in llm:
                calls.append({"trial": trial["trial"], "task": trial["task"], "variant": trial["variant"], **r})
    return pd.DataFrame(trials), pd.DataFrame(calls)


def _prefill_ms(call: dict) -> float:
    if call.get("server_prompt_ms") is not None:
        return call["server_prompt_ms"]
    return call.get("ttft_ms") or 0.0


def _seconds(span: dict | None) -> float | None:
    if not span or not span.get("started_at") or not span.get("finished_at"):
        return None
    start = pd.Timestamp(span["started_at"])
    return (pd.Timestamp(span["finished_at"]) - start).total_seconds()


# --------------------------------------------------------------------------- statistics


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (center - half, center + half)


def paired_bootstrap(trials: pd.DataFrame, variant: str, n_boot: int = 10_000, seed: int = 0):
    """Mean per-task reward difference (variant - baseline) with a bootstrap CI over tasks."""
    per_task = trials.pivot_table(index="task", columns="variant", values="reward", aggfunc="mean")
    if BASELINE not in per_task or variant not in per_task:
        return None
    diffs = (per_task[variant] - per_task[BASELINE]).dropna().tolist()
    if not diffs:
        return None
    rng = random.Random(seed)
    means = sorted(sum(rng.choices(diffs, k=len(diffs))) / len(diffs) for _ in range(n_boot))
    return sum(diffs) / len(diffs), means[int(0.025 * n_boot)], means[int(0.975 * n_boot)], len(diffs)


def ordered_variants(trials: pd.DataFrame) -> list[str]:
    present = list(trials["variant"].unique())
    return [v for v in VARIANT_ORDER if v in present] + sorted(v for v in present if v not in VARIANT_ORDER)


def summarize(trials: pd.DataFrame, calls: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for variant in ordered_variants(trials):
        t = trials[trials.variant == variant]
        c = calls[(calls.variant == variant) & (calls.kind == "agent")]
        passed = int((t.reward >= 1).sum())
        lo, hi = wilson(passed, len(t))
        rows.append(
            {
                "variant": variant,
                "attempts": len(t),
                "passed": passed,
                "pass_rate": passed / len(t),
                "ci_low": lo,
                "ci_high": hi,
                "median_steps": t.steps.median(),
                "prompt_tokens_per_task": t.prompt_tokens.mean(),
                "prefill_computed_per_task": t.prefill_computed.mean(),
                "cache_hit_rate": t.cached_tokens.sum() / max(1, t.prompt_tokens.sum()),
                "output_tokens_per_task": t.completion_tokens.mean(),
                "ttft_p50_s": c.ttft_ms.quantile(0.5) / 1000,
                "ttft_p90_s": c.ttft_ms.quantile(0.9) / 1000,
                "decode_ms_per_token": c.server_decode_ms_per_token.median(),
                "median_task_wall_s": t.agent_wall_s.median(),
                "compactions_per_task": t.compactions.mean(),
            }
        )
    return pd.DataFrame(rows)


def write_markdown(summary: pd.DataFrame, trials: pd.DataFrame, path: Path) -> None:
    lines = [
        "| Variant | Pass rate (95% CI) | Median steps | Prompt tok / task | Prefill computed / task "
        "| Cache hit | Output tok / task | TTFT p50 / p90 | Median task time |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in summary.itertuples():
        lines.append(
            f"| {r.variant} | {r.passed}/{r.attempts} = {r.pass_rate:.0%} ({r.ci_low:.0%}–{r.ci_high:.0%}) "
            f"| {r.median_steps:.0f} | {r.prompt_tokens_per_task:,.0f} | {r.prefill_computed_per_task:,.0f} "
            f"| {r.cache_hit_rate:.0%} | {r.output_tokens_per_task:,.0f} "
            f"| {r.ttft_p50_s:.1f} s / {r.ttft_p90_s:.1f} s | {r.median_task_wall_s:.0f} s |"
        )
    lines += ["", f"Paired difference in pass rate vs `{BASELINE}` (same tasks; bootstrap 95% CI over tasks):", ""]
    for variant in ordered_variants(trials):
        if variant == BASELINE:
            continue
        res = paired_bootstrap(trials, variant)
        if res:
            mean, lo, hi, n = res
            lines.append(f"- `{variant}`: {mean:+.0%} ({lo:+.0%} to {hi:+.0%}), {n} tasks")
    stops = trials.groupby(["variant", "stop_reason"]).size().unstack(fill_value=0)
    lines += ["", "Stop reasons:", "", stops.to_markdown()]
    path.write_text("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- charts
# Colors from the validated reference palette (light / dark). Rendered at 2x: 1 css px = 2 image px.

THEMES = {
    "light": {
        "surface": "#fcfcfb",
        "primary": "#0b0b0b",
        "secondary": "#52514e",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "axis": "#c3c2b7",
        "series": ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"],
    },
    "dark": {
        "surface": "#1a1a19",
        "primary": "#ffffff",
        "secondary": "#c3c2b7",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "axis": "#383835",
        "series": ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"],
    },
}
DPI = 200
PX = 72 / 100  # one css px in points at 2x

plt.rcParams.update(
    {
        "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"],
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.titleweight": "bold",
    }
)


def variant_color(theme: dict, variant: str) -> str:
    """Color follows the variant, never its rank among the variants present."""
    index = VARIANT_ORDER.index(variant) if variant in VARIANT_ORDER else len(VARIANT_ORDER) - 1
    return theme["series"][index % len(theme["series"])]


def new_figure(theme: dict, width_in: float, height_in: float, ncols: int = 1):
    fig, axes = plt.subplots(1, ncols, figsize=(width_in, height_in), dpi=DPI, squeeze=False)
    fig.patch.set_facecolor(theme["surface"])
    for ax in axes[0]:
        ax.set_facecolor(theme["surface"])
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(theme["axis"])
            ax.spines[side].set_linewidth(1 * PX)
        ax.tick_params(colors=theme["muted"], labelcolor=theme["secondary"], width=1 * PX, length=3)
        ax.title.set_color(theme["primary"])
        ax.xaxis.label.set_color(theme["secondary"])
        ax.yaxis.label.set_color(theme["secondary"])
    return fig, axes[0]


def grid(ax, theme: dict, axis: str) -> None:
    ax.grid(axis=axis, color=theme["grid"], linewidth=1 * PX, linestyle="-")
    ax.set_axisbelow(True)


def px_to_data(ax, px: float) -> tuple[float, float]:
    box = ax.get_window_extent()
    x0, x1 = ax.get_xlim()
    y0, y1 = ax.get_ylim()
    scale = 2 * px  # css px -> image px
    return abs(x1 - x0) / box.width * scale, abs(y1 - y0) / box.height * scale


def rounded_hbar(ax, y: float, left: float, width: float, height: float, color: str, radius_px: float = 4):
    """Horizontal bar, square at the baseline, rounded at the data end."""
    if width <= 0:
        return
    rx, ry = px_to_data(ax, radius_px)
    rx, ry = min(rx, width), min(ry, height / 2)
    x0, x1, yb, yt = left, left + width, y - height / 2, y + height / 2
    verts = [(x0, yb), (x1 - rx, yb), (x1, yb), (x1, yb + ry), (x1, yt - ry), (x1, yt), (x1 - rx, yt), (x0, yt), (x0, yb)]
    codes = [MplPath.MOVETO, MplPath.LINETO, MplPath.CURVE3, MplPath.CURVE3, MplPath.LINETO,
             MplPath.CURVE3, MplPath.CURVE3, MplPath.LINETO, MplPath.CLOSEPOLY]
    ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=color, edgecolor="none", zorder=2))


def bar_height(ax, n_bars: int, max_px: float = 24) -> float:
    """Bar thickness in data units: at most 24 css px, and at most 60% of the band."""
    _, per_px = px_to_data(ax, 1)
    return min(0.6, max_px * per_px)


def legend(ax, theme: dict, handles, labels, ncol: int) -> None:
    leg = ax.legend(handles, labels, loc="lower left", bbox_to_anchor=(0, 1.02), ncol=ncol, frameon=False,
                    handlelength=1.2, columnspacing=1.4, borderaxespad=0)
    for text in leg.get_texts():
        text.set_color(theme["secondary"])


def swatch(color: str):
    return plt.Rectangle((0, 0), 1, 1, facecolor=color, edgecolor="none")


def save(fig, out: Path, name: str, mode: str) -> None:
    suffix = "" if mode == "light" else "-dark"
    fig.savefig(out / f"{name}{suffix}.png", facecolor=fig.get_facecolor())
    plt.close(fig)


def chart_pass_rate(summary: pd.DataFrame, theme: dict, out: Path, mode: str) -> None:
    n = len(summary)
    height = 0.9 + 0.45 * n
    fig, (ax,) = new_figure(theme, 7, height)
    fig.subplots_adjust(left=0.16, right=0.93, top=1 - 0.55 / height, bottom=0.4 / height)
    ax.set_xlim(0, 1)
    ax.set_ylim(n - 0.5, -0.5)
    grid(ax, theme, "x")
    h = bar_height(ax, n)
    for i, r in enumerate(summary.itertuples()):
        rounded_hbar(ax, i, 0, r.pass_rate, h, theme["series"][0])
        ax.plot([r.ci_low, r.ci_high], [i, i], color=theme["primary"], linewidth=1 * PX, zorder=3)
        for x in (r.ci_low, r.ci_high):
            ax.plot([x, x], [i - h / 4, i + h / 4], color=theme["primary"], linewidth=1 * PX, zorder=3)
        label_x = max(r.pass_rate, r.ci_high) + 0.015
        ax.text(label_x, i, f"{r.pass_rate:.0%}  ({r.passed}/{r.attempts})", va="center",
                color=theme["secondary"], fontsize=8)
    ax.set_yticks(range(n), summary.variant)
    ax.xaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    ax.set_title("Task pass rate by harness variant (whiskers: 95% Wilson CI)", loc="left", pad=10)
    save(fig, out, "pass_rate", mode)


def chart_context_growth(calls: pd.DataFrame, variants: list[str], theme: dict, out: Path, mode: str) -> None:
    agent = calls[calls.kind == "agent"]
    fig, (ax,) = new_figure(theme, 7, 3.6)
    fig.subplots_adjust(left=0.11, right=0.97, top=0.8, bottom=0.14)
    grid(ax, theme, "y")
    handles = []
    for v in variants:
        med = agent[agent.variant == v].groupby("step").prompt_tokens.median()
        if med.empty:
            continue
        color = variant_color(theme, v)
        (line,) = ax.plot(med.index, med.values, color=color, linewidth=2 * PX, solid_capstyle="round",
                          solid_joinstyle="round", zorder=2)
        ax.plot(med.index[-1:], med.values[-1:], "o", color=color, markersize=8 * PX,
                markeredgecolor=theme["surface"], markeredgewidth=2 * PX, zorder=3)
        handles.append((line, v))
    ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
    ax.set_xlabel("Agent step")
    ax.set_ylabel("Prompt tokens (median)")
    legend(ax, theme, [h for h, _ in handles], [v for _, v in handles], ncol=len(handles))
    ax.set_title("How the prompt grows each step", loc="left", pad=28)
    save(fig, out, "context_growth", mode)


def chart_ttft(calls: pd.DataFrame, theme: dict, out: Path, mode: str) -> None:
    agent = calls[(calls.kind == "agent") & calls.ttft_ms.notna()]
    fig, axes = new_figure(theme, 7, 3.2, ncols=2)
    fig.subplots_adjust(left=0.09, right=0.98, top=0.78, bottom=0.16, wspace=0.25)
    panels = [("prompt_tokens", "Total prompt tokens"), ("prefill_tokens_computed", "Prompt tokens actually computed")]
    for ax, (column, xlabel) in zip(axes, panels):
        grid(ax, theme, "both")
        ax.scatter(agent[column], agent.ttft_ms / 1000, s=(8 * PX) ** 2, color=theme["series"][0],
                   edgecolors=theme["surface"], linewidths=2 * PX, alpha=0.85, zorder=2)
        ax.set_xlabel(xlabel)
        ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: f"{x:,.0f}"))
        ax.set_xlim(left=0)
        ax.set_ylim(bottom=0)
    axes[0].set_ylabel("Time to first token (s)")
    fig.suptitle("TTFT follows the tokens the server must compute, not the prompt size",
                 x=0.09, ha="left", y=0.95, color=theme["primary"], fontsize=10, fontweight="bold")
    save(fig, out, "ttft_vs_tokens", mode)


def chart_stacked(summary_rows: list[tuple[str, list[float]]], segments: list[str], title: str, unit_fmt,
                  theme: dict, out: Path, name: str, mode: str) -> None:
    n = len(summary_rows)
    height = 1.2 + 0.45 * n
    fig, (ax,) = new_figure(theme, 7, height)
    fig.subplots_adjust(left=0.16, right=0.9, top=1 - 0.85 / height, bottom=0.4 / height)
    xmax = max(sum(vals) for _, vals in summary_rows) * 1.18 or 1
    ax.set_xlim(0, xmax)
    ax.set_ylim(n - 0.5, -0.5)
    grid(ax, theme, "x")
    h = bar_height(ax, n)
    gap_x, _ = px_to_data(ax, 2)
    for i, (_, vals) in enumerate(summary_rows):
        left = 0.0
        last = max((k for k, v in enumerate(vals) if v > 0), default=-1)
        for k, v in enumerate(vals):
            if v <= 0:
                continue
            if k == last:
                rounded_hbar(ax, i, left, v, h, theme["series"][k])
            else:
                ax.add_patch(plt.Rectangle((left, i - h / 2), max(0, v - gap_x), h,
                                           facecolor=theme["series"][k], edgecolor="none", zorder=2))
            left += v
        ax.text(left + xmax * 0.01, i, unit_fmt(left), va="center", color=theme["secondary"], fontsize=8)
    ax.set_yticks(range(n), [label for label, _ in summary_rows])
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda x, _: unit_fmt(x)))
    legend(ax, theme, [swatch(theme["series"][k]) for k in range(len(segments))], segments, ncol=len(segments))
    ax.set_title(title, loc="left", pad=26)
    save(fig, out, name, mode)


def render_charts(trials: pd.DataFrame, calls: pd.DataFrame, summary: pd.DataFrame, out: Path) -> None:
    variants = ordered_variants(trials)
    means = trials.groupby("variant")[["prefill_s", "decode_s", "tool_s", "prefill_computed", "cached_tokens"]].mean()
    time_rows = [(v, [means.at[v, "prefill_s"], means.at[v, "decode_s"], means.at[v, "tool_s"]]) for v in variants]
    token_rows = [(v, [means.at[v, "prefill_computed"], means.at[v, "cached_tokens"]]) for v in variants]
    for mode, theme in THEMES.items():
        chart_pass_rate(summary, theme, out, mode)
        chart_context_growth(calls, variants, theme, out, mode)
        chart_ttft(calls, theme, out, mode)
        chart_stacked(time_rows, ["Prefill (model reads prompt)", "Decode (model writes)", "Tool execution"],
                      "Where the time goes: mean seconds per task", lambda x: f"{x:,.0f} s",
                      theme, out, "time_breakdown", mode)
        chart_stacked(token_rows, ["Prompt tokens computed", "Prompt tokens served from cache"],
                      "Prefill work per task: computed vs. cached prompt tokens", lambda x: f"{x / 1000:,.0f}k",
                      theme, out, "prefill_work", mode)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("jobs", nargs="+", type=Path, help="Harbor job directories")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--no-charts", action="store_true")
    args = parser.parse_args()

    trials, calls = load(args.jobs)
    if trials.empty:
        raise SystemExit("No harness-lab trials found in the given job directories.")
    args.out.mkdir(parents=True, exist_ok=True)
    trials.to_csv(args.out / "trials.csv", index=False)
    calls.to_csv(args.out / "calls.csv", index=False)
    summary = summarize(trials, calls)
    write_markdown(summary, trials, args.out / "summary.md")
    if not args.no_charts:
        render_charts(trials, calls, summary, args.out)
    print((args.out / "summary.md").read_text())


if __name__ == "__main__":
    main()
