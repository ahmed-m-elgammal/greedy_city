#!/usr/bin/env python3
"""validate_plan.py - checks plan.json against the planning rules.

Exit codes: 0 = all checks passed, 1 = one or more failures.

Usage:  python3 validate_plan.py [--plan plan.json]
Run from the repo root (GDD.md, game_model.json, test_results.json must exist).
"""
import argparse
import json
import os
import re
import sys

REQUIRED_TASK_FIELDS = [
    "id", "title", "milestone", "track", "type", "summary", "context_pack",
    "inputs", "outputs", "depends_on", "blocks", "size", "parallel_group",
    "acceptance_criteria", "tests", "definition_of_done", "risks",
    "ai_agent_failure_modes", "human_required", "human_reason",
]
REQUIRED_TEST_FIELDS = ["id", "kind", "command", "pass_criteria"]
SIZES = {"S", "M", "L"}

failures = []
warnings = []


def fail(msg):
    failures.append(msg)


def warn(msg):
    warnings.append(msg)


def check(condition, msg):
    if not condition:
        fail(msg)
    return condition


def load_plan(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: cannot parse {path}: {e}")
        sys.exit(2)


def gdd_sections(repo):
    heads = []
    with open(os.path.join(repo, "GDD.md"), encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^##\s+(.+?)\s*$", line)
            if m:
                heads.append(m.group(1))
    return heads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", default="plan.json")
    ap.add_argument("--repo", default=".", help="repo root containing GDD.md etc.")
    args = ap.parse_args()
    repo = os.path.abspath(args.repo)

    plan = load_plan(args.plan)

    # ---- section 0: top-level shape ------------------------------------
    for key in ("meta", "tech_stack", "principles", "milestones", "tasks",
                "critical_path", "coverage", "risk_register", "decisions_log",
                "open_assumptions"):
        check(key in plan, f"top-level key missing: {key}")
    if failures:
        report()
        sys.exit(1)

    meta = plan["meta"]
    for key in ("game", "version", "date", "planner_assumptions"):
        check(key in meta, f"meta.{key} missing")
    check(isinstance(meta.get("planner_assumptions"), list) and meta["planner_assumptions"],
          "meta.planner_assumptions must be a non-empty list")
    ts = plan["tech_stack"]
    for key in ("choice", "alternatives_considered", "why", "constraints"):
        check(key in ts, f"tech_stack.{key} missing")
    check(isinstance(ts.get("alternatives_considered"), list) and len(ts["alternatives_considered"]) >= 2,
          "tech_stack.alternatives_considered must compare at least two options")

    milestones = {m["id"]: m for m in plan["milestones"]}
    check(len(milestones) == len(plan["milestones"]), "duplicate milestone ids")
    tasks = plan["tasks"]
    by_id = {}
    for t in tasks:
        tid = t.get("id", "<no id>")
        check(tid not in by_id, f"duplicate task id: {tid}")
        by_id[tid] = t

    # ---- rule 1: task schema -------------------------------------------
    for t in tasks:
        tid = t.get("id", "<no id>")
        for field in REQUIRED_TASK_FIELDS:
            check(field in t, f"{tid}: missing required field '{field}'")
        check(t.get("size") in SIZES, f"{tid}: size must be one of {sorted(SIZES)}")
        check(bool(t.get("context_pack")), f"{tid}: context_pack empty")
        check(bool(t.get("outputs")), f"{tid}: outputs empty")
        check(bool(t.get("acceptance_criteria")), f"{tid}: acceptance_criteria empty")
        check(bool(t.get("definition_of_done")), f"{tid}: definition_of_done empty")
        check(bool(t.get("risks")), f"{tid}: risks empty")
        check(bool(t.get("ai_agent_failure_modes")), f"{tid}: ai_agent_failure_modes empty")
        check(isinstance(t.get("human_required"), bool), f"{tid}: human_required must be bool")
        if t.get("human_required"):
            check(bool(t.get("human_reason")), f"{tid}: human_required true but human_reason empty")

    # ---- rule 2: DAG, unknown ids, orphans ------------------------------
    for t in tasks:
        tid = t["id"]
        for dep in t.get("depends_on", []):
            check(dep in by_id, f"{tid}: depends_on unknown id '{dep}'")
            check(dep != tid, f"{tid}: depends on itself")
        for blk in t.get("blocks", []):
            check(blk in by_id, f"{tid}: blocks unknown id '{blk}'")
        check(t.get("milestone") in milestones, f"{tid}: unknown milestone '{t.get('milestone')}'")

    # blocks must equal reverse edges of depends_on
    for t in tasks:
        expected = sorted(o["id"] for o in tasks if t["id"] in o.get("depends_on", []))
        check(sorted(t.get("blocks", [])) == expected,
              f"{t['id']}: blocks != reverse edges of depends_on")

    # cycles (iterative DFS)
    color = {tid: 0 for tid in by_id}
    for root in by_id:
        if color[root]:
            continue
        stack = [(root, iter(by_id[root].get("depends_on", [])))]
        color[root] = 1
        path = [root]
        while stack:
            node, it = stack[-1]
            advanced = False
            for nxt in it:
                if nxt not in by_id:
                    continue
                if color[nxt] == 1:
                    cyc = path[path.index(nxt):] + [nxt]
                    fail("dependency cycle: " + " -> ".join(cyc))
                elif color[nxt] == 0:
                    color[nxt] = 1
                    stack.append((nxt, iter(by_id[nxt].get("depends_on", []))))
                    path.append(nxt)
                    advanced = True
                    break
            if not advanced:
                color[node] = 2
                stack.pop()
                path.pop()

    # orphans: every task in exactly one milestone.task_ids
    seen = {}
    for m in plan["milestones"]:
        for tid in m.get("task_ids", []):
            seen.setdefault(tid, []).append(m["id"])
            check(tid in by_id, f"milestone {m['id']}: task_ids references unknown task '{tid}'")
    for t in tasks:
        holders = seen.get(t["id"], [])
        check(len(holders) == 1, f"{t['id']}: orphan/ambiguous - listed in milestones {holders or ['NONE']}")
        if holders:
            check(holders[0] == t.get("milestone"),
                  f"{t['id']}: milestone field '{t.get('milestone')}' != containing milestone '{holders[0]}'")

    # ---- rule 3: every task has >=1 concrete test ------------------------
    for t in tasks:
        tid = t["id"]
        tests = t.get("tests", [])
        check(bool(tests), f"{tid}: no tests")
        for spec in tests:
            for field in REQUIRED_TEST_FIELDS:
                check(field in spec and str(spec[field]).strip(),
                      f"{tid}: test {spec.get('id', '?')} missing/empty '{field}'")
            check(str(spec.get("command", "")).strip() != "", f"{tid}: test without command")
            pc = str(spec.get("pass_criteria", ""))
            check(any(ch.isdigit() for ch in pc) or any(w in pc.lower() for w in
                  ("exit", "pass", "ok", "match", "green", "identical", "equal", "zero", "covers", "coverage", "complete", "signed", "nonzero", "no ")),
                  f"{tid}: test {spec.get('id')} pass_criteria is not concrete: '{pc}'")

    # ---- rule 4: size L needs justification ------------------------------
    for t in tasks:
        if t.get("size") == "L":
            check(bool(t.get("l_justification")),
                  f"{t['id']}: size L without l_justification")

    # ---- rule 5: GDD sections and model keys coverage --------------------
    cov = plan["coverage"]
    for key in ("gdd_sections", "model_keys", "sim_tests"):
        check(key in cov, f"coverage.{key} missing")

    sections = gdd_sections(repo)
    check(bool(sections), "could not parse any '##' sections from GDD.md")
    for s in sections:
        ids = cov["gdd_sections"].get(s)
        check(bool(ids), f"GDD section not covered: '{s}'")
        if ids:
            for i in ids:
                check(i in by_id, f"coverage.gdd_sections['{s}'] unknown task '{i}'")

    model_path = os.path.join(repo, "game_model.json")
    with open(model_path, encoding="utf-8") as f:
        mkeys = sorted(json.load(f).keys())
    for k in mkeys:
        ids = cov["model_keys"].get(k)
        check(bool(ids), f"game_model.json top-level key not covered: '{k}'")
        if ids:
            for i in ids:
                check(i in by_id, f"coverage.model_keys['{k}'] unknown task '{i}'")

    # ---- rule 6: named sim tests coverage ---------------------------------
    tr_path = os.path.join(repo, "test_results.json")
    with open(tr_path, encoding="utf-8") as f:
        tnames = sorted((k for k in json.load(f).keys() if re.match(r"^T\d+$", k)),
                        key=lambda s: int(s[1:]))
    for name in tnames:
        ids = cov["sim_tests"].get(name)
        check(bool(ids), f"test_results.json named test not covered: '{name}'")
        if ids:
            for i in ids:
                check(i in by_id, f"coverage.sim_tests['{name}'] unknown task '{i}'")

    # ---- rule 7: milestone exit gates -------------------------------------
    for m in plan["milestones"]:
        gate = m.get("exit_gate") or {}
        autos = gate.get("automated_checks") or []
        check(bool(autos), f"milestone {m['id']}: exit gate has no automated checks")
        for a in autos:
            check(bool(a.get("command")), f"milestone {m['id']}: automated check without command")
            check(bool(a.get("pass_criteria")), f"milestone {m['id']}: automated check without pass_criteria")
        check(bool(gate.get("human_playtest")), f"milestone {m['id']}: no human playtest checklist")
        check(bool(m.get("goal")) and bool(m.get("playable_outcome")),
              f"milestone {m['id']}: goal/playable_outcome missing")
        check(bool(m.get("entry_criteria")), f"milestone {m['id']}: entry_criteria empty")

    # ---- rule 8: critical path recomputed ---------------------------------
    def longest_from(tid):
        deps = by_id[tid].get("depends_on", [])
        best, best_len = None, 0
        for d in sorted(deps):
            if d not in by_id:
                continue
            path, ln = longest_from(d)
            if ln > best_len:
                best, best_len = path, ln
        return (best + [tid] if best else [tid], best_len + 1)

    sys.setrecursionlimit(100000)
    best, best_len = None, 0
    for tid in sorted(by_id):
        path, ln = longest_from(tid)
        if ln > best_len:
            best, best_len = path, ln
    printed_path = plan.get("critical_path")
    check(isinstance(printed_path, list) and bool(printed_path), "critical_path missing/empty")
    if printed_path:
        check(printed_path == best,
              f"critical_path mismatch:\n  plan:    {' -> '.join(printed_path)}\n  compute: {' -> '.join(best)}")
    print("CRITICAL PATH (length {}): {}".format(best_len, " -> ".join(best)))

    # ---- rule 9: outputs unique per task ----------------------------------
    owners = {}
    for t in tasks:
        for out in t.get("outputs", []):
            owners.setdefault(out, []).append(t["id"])
    for out, ids in sorted(owners.items()):
        if len(ids) > 1:
            fail(f"output '{out}' claimed by tasks {ids}; outputs must be unique to one task (D6)")

    # ---- rule 10: producer-directive pins (plan v1.1.0, 2026-11-26) --------
    # The producer's four inputs are requirements, not preferences: engine pin,
    # mobile-first platforms, data-driven mandate, and the two verified
    # simulation weaknesses must stay represented in the plan (D21-D24).
    check("4.7.2" in str(ts.get("choice", "")),
          "tech_stack.choice must pin Godot 4.7.2 (producer directive, D24)")
    cons_text = " ".join(str(c) for c in ts.get("constraints", []))
    check("iOS" in cons_text and "Android" in cons_text,
          "tech_stack.constraints must name the mobile-first platforms (iOS and Android, D14)")
    dids = {d.get("id") for d in plan["decisions_log"]}
    for did in ("D21", "D22", "D23", "D24"):
        check(did in dids, f"decisions_log missing producer-directive entry {did}")
    tids = {t["id"] for t in tasks}
    for tid in ("M7-T9", "M7-T10"):
        check(tid in tids, f"plan missing producer-directive task {tid}")
    m7_tids = set(next(m for m in plan["milestones"] if m["id"] == "M7").get("task_ids", []))
    for tid in ("M7-T9", "M7-T10"):
        check(tid in m7_tids, f"milestone M7 task_ids missing {tid}")
    blob = " ".join((t.get("title", "") + " " + t.get("summary", "")) for t in tasks)
    check("Android" in blob and "iOS" in blob,
          "plan must contain Android and iOS export/publish tasks (mobile-first, D14)")

    report()
    sys.exit(1 if failures else 0)


def report():
    if warnings:
        for w in warnings:
            print(f"WARNING: {w}")
    if failures:
        print(f"FAILED ({len(failures)}):")
        for f_ in failures:
            print(f"  - {f_}")
    else:
        print("ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
