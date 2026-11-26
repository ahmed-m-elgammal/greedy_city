# Gaps Report — adversarial review of plan.json (Small Wants build plan)

**Reviewer stance:** a different executing agent, given only `plan.json`, `docs/AGENT_GUIDE.md`
(which does not exist until M0-T9 lands), and the repo. I simulated executing the first
10 tasks (M0-T1 … M0-T9, M1-T1) one session each, with no memory, exactly as written.
Every issue below was either **patched into plan.json** (noted with the fix) or is listed
as a remaining weakness with an owner. Nothing was hidden.

**Baseline when this review started:** validator said ALL CHECKS PASSED — and the plan
still contained 44 unowned file references, 2 dependency cycles, 15 soft pass-criteria,
zero human-approval tasks, and a 20-day parity claim that was impossible at M0.
"Validator green" is where the audit starts, not where it ends.

---

## Part 1 — first 10 tasks: where I got stuck, guessed, or failed

### M0-T1 (repo scaffold)
- **Stuck:** outputs listed a bare `docs/` directory — a literal agent cannot create a
  directory as a deliverable. → **PATCHED:** removed; docs/ is created by M0-T9's files.
- **Guess:** `validate_plan.py` exits 2 (fatal) before plan.json exists. The task says
  "allow-fail with a TODO comment removed by M0-T7" — workable, kept.

### M0-T2 (Godot skeleton + runner)
- **Failed:** nothing told the agent how CI obtains the Godot binary; every later test
  command calls `godot` and would fail on a bare runner. → **PATCHED:** M0-T2 owns the
  logic-tests job (ci.yml as input) and its acceptance criteria now include "CI downloads
  the pinned Godot 4.3-stable binary (URL + sha256) and runs the runner green".
- **Contradiction:** outputs included `version.gd` with "reads model meta.title at
  runtime" — but model.gd does not exist until M0-T4. → **PATCHED:** M0-T2's version.gd
  exposes GAME_VERSION only; the title joins at M0-T8.
- **Gap:** `tools/check_project.py` was used by M0-T2's tests but its ownership said
  "if not already present, coordinate" — agents cannot coordinate. → **PATCHED:** owned
  by M0-T2; M0-T3/M0-T8 reach it via dependency closure.

### M0-T3 (Python RNG port)
- **Stuck:** this is the hardest task in the plan and its spec depends on the runner
  (M0-T2) with no declared dependency. → **PATCHED:** M0-T3 now depends on M0-T2.
- **Residual risk (not patchable by planning):** CPython's `random` internals are subtle
  (str seeds via sha512 → big-endian int → little-endian 32-bit words → init_by_array;
  gauss caches the second variate). The known-answer vectors are the real safety net.
  If the vectors pass but the *game* still diverges, the bug is in draw ORDER, not the
  RNG — see W2.

### M0-T4 (model loader)
- **Gotcha found by simulation:** `--path game` sandboxes `res://`; `res://../game_model.json`
  may not resolve. → **PATCHED:** acceptance criterion requires loading under both
  invocations, trying `res://../` then absolute paths derived from the script location,
  and erroring with the full searched-path list.
- **Gap:** nobody said who writes `game/tests/golden/model_sha.txt` first.
  → **PATCHED:** DoD names `--update-golden` in this task.

### M0-T5 (entities)
- **Gap:** `tools/dump_person.py` and `person_fixture.json` were used in tests but owned
  by nobody. → **PATCHED:** owned by M0-T5.

### M0-T6 (city generation)
- **Ordering paradox (would have deadlocked a literal agent):** M0-T6's parity test
  needed seeds 1–24 goldens from `tools/gen_golden.py`, which M0-T7 owned — and M0-T7
  depended on M0-T6. → **PATCHED:** gen_golden.py is created in M0-T6 (with `--kind city`);
  M0-T7 extends it via inputs. This is the single most important fix of the audit.

### M0-T7 (parity harness)
- **Impossible claim:** the M0 suite demanded "3 pinned run seeds replay 20 in-game days" —
  the day engine does not exist until M1-T3, and no pass is ported until M2. → **PATCHED:**
  m0 suite = RNG vectors + city seeds 0–24 only; the M0 exit gate and suite counts updated.
- **Perf guess:** one `godot` boot per seed would make the parity suite slow.
  → **PATCHED:** DoD now requires ONE headless process per suite, all seeds looped inside.

### M0-T8 (title screen)
- **Gap:** tests referenced `spec_title.gd` which no task owned. → **PATCHED:** added to
  outputs.

### M0-T9 (agent guide)
- **Gap:** `tools/check_docs.py` unowned; later tasks (M7-T6, M8-T*) call its `--policy`,
  `--build`, `--legal`, `--signoff`, `--rc`, `--postlaunch` modes without any dependency
  path to M0-T9. → **PATCHED:** owned by M0-T9; explicit M0-T9 dependencies added to
  M7-T6, M8-T2, M8-T3, M8-T4, M8-T6.

### M1-T1 (trade resolver)
- **Architecture hole (would have failed hard):** the spec must replay scripted trades
  through the ported resolver, but the run container (`engine.gd`) does not exist until
  M1-T3 — trade.gd had nothing to operate on. → **PATCHED:** M1-T1 owns
  `game/src/sim/run_state.gd` (minimal container: people, heat, player state, day);
  M1-T3's engine adopts it. The trade-vector golden now stores the scripted inputs too,
  so the game side replays the same script.
- **Guess resolved:** verified against sim.py that reason machine-labels are snake_case
  (`neighbors_greedy`, `neighbors_narrow`) with display labels living inside
  `game_model.json → reasons.*.label`; M2-T1's wording corrected so agents port the data,
  not the GDD's prose labels.

### Cross-cutting findings from the mechanical scans
- **44 unowned file references** (specs, goldens, checker tools) — every one either got an
  owner task, a dependency edge, or was reworded. A literal agent hits these as
  "file not found / who creates this?" failures.
- **2 dependency cycles** (M3-T1→M3-T12→M3-T3→M3-T1; M7-T2→M7-T5→M7-T2) — would have
  deadlocked any topological executor. Broken at the weakest edge.
- **15 pass-criteria without a concrete numeric/boolean criterion** ("YAML valid",
  "state machine cases pinned") — all rewritten with explicit exit codes and counts.
- **Ownership collisions** on `tools/parity_check.py`, `game/tests/golden/runs/`,
  `tools/placeholder_tiles.py`, `docs/asset_manifest.md`, `tools/audit_licenses.py` —
  resolved to single creators + `inputs` for modifiers (rule D6).
- **No human-approval tasks existed** although the rules demand them → M5-T8, M5-T9,
  M8-T4, M8-T5, M8-T7 are now `human_required` with placeholder-first paths.
- **All 93 tasks were graded M** — now 18 S / 75 M / 0 L.
- **Two design gaps found in the LOCKED design (not bugs, underspecification), resolved
  and logged in `decisions_log` as required:**
  - **D19:** GDD never says whether NPCs collide with the player. Resolution: walk-through,
    schedules are presentation-only.
  - **D20:** shop upgrades are sim-abstracted (`sim_coverage`), so their in-game mechanics
    are undefined ("buy prices 10% better" has no counterpart in the model's fixed coin
    flows). Resolution: precise game-only rules per upgrade, disabled under `--parity`.

---

## Part 2 — remaining weaknesses (ranked by impact)

### W1 — Float parity is machine-anchored, not math-anchored (HIGH)
`rng.gauss` calls `log/cos/sin` from libm. GDScript on the same Linux image calls the same
glibc, so pinned goldens reproduce — but a new CI image, a Godot upgrade that bundles a
different toolchain, or a contributor on Windows can produce 1-ULP drift that flips a
threshold comparison and cascades into different endings on some seeds. The plan detects
this (vectors + first-mismatch reporting + checksum gates) but cannot *prevent* it; the
honest fallback is the documented golden-regeneration procedure, which weakens the
"sim.py is the arbiter" promise to "sim.py on the reference machine is the arbiter".
**Mitigation owner:** M0-T7 (suite definitions), M7-T5 (nightly). **Residual:** accepted;
if divergence appears, the first response must be a bisection tool, not a regen.

### W2 — Draw-order fidelity is only as good as the porting discipline (HIGH)
Every pass task says "same rng call order as sim.py", but sim.py's `Run` methods interleave
rng draws across systems in ways only visible line-by-line. The plan's mitigation is
action-log parity (M2-T11) and per-pass traces, which localize an ordering bug to the first
divergent day — but a wrong order that produces *plausible* values can still pass unit
specs and only fail full-run parity. **Residual:** the M2 gate is the real tripwire; M2-T12
must not be merged with any known mismatch.

### W3 — Godot API risk concentrated in M0-T2/M1-T4/M5-T7 (MEDIUM)
The plan bans TileMap and .tscn editing, but GDScript still has failure surfaces: user-args
parsing after `--`, `SceneTree` script semantics, window/headless differences, llvmpipe in
the visual job. The pinned binary + one-true-runner rule reduces this; it does not zero it.
**Residual:** the first session on M0-T2 is the highest-risk hour of the project; if it
slips, everything slips (it is on the critical path).

### W4 — The plan trusts sim.py line references written by the planner (MEDIUM)
Context packs cite line ranges (e.g., "act_trade lines 236-310"). These were derived by
inspection and spot-verified (shield decay, bots, slots_for, upgrades), but not every range
was re-read end-to-end. If one is off by a few lines, the agent loses minutes, not days —
but the plan should be treated as a map, not a transcript. **Mitigation:** every context
pack also names the function to grep, so a stale line number is recoverable.

### W5 — Content volume is underestimated in effort terms (MEDIUM)
M3-T6 asks for 30 characters × 6–10 tagged choices with voice consistency. That is a
large single-session writing task; an agent may produce volume without voice or produce
tags that validate but read flat. The schema/lint checks catch mechanics, not quality;
the human readability pass (M3-T14) is the only quality gate. **Residual:** consider
splitting per-district if the first execution overruns a session (the plan allows it —
the 5 pack files are independent).

### W6 — The visual snapshot job is expected to be flaky (LOW, accepted)
xvfb + llvmpipe on shared runners will fail transiently. The plan already quarantines it
(optional workflow, pixel-sample tolerance, QA policy) and the logic band tests carry the
real guarantee. **Residual:** accepted; do not promote it to a blocking gate.

### W7 — Balance re-tuning procedure is social, not technical (LOW)
If someone changes `game_model.json`, the checksum gate forces the conversation — but no
tool can force the *right* conversation (regen goldens + balance report + test owner
sign-off). The AGENT_GUIDE documents the procedure; enforcement is review discipline.
**Residual:** accepted; R7 covers the detection half.

---

## Part 3 — unanswerable questions (decisions were made anyway; see decisions_log)

1. Should NPC-player collision ever exist (D19 chose walk-through)? Only playtesting can
   tell whether the city feels alive or ghostly.
2. Are the D20 upgrade semantics the design the notes intended? The model's effect strings
   ("buy prices 10% better") have no sim-side counterpart; my reading is documented and
   reversible in one task (M3-T9) plus one spec file.
3. Will a human reviewer actually be available at each of the 9 gates (open assumption)?
   The gates degrade to automated-only if not; the plan says which checklist items are
   judgement-only.
4. Is the 24-seed per-PR parity subset big enough? test_report.md needed 200 seeds for
   T1 rates; 24 seeds × 6 bots is a tripwire, not a verdict — the nightly sweep is the
   verdict. If PR-parity passes but nightly fails, the plan's procedure covers it, but
   the cost is a wasted night.

---

## Part 4 — risky assumptions worth re-checking before M2

- `random.Random(int)` behavior is stable across CPython 3.11 patch releases (assumed;
  vectors pin the exact interpreter that generated them).
- GDScript `float` is IEEE-754 double with no FMA contraction (true in 4.3's interpreted
  VM; would need re-verification if the VM ever JIT-compiles).
- `sim.py --tests` exits non-zero on failure (assumed by tools/run_model_tests.py; verify
  in M7-T5's first run).
- Godot 4.3's `OS.get_cmdline_user_args()` returns everything after `--` (assumed by every
  `-- only=` command; M0-T2's acceptance tests it explicitly).
