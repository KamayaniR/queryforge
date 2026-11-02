"""Tables and figures from eval runs (CLAUDE.md 10.4) -> eval/summary.json, eval/figures/, eval/results.md.

Runs are named {setup}_test (frozen template+behavior set) and {setup}_hw (frozen hand-written set).
"Combined" merges both for each setup.
"""
import json
import sys
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from eval.run_eval import summarize  # noqa: E402
from eval.stats import compare_runs, load_run  # noqa: E402

CFG = yaml.safe_load(open(ROOT / "config.yaml"))
FIG = ROOT / CFG["paths"]["figures"]
SETUPS = ["S0", "S1", "S2", "S4", "S5", "S5H", "S6"]
HEADLINE_SETUP = "S4"  # recommended production setup (README findings)
# Model name first, setup code as a tag (codes match eval/runs/ and config.yaml).
LABELS = {"S0": "GLM 5.3 Flash, schema only (S0)", "S1": "GLM 5.3 Flash + dictionary, baseline (S1)",
          "S2": "Nemotron 3 Ultra + dictionary (S2)", "S4": "GLM 5.3 Flash + harness (S4)",
          "S5": "GLM 5.3 Flash fine-tuned (S5)", "S5H": "GLM 5.3 Flash fine-tuned + harness (S5H)",
          "S6": "GLM 5.3 Flash + harness → Nemotron 3 Ultra (S6)"}
CHART = {"S0": "GLM 5.3 Flash<br>schema only (S0)", "S1": "GLM 5.3 Flash<br>baseline (S1)",
         "S2": "Nemotron 3 Ultra<br>(S2)", "S4": "GLM 5.3 Flash<br>+ harness (S4)",
         "S5": "GLM 5.3 Flash<br>fine-tuned (S5)", "S5H": "GLM 5.3 Flash<br>fine-tuned + harness (S5H)",
         "S6": "Flash + harness<br>→ Ultra router (S6)"}
# Compact two-line labels for the 7-bar generalization chart, so neighbours don't overlap.
SHORT = {"S0": "Flash<br>schema only (S0)", "S1": "Flash<br>baseline (S1)", "S2": "Nemotron<br>Ultra (S2)",
         "S4": "Flash<br>+ harness (S4)", "S5": "Flash<br>fine-tuned (S5)", "S5H": "Flash FT<br>+ harness (S5H)",
         "S6": "Flash → Ultra<br>router (S6)"}
TAG = {"S0": "Flash, schema only", "S1": "Flash baseline", "S2": "Nemotron 3 Ultra", "S4": "Flash + harness",
       "S5": "Flash fine-tuned", "S5H": "Flash FT + harness", "S6": "Flash → Ultra router"}
CATS = ["simple", "join", "date", "business_rule", "gotcha", "clarify", "refuse"]
COLORS = {"real gain": "#2a9d8f", "real loss": "#e76f51", "could be luck": "#9aa5b1"}
ANSWER = lambda r: r["expected_action"] == "answer"  # noqa: E731


def runs_for(setup):
    ids = [f"{setup}_test", f"{setup}_hw"]
    return [i for i in ids if (ROOT / CFG["paths"]["runs"] / i / "results.jsonl").exists()]


def acc(rows, pred=lambda r: True):
    sel = [r["correct"] for r in rows if pred(r)]
    return float(np.mean(sel)) if sel else None


def setup_summary(setup):
    out = {}
    for name, ids in (("test", [f"{setup}_test"]), ("handwritten", [f"{setup}_hw"]), ("combined", runs_for(setup))):
        data = load_run(ids) if ids else None
        if not data:
            continue
        rows = list(data.values())
        s = summarize(rows)
        # Unrounded accuracies: every display rounds once, to 1 decimal (summarize() pre-rounds to 4 dp).
        s["exec_accuracy"] = acc(rows, ANSWER)
        s["behavior_accuracy"] = acc(rows, lambda r: not ANSWER(r))
        s["seen_acc"] = acc(rows, lambda r: r["seen_template"] is True)
        s["unseen_acc"] = acc(rows, lambda r: r["seen_template"] is False)
        s["by_category"] = {c: acc(rows, lambda r, c=c: r["category"] == c) for c in CATS}
        out[name] = s
    return out


def gap_pts(new, base):
    """Displayed gap = difference of the displayed (1-decimal) accuracies, so the numbers always add up."""
    return round(round(100 * new, 1) - round(100 * base, 1), 1)


def fmt(x, pct=True):
    return "-" if x is None else (f"{100 * x:.1f}%" if pct else f"{x}")


def save(fig, name, category_x=False):
    fig.update_layout(template="plotly_white", font=dict(size=14), margin=dict(l=60, r=30, t=70, b=60))
    if category_x:  # two-line model-name labels, kept horizontal
        fig.update_xaxes(tickangle=0, tickfont=dict(size=12))
    fig.write_image(FIG / f"{name}.png", width=1000, height=560, scale=2)


def main():
    FIG.mkdir(parents=True, exist_ok=True)
    present = [s for s in SETUPS if runs_for(s)]
    summ = {s: setup_summary(s) for s in present}
    stats = {}
    for s in present:
        if s == "S1":
            continue
        stats[s] = {
            "answer_combined": compare_runs(runs_for("S1"), runs_for(s), ANSWER),
            "answer_test": compare_runs(["S1_test"], [f"{s}_test"], ANSWER),
            "answer_seen": compare_runs(["S1_test"], [f"{s}_test"], lambda r: ANSWER(r) and r["seen_template"] is True),
            "answer_unseen": compare_runs(["S1_test"], [f"{s}_test"], lambda r: ANSWER(r) and r["seen_template"] is False),
            "answer_handwritten": compare_runs(["S1_hw"], [f"{s}_hw"], ANSWER),
            "behavior_test": compare_runs(["S1_test"], [f"{s}_test"], lambda r: not ANSWER(r)),
            "all_combined": compare_runs(runs_for("S1"), runs_for(s)),
        }
    if "S4" in present and "S2" in present:
        stats["S4_vs_S2"] = {
            "answer_combined": compare_runs(runs_for("S2"), runs_for("S4"), ANSWER),
            "answer_handwritten": compare_runs(["S2_hw"], ["S4_hw"], ANSWER),
            "behavior_test": compare_runs(["S2_test"], ["S4_test"], lambda r: not ANSWER(r)),
        }
    small = [s for s in present if s not in ("S1", "S2", "S0")]
    best = max(small, key=lambda s: summ[s]["combined"]["exec_accuracy"]) if small else None
    # Headline = the recommended production setup (S4), not simply the top combined score: S5 scores higher
    # on the frozen test but drops on hand-written questions (see README findings).
    head = HEADLINE_SETUP if HEADLINE_SETUP in present else best

    # 1. Headline table
    b, n = summ["S1"]["combined"], summ[head]["combined"] if head else None
    headline = [("Execution accuracy (answer items)", b["exec_accuracy"], n and n["exec_accuracy"], True),
                ("Hand-written questions (n = 30)", summ["S1"]["handwritten"]["exec_accuracy"],
                 summ[head].get("handwritten", {}).get("exec_accuracy"), True),
                ("Behavior accuracy (clarify/refuse)", b["behavior_accuracy"], n and n["behavior_accuracy"], True),
                ("Cost per 1k tickets (USD)", b["cost_per_1k"], n and n["cost_per_1k"], False),
                ("p50 latency (ms)", b["p50_latency_ms"], n and n["p50_latency_ms"], False)]
    md = [f"### Headline: {LABELS[head]} vs {LABELS['S1']} (combined test + hand-written)\n",
          f"| Metric | {LABELS['S1']} | {LABELS[head]} | Gain |", "|---|---|---|---|"]
    for name, x, y, pct in headline:
        gain = None if y is None or x is None else (gap_pts(y, x) if pct else y - x)
        g = "-" if gain is None else (f"{gain:+.1f} pts" if pct else f"{gain:+.3f}" if isinstance(gain, float) else f"{gain:+d}")
        md.append(f"| {name} | {fmt(x, pct)} | {fmt(y, pct)} | {g} |")
    st = stats[head]["answer_combined"]
    md.append(f"\nAccuracy gap {gap_pts(st['new_acc'], st['base_acc']):+.1f} pts, 95% cluster-bootstrap CI [{100 * st['ci95'][0]:+.1f}, "
              f"{100 * st['ci95'][1]:+.1f}], McNemar p = {st['p_value']:.4f} ({st['only_new_right']} items only {head} "
              f"got right vs {st['only_base_right']} only S1 got right) -> **{st['verdict']}**.\n")
    if best and best != head:
        v = stats[best]["answer_combined"]
        md.append(f"{LABELS[best]} has the highest combined score ({fmt(summ[best]['combined']['exec_accuracy'])}, "
                  f"{gap_pts(v['new_acc'], v['base_acc']):+.1f} pts vs S1), but drops on the hand-written questions "
                  f"({fmt(summ[best].get('handwritten', {}).get('exec_accuracy'))} vs "
                  f"{fmt(summ['S1']['handwritten']['exec_accuracy'])}), so it is not the headline. See the findings below.\n")

    # Summary table
    md += ["### All setups\n",
           "| Setup | Items run (test / hw) | Test acc | Hand-written acc | Combined acc | Seen tmpl | Unseen tmpl | Behavior | p50 ms | $/1k tickets | vs S1, paired on same answer items |",
           "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in present:
        c, t, h = summ[s].get("combined", {}), summ[s].get("test", {}), summ[s].get("handwritten", {})
        v = stats.get(s, {}).get("answer_combined")
        vs = "baseline" if s == "S1" else (f"{gap_pts(v['new_acc'], v['base_acc']):+.1f} pts, p={v['p_value']:.3f}, {v['verdict']} (n={v['n']})" if v else "-")
        md.append(f"| {LABELS[s]} | {t.get('n', 0)} / {h.get('n', 0)} | {fmt(t.get('exec_accuracy'))} | {fmt(h.get('exec_accuracy'))} | "
                  f"{fmt(c.get('exec_accuracy'))} | {fmt(c.get('seen_acc'))} | {fmt(c.get('unseen_acc'))} | {fmt(c.get('behavior_accuracy'))} | "
                  f"{c.get('p50_latency_ms')} | {c.get('cost_per_1k'):.3f} | {vs} |")

    # Paired comparisons vs S1 on exactly the same items, by slice
    def cell(v):
        if not v:
            return "-"
        return (f"{100 * v['base_acc']:.1f} → {100 * v['new_acc']:.1f} ({gap_pts(v['new_acc'], v['base_acc']):+.1f}; "
                f"{v['only_new_right']}/{v['only_base_right']}; p={v['p_value']:.3g}; {v['verdict']}) n={v['n']}")
    md += ["\n### Paired vs S1 on the same items (S1 acc → setup acc (gap; only-setup-right/only-S1-right; McNemar p; verdict) n)\n",
           "| Setup | Seen templates | Held-out templates | Hand-written | Behavior (clarify/refuse) |", "|---|---|---|---|---|"]
    for s in [x for x in present if x != "S1"]:
        v = stats[s]
        md.append(f"| {LABELS[s]} | {cell(v['answer_seen'])} | {cell(v['answer_unseen'])} | {cell(v['answer_handwritten'])} | {cell(v['behavior_test'])} |")
    if "S4_vs_S2" in stats:
        v = stats["S4_vs_S2"]
        md += ["\n### S4 vs S2 (Nemotron Ultra), paired (S2 acc → S4 acc)\n",
               "| Slice | Result |", "|---|---|",
               f"| Answer items, test + hand-written | {cell(v['answer_combined'])} |",
               f"| Hand-written only | {cell(v['answer_handwritten'])} |",
               f"| Behavior (clarify/refuse) | {cell(v['behavior_test'])} |"]

    # 6. Category table
    md += ["\n### Accuracy by category (combined)\n", "| Setup | " + " | ".join(CATS) + " |", "|---|" + "---|" * len(CATS)]
    for s in present:
        bc = summ[s]["combined"]["by_category"]
        md.append(f"| {LABELS[s]} | " + " | ".join(fmt(bc[c]) for c in CATS) + " |")
    (ROOT / "eval" / "results.md").write_text("\n".join(md) + "\n")

    # 2. Ladder chart
    order = [s for s in ["S0", "S1", "S4", "S5", "S5H", "S6"] if s in present]
    fig = go.Figure(go.Bar(x=[CHART[s] for s in order], y=[100 * summ[s]["combined"]["exec_accuracy"] for s in order],
                           text=[f"{100 * summ[s]['combined']['exec_accuracy']:.1f}%" for s in order], textposition="outside",
                           marker_color=["#9aa5b1" if s in ("S0", "S1") else "#2a9d8f" for s in order]))
    if "S2" in present:
        y2 = 100 * summ["S2"]["combined"]["exec_accuracy"]
        fig.add_hline(y=y2, line_dash="dash", line_color="#264653",
                      annotation_text=f"Nemotron 3 Ultra, large model (S2) {y2:.1f}%", annotation_position="bottom left")
    fig.update_layout(title="Execution accuracy by setup (test + hand-written, answer items)",
                      yaxis=dict(title="accuracy (%)", range=[0, 105]))
    save(fig, "ladder", category_x=True)

    # 3. Significance chart
    comp = [s for s in ["S0", "S2", "S4", "S5", "S5H", "S6"] if s in stats and stats[s]["answer_combined"]]
    fig = go.Figure()
    new_right = [stats[s]["answer_combined"]["only_new_right"] for s in comp]
    base_right = [stats[s]["answer_combined"]["only_base_right"] for s in comp]
    fig.add_bar(name="only this setup right", x=[CHART[s] for s in comp], y=new_right, marker_color="#2a9d8f",
                text=new_right, textposition="outside", cliponaxis=False)
    fig.add_bar(name="only the baseline right", x=[CHART[s] for s in comp], y=base_right, marker_color="#e76f51",
                text=base_right, textposition="outside", cliponaxis=False)
    top = max(new_right + base_right)
    for s, a, b_ in zip(comp, new_right, base_right):
        v = stats[s]["answer_combined"]
        # Verdict sits above both bars and their value labels, anchored at its bottom so it never overlaps them.
        fig.add_annotation(x=CHART[s], y=max(a, b_), yanchor="bottom", yshift=26, showarrow=False,
                           text=f"<b>{v['verdict']}</b><br>p = {v['p_value']:.2g}", font=dict(size=12))
    fig.update_layout(title="Disagreements with the baseline, GLM 5.3 Flash (S1) — McNemar", barmode="group",
                      yaxis=dict(title="items", range=[0, top * 1.35]),
                      legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0))
    save(fig, "significance", category_x=True)

    # 4. Interval chart
    fig = go.Figure()
    for s in comp:
        v = stats[s]["answer_combined"]
        fig.add_trace(go.Scatter(x=[100 * v["gap"]], y=[LABELS[s]], mode="markers", marker=dict(size=14, color=COLORS[v["verdict"]]),
                                 error_x=dict(type="data", symmetric=False, array=[100 * (v["ci95"][1] - v["gap"])],
                                              arrayminus=[100 * (v["gap"] - v["ci95"][0])]), showlegend=False))
    fig.add_vline(x=0, line_color="#264653")
    fig.update_layout(title="Accuracy gap vs the baseline (GLM 5.3 Flash, S1), 95% cluster-bootstrap interval",
                      xaxis_title="gap (percentage points)")
    save(fig, "intervals")

    # 5. Tradeoff chart
    fig = go.Figure()
    pos = {"S0": "top center", "S1": "bottom center", "S2": "top center", "S4": "top center", "S5": "top center",
           "S5H": "top center", "S6": "bottom right"}
    for s in present:
        c = summ[s]["combined"]
        fig.add_trace(go.Scatter(x=[c["cost_per_1k"]], y=[100 * c["exec_accuracy"]], mode="markers+text",
                                 text=[f"{TAG[s]} ({s})"], textposition=pos.get(s, "top center"),
                                 marker=dict(size=16, color="#2a9d8f" if s in ("S4", "S5", "S5H", "S6") else "#9aa5b1"
                                             if s in ("S0", "S1") else "#264653"), name=LABELS[s], showlegend=False))
    fig.update_layout(title="Quality vs cost (green = QueryForge setups, gray = GLM baselines)",
                      xaxis=dict(title="USD per 1,000 tickets (log)", type="log", range=[-0.75, 0.6],
                                 tickvals=[0.2, 0.5, 1, 2], ticktext=["$0.20", "$0.50", "$1", "$2"]),
                      yaxis=dict(title="execution accuracy (%)", range=[45, 102]))
    save(fig, "tradeoff")

    # Seen vs unseen templates
    fig = go.Figure()
    xs = [SHORT[s] for s in order]
    fig.add_bar(name="seen templates", x=xs, y=[100 * (summ[s]["combined"]["seen_acc"] or 0) for s in order])
    fig.add_bar(name="held-out templates", x=xs, y=[100 * (summ[s]["combined"]["unseen_acc"] or 0) for s in order])
    fig.add_bar(name="hand-written", x=xs, y=[100 * (summ[s].get("handwritten", {}).get("exec_accuracy") or 0) for s in order])
    fig.update_layout(title="Generalization: seen vs held-out templates vs hand-written", barmode="group",
                      yaxis=dict(title="accuracy (%)", range=[0, 105]))
    save(fig, "seen_unseen", category_x=True)

    json.dump({"best_setup": best, "headline_setup": head, "summaries": summ, "stats_vs_S1": stats}, open(ROOT / "eval" / "summary.json", "w"), indent=1)
    readme = ROOT / "README.md"
    if readme.exists():
        text = readme.read_text()
        start, end = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"
        if start in text and end in text:
            head, rest = text.split(start, 1)
            readme.write_text(head + start + "\n" + "\n".join(md) + "\n" + end + rest.split(end, 1)[1])
    print("\n".join(md))


if __name__ == "__main__":
    main()
