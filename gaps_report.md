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

## Revision 2 (2026-11-26) — producer inputs incorporated

The producer reviewed plan v1.0.0 and returned four inputs: two weaknesses found in the
locked simulation, an engine pin (Godot 4.7.2), a platform decision (mobile-first:
iOS & Android, desktop later), and an architecture mandate (data-driven: no hardcoded
data in Godot, everything from JSON). Every claim was re-verified against the design
files before being logged; the plan is now v1.1.0 with decisions D21–D24, tasks
M7-T9/M7-T10, risks R11–R14, principles +2, and a new validator rule 10 that fails if
any of the four directives silently regresses.

### Producer finding 1 — the graph is too small for the thresholds to matter (VERIFIED)

Re-measured, not copied. Across 200 seeded cities (6,000 people, `sim.py
generate_city`) the degree histogram is 2: 3,975, 3: 1,705, 4: 284, 5: 33, 6: 3 —
**66.2% of people have exactly 2 neighbors** (ring within district + 6 cross-district
pairs, sim.py lines 122–134). With two ordinary (weight-1) neighbors the only
achievable `greedy_frac` values are 0, 0.5, 1.0. Contagion thresholds
(`game_model.json → contagion.thresholds`) are fear 0.60, pride 0.50, envy 0.35, so:

- pride and envy tip on the **identical fraction set {0.5, 1.0}** for degree-2 people —
  they are indistinguishable for two-thirds of the population;
- fear requires frac = 1.0 (both neighbors greedy), which does work;
- "envy tips first" — the 0.35 ≤ frac < 0.50 band where envy tips and pride does not —
  requires a hub neighbor (weight 2.0 in `contagion_pass`) or degree ≥ 4, i.e. it can
  only show up around hubs or people with extra ties. Exact match with the producer's
  finding.

Design is LOCKED → no redesign. Patched as **D22**: the behavior is pinned by the
existing parity goldens (M2-T12), measured by the new **M7-T9** topology report
(degree histogram + per-threshold tip rates per degree class + channel-coupling
metrics), and recorded in-repo by `docs/sim_behavior_notes.md` (owned by M7-T9). The
audit also added a do-not-fix failure mode to M2-T1: a well-meaning porting agent must
not "improve" the pride/envy equivalence — parity with sim.py is the goal. Any
threshold/degree retune is a post-1.0 design change requiring owner sign-off + golden
regeneration (open assumption).

### Producer finding 2 — only one channel uses the graph (VERIFIED)

Confirmed in code, not prose: `gossip_pass` (sim.py ~line 415) picks seeded random
targets with a **70% same-district bias** and never reads neighbor lists; market prices
act on Market Square or all districts (`game_model.json → market.price_reasons`);
only `contagion_pass` iterates neighbor lists. The social graph carries exactly one of
the three channels — consistent with the GDD's three-channel design, but "graph-based"
oversells it. Patched as **D23**: M7-T9 quantifies channel-vs-topology coupling (% of
gossip targets that are graph neighbors; price reasons reaching non-adjacent people);
`gossip-along-edges` and `price-locality` are logged as post-1.0 design-change
requests; M2-T2 gained a do-not-reroute failure mode.

### Producer directives — engine, platforms, architecture

- **Godot 4.7.2** (D24): the 4.3 pin is superseded *before execution starts* — the
  cheapest possible moment. Parity is machine-anchored (W1), so M0-T2 re-pins the CI
  binary URL + sha256, and M0-T3/M0-T6 regenerate the RNG known-answer vectors and
  city goldens **on the 4.7.2 toolchain** before any ported code exists to debug.
  Validator rule 10 now fails if the pin regresses. Residual risk tracked as R14.
- **Mobile-first (iOS + Android), desktop later** (D14 rewritten; supersedes GDD 1.3's
  PC lock per planning rule 11): M8 was reworked — M8-T1 produces five export presets
  (Android arm64-v8a + armeabi-v7a, iOS, and Win/Linux/macOS kept building but
  release-deferred), M8-T2's release CI ships AAB/APK/IPA artifacts with a
  debug-keystore/human-signing split, M8-T6 adds a static APK check (with an aapt2
  degradation path), M8-T7 becomes Google Play + App Store submission (human), and the
  M8 gate's human playtests moved onto devices. Touch was already the primary input
  model (tap/click, M1-T6), so no earlier milestone churns. New risk: R13.
- **Data-driven mandate** (D21, extends D7): every design number, roster, dialogue
  tag, palette band, audio rule and store copy loads from JSON at runtime. New
  **M7-T10** adds `tools/check_data_driven.py --strict` (fails CI on content literals
  in .gd outside the engine-constants whitelist; the literal blacklist is itself built
  from game_model.json + game/data JSONs at runtime — the lint is data-driven too),
  and the check joined the M7 exit gate.

### Audit findings from re-simulating the changed tasks (all patched)

- **F1 (the dangerous one):** M2-T1/M2-T2 porting agents could treat the two
  producer-found behaviors as bugs and "fix" them, silently breaking parity →
  do-not-fix failure modes added (D22/D23 are facts to reproduce, not defects).
- **F2:** M7-T9's `--check` needs its golden to exist first → `--update-golden`
  first-run named in DoD (same fix pattern as M0-T4's model_sha.txt in revision 1).
- **F3:** "+/- 2pp of 66.2% on 24 seeds" is a sampling-noise trap (sd ≈ 1.76pp) →
  CI gate is now the deterministic 24-seed golden only; the 200-seed reference run
  (66.2% ± 1pp) is documented, not a gate. The current 24-seed share is 66.0%.
- **F4:** M7-T10's selftest fixture ownership and the runtime-built literal blacklist
  were underspecified → DoD lines added.
- **F5:** CI cannot release-sign Android/iOS without human-held keys → debug-keystore
  (CI) / release-signing (human) split documented in M8-T2, consumed by M8-T7.
- **F6:** M8-T6's APK versionName check needs aapt2 → build-tools installed by the
  release job; explicit degradation path when absent (exit 0 with a SKIPPED line).

Plan size after revision 2: **95 tasks (18 S / 77 M / 0 L)**, 9 milestones, 24
decisions, 14 risks; critical path recomputed by validate_plan.py (unchanged at 31).

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

Revision-1 numbering (W1–W7) is preserved so cross-references in decisions_log stay
valid. Revision 2 appends W8–W10 below and promotes two producer-verified facts above
the ranking: the threshold-vs-graph coarseness (D22, R11) and the single-graph-channel
reality (D23, R12) are the two highest-visibility weaknesses in the project — fully
measured, documented in docs/sim_behavior_notes.md via M7-T9, and deliberately NOT
redesigned while the design is locked. They rank first in impact and last in
actionability; everything below is ranked after them.

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

### W8 — Mobile is now the ship platform, and its gates are human-held (MEDIUM-HIGH, new in revision 2)
Android/iOS bring failure surfaces the revision-1 plan never had: mid-range devices
must hold the frame budget (M7-T3's CI numbers are a proxy, not the device), the App
Store/Play review can reject builds late in M8, and signing/provisioning is human-only
by definition (M8-T2 F5 split, M8-T7). The desktop fallback still builds, but "ship"
now means passing gates no CI can automate. **Mitigation:** budgets calibrated to a
mid-range Android reference device from M1; static APK check with aapt2 degradation
(F6); device smoke before submission. **Residual:** store-review timing is
uncontrollable; R13 tracks it.

### W9 — The 4.7.2 bump re-anchors every machine-anchored promise (LOW residual, new in revision 2)
The engine pin moved 4.3 → 4.7.2 before execution, which is the cheapest moment — but
W1's mechanism applies: RNG known-answer vectors and city goldens must be regenerated
ON the 4.7.2 toolchain (M0-T3/M0-T6), and if the VM ever changes float semantics in a
later 4.x, the same re-anchoring repeats. Because no ported code exists yet, the bump
costs hours, not weeks. **Residual:** accepted; R14 tracks it; rule 10 pins the
version so it cannot drift silently.

### W10 — The data-driven lint fights its own false-positive rate (LOW, new in revision 2)
M7-T10 must flag content literals (thresholds, deltas, names, hex codes) without
drowning agents in layout-math false positives. The whitelist + runtime-built
blacklist (F4) keeps it precise, but a lint that is too strict gets bypassed with
generic "data-driven: ok" comments, and one that is too loose becomes theater. The
selftest pins both directions. **Residual:** accepted; the M7 gate runs --strict so
erosion is visible.

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
