# SMALL WANTS — Game Design Document

**Version:** 1.0 (design complete, simulation-verified)
**Formerly:** "Greedy City" (working title in the design notes)
**Source of truth:** `game_model.json` v1.0.0-tuned. Every number in this document is copied from that file; where the two ever disagree, the JSON wins.
**Verification:** `sim.py` plays this document end-to-end with 6 scripted bots; `test_report.md` holds the results of the acceptance suite (200 seeds per strategy).

---

## 1. Overview

### 1.1 Premise (locked)

The player inherits a shop in a city whose people are greedy and selfish. The player is new and does not know what is wrong with the people — they find out by talking and trading. Every interaction either **feeds a person's greed or heals it**, and the cause is always visible to the player as a list of reasons. The previous owner was a kind relative, Uncle Fenn, who disappeared; the ledger reveals he got very rich and the city killed him for it. The same can happen to the player.

The player is corrupted too. Healing the city while staying good, getting rich and surviving, curing it while rotting yourself, or dying with it — those are the four endings, and every ending leads somewhere.

### 1.2 Design pillars

1. **Every trade and every word feeds a person's greed or heals it, and the cause is always visible to the player as a list of reasons.**
2. **Greed is contagious (prices, gossip, neighborhoods), and healing is never permanent.**
3. **The player is corrupted by greed too, and getting too rich gets the player killed.**
4. **The game feels endless: many different runs, not a 2-3 hour experience.**
5. **The simulation stays simple enough for a player to observe and understand.**

### 1.3 Format (locked)

2D top-down pixel art. Story/dialogue-driven trading simulation. Day-by-day time with limited actions per day. Two clocks run at once: the city's greed and the player's danger. Platform: PC (Steam, itch.io), 1280×720 window, mouse-first. Session length: 15–25 minutes (about one in-game week); a full run: 1–3.5 hours depending on the path. The long loop across cities is the "endless" layer.

### 1.4 Scales and bands (all visible unless noted)

| Meter | Range | Visibility |
|---|---|---|
| City greed | 0–100 | Always visible |
| Player greed | 0–100 | Always visible |
| Person greed | 0–100 | Hidden; fuzzy estimate at trust 25+, exact at 40+ hint/60+ full |
| Person trust | 0–100 | Hidden; the "why" list unlocks at 25 (partial) and 60 (full) |
| Market heat | 0–100 | Visible (drives the price channel) |
| Danger | 0–100 | **Never shown as a number** — only warning stages |

Key bands: **narrow** (a person cured of broad greed): greed ≤ 25. **Greedy** (tipped): greed ≥ their type tip (fear 55, pride 50, envy 45, ±6 seeded jitter). **City cured** (Healer ending bar): city ≤ 20. **City warning**: ≥ 60. **Dying zone**: ≥ 76 (collapse timer). **Valve**: ≥ 85 (despair). **Wealth limit** (fixed, locked design): 100 coins. **Tycoon target**: 250 coins. **Day cap**: 68.

---

## 2. The four loops

### 2.1 The moment (one trade)

A trade is one action: pick a person, pick an item (goods, favor, secret, time), pick a deal kind (generous, fair, tilted, exploitative) and a tone (honest, kind, flattering, threatening). The resolver (§3.2) produces: a reason on the target's greed list, trust changes, coin movement, market-heat response, witness ripple, and a player-greed delta. The player watches the why-list update in real time. A good moment is legible: *"Hessa Vess: Overcharged +8 (5d) — because you wanted the margin."*

### 2.2 The day

Each morning a plain-language **morning report** (§5.2) tells the player what spread overnight: who tipped, who recovered, what the prices did, what the gossip says, what happened. Then the player spends their actions: **2 on tutorial days 1–2, then 4 per day**. Actions: trades, favors, give-aways, promises, protecting/exposing secrets, minding the shop (income), reading the ledger. The day ends with the systems pass (§3.3–3.8), an ending check, and the night tick (reasons fade one day, everyone earns a 2-coin wage, secret discovery is checked, hoarding feeds the player's greed).

### 2.3 The run (one city, one arc)

A run is one generated city (§3.12). The run ends in one of the four endings or the day cap (§3.10). Typical lengths measured across 1,200 seeded runs: healer ≈ 50–70 days (the long arc), fallen healer ≈ 55–69, tycoon ≈ 16–22, passive ≈ 30–49, reckless ≈ 11–12, random ≈ 23–27. The day cap is 68: "the road goes on" — the player moves on before anything ends.

### 2.4 The long loop (across cities, locked)

Every ending leads somewhere (§3.10 carry-over table). If the player is killed, an **heir inherits the shop in the same city** — the city keeps its scars, the death becomes a reason in people's lists, and the ledger can be read to learn what went wrong. If the city collapses, the player flees to a new city with nothing. The shop's **wall of owners** shows one portrait per finished run with its ending. The game cannot be solved: every run is a new generated city.

---

## 3. Core systems with exact rules

### 3.1 Greed is a list of reasons

A person's greed is:

```
greed = clamp(base_greed + Σ(active reason deltas × their fade), 0, 100)
```

- `base_greed` starts at a generated value (§4) and **drifts**: −4/day while greed ≤ 25 (floor 15, or 10 for a secret person at peace) — *healing narrows the want itself*; +3.5/day while greed ≥ 45 (cap: the person's original base) — *neglect lets it creep back*.
- Each reason = {label, delta, days}. Its effect fades linearly over `days` and then drops off. Everything the player can do writes a reason; everything the simulation does writes a reason. Tapping a person shows the list (§5.1).
- **Trust** works the same way with its own catalog (§3.5).

**Reason catalog** (greed reasons; the full machine-readable list is in `game_model.json → reasons`):

| Reason | Delta | Days | Source |
|---|---|---|---|
| Fair deal | −9 | 8 | fair deal |
| Generous deal | −15 | 9 | generous deal |
| Overcharged | +8 | 5 | tilted deal |
| Fleeced | +14 | 8 | exploitative deal |
| Honest words | −3 | 4 | honest tone |
| Kind words | −4 | 4 | kind tone |
| Flattered | +5 | 4 | flattering tone |
| Threatened | +10 | 6 | threatening tone |
| Greedy neighbors | +15 | 2 | contagion pass (renewed daily) |
| Content neighbors | dynamic −8…−20 | 2 | contagion shield (renewed daily) |
| Prices rising | +5 market / +6 citywide | 3 | heat ≥ 60 / ≥ 75 |
| Gossip: someone struck it rich | +4 | 2 | gossip pass |
| Hungry | +8 (×1.3 fear) | 3 | famine event |
| Steady supply | −7 | 4 | fair/generous goods to fear-greed |
| Owes the player a favor | +3 (×1.5 fear) | 6 | favor |
| They promised me | −2 | 5 | promise |
| Betrayed a promise | +18 | 10 | betrayal |
| Kept their promise | −3 | 5 | keep-promise |
| Their secret is public | +15 | 8 | expose |
| Taste of easy coin | +12 | 10 | secret person corrupted |
| Old habit creeping back | +8 (+10 pressured) | 3 | relapse pass (re-added daily) |
| Festival warmth | −6 | 2 | festival event |
| Stranger's tales of riches | +10 | 6 | stranger event |
| Rumor of new riches | +4 | 2 | rumor event |
| Shortage | +5 (×1.3 fear) | 3 | shortage event |
| Market crash | −10 | 3 | crash event |
| Public scandal | −20 | 1 | scandal event (the hub) |
| The mighty have fallen | −6 | 3 | scandal event (envy people) |
| Someone richer paid the tax | −4 | 2 | tax event |
| Neighborly warmth | −4 | 3 | kindness wave event |
| A quiet wedding | −3 | 3 | wedding event |
| Saw the deal | dynamic 0.40 × target delta | 3 | witness ripple |
| The last shop owner was killed | +6 | 20 | heir runs only |

### 3.2 The trade resolver — all four layers (locked structure, exact values)

**Layer 1 — greed-type reaction.** Each type multiplies the deal's effect differently (matrix in §3.4).

**Layer 2 — item type.** goods ×1.0 (moves market heat; fair/generous goods to a fear person add *Steady supply* −7/4d); favor ×0.7 on greed but trust ×1.3 and adds the debt reason; secret ×1.5 on greed (exposing triggers the cascade, §3.9); time ×0.6 on greed and extends the target's positive reason durations by +50% (patience).

**Layer 3 — trust multiplier.**

```
heal_mult = (0.65 + 0.72 × trust/100) × (1 − weariness)   # applied to healing deltas
harm_mult = 1.25 − 0.50 × trust/100                        # applied to deal damage
word_mult = 0.60 + 0.70 × trust/100                        # applied to all word deltas
```

Trust amplifies healing and softens damage; low trust weakens words both ways. High trust is earned (§3.5) — it is the multiplier that makes late-game healing efficient.

**Layer 4 — witnesses and neighbor ripple.** Up to 4 same-district neighbors of the target receive a *Saw the deal* reason worth **0.40 × the target's net greed delta** (and 0.30 × the deal's trust delta). The ripple is ×1.25 while player greed ≥ 60 **on hostile deals only** — your cruelty spreads, your charity does not. While the safety valve is active the ripple is ×0.5.

**Deal kinds** (coin flow per deal; a person never drops below 5 coins — the player only gets what they can take):

| Kind | Coins (player / person) | Greed Δ (before multipliers) | Trust | Player greed |
|---|---|---|---|---|
| Generous | −6 / +6 | **−15** | +3 | −1 |
| Fair | +3 / −3 | **−9** | +3 | 0 |
| Tilted | +12 / −10 | **+8** | −5 | **+10** |
| Exploitative | +20 / −18 | **+14** | −10 | **+12** |

**Tones:** honest {greed −3, trust +2, player −1}, kind {−4, +1, −1}, flattering {+5, −1, **+2**}, threatening {+10, −12, +2}.

**Other actions:** favor {−3 coins, trust +6×1.3, debt reason}, give-away {−15 coins, target greed −6×heal_mult, trust +4, player −2}, work the shop {+1 coin}, protect secret {trust +10}, expose secret {+12 coins, target +15 greed 8d, trust −20, 3-person gossip cascade, **player +10**}, promise {trust +8}, keep promise {trust +6, −3 coins}, betray {target +18 greed 10d, trust −25, **player +5**}.

**Player greed** rises from tilted/exploitative deals (+10/+12), flattery (+2), exposing secrets (+10), betrayal (+5) and **hoarding (+2/day while wealth > 2× median person wealth)**; it falls from generous deals (−1), honest/kind words (−1) and give-aways (−2). Fair deals are greed-neutral — they pay the bills, they do not purify. Player greed ≥ 60 turns you into gossip (12%/day a random person hears *the shopkeeper hoards coin*: their trust −2, greed +3) and amplifies your hostile-deal ripple. It gates the endings: Healer needs current < 40 **and peak < 55**; Fallen Healer needs **peak ≥ 55**.

### 3.3 Threshold contagion — three channels (locked: prices, gossip, neighborhoods)

Run once per day per person over their neighbor set (ring within district + seeded cross-district ties; hubs count double):

```
greedy_frac = Σ(weight of greedy neighbors) / Σ(all neighbor weights)
if greedy_frac >= contagion_threshold[type]:   renew "Greedy neighbors" +15 (2d)
if no greedy same-district neighbor AND all same-district neighbors narrow:
                                               renew the content shield (below)
```

Thresholds (Granovetter/Watts): **fear 0.60, pride 0.50, envy 0.35** — envy tips first, fear last.

**Channel 1 — neighborhoods** is the pass above.

**Channel 2 — prices (market heat).** Heat drifts daily: `heat += (mean Market Square greed − 50) × 0.04`. Tilted/exploitative goods deals in Market Square: heat +3; fair/generous: −2. Heat ≥ 60: Market Square gets *Prices rising* +5 daily. Heat ≥ 75: **all districts** get +6 daily — the citywide spiral. This is how one seller's greed becomes everyone's problem.

**Channel 3 — gossip.** Each greedy person spreads gossip 30%/day (hubs 60%/day to 2 targets): 65% same district, 35% anywhere. Effect: *Gossip: someone struck it rich* +4 (2d). Player greed ≥ 60 makes the player the subject (§3.2).

**The content shield.** When no same-district neighbor is greedy and all same-district neighbors are narrow, a person gets *Content neighbors*: **−(20 − min(12, 1.5 × days since the district last saw you))**. Freshly visited districts hold at −20; abandoned districts rot back toward −8 — **healed neighborhoods hold only while you keep showing up** (pillar 2, literal). Narrow people also take all contagion-tagged reasons at ×0.5 (the content resist pressure), and un-corrupted secret people at ×0.3 (they look immune).

### 3.4 Three greed types and their cures (locked)

| Type | Meaning | Cure (locked) | Tip | Contagion threshold | Deal reaction | Word reaction |
|---|---|---|---|---|---|---|
| **Fear-greed** | Hoarding to survive | Make them feel secure: steady supply and fair prices | 55 | 0.60 | generous/fair ×1.2, tilted ×1.1, exploitative ×1.2 | honest/kind ×0.8–1.0, flattering ×0.6, threatening ×1.2 |
| **Pride-greed** | Status | Honest, humble dealing that does not feed their status | 50 | 0.50 | generous ×0.8, fair ×1.0, tilted ×1.0, exploitative ×0.9 | honest/kind ×1.2, **flattering ×1.8**, threatening ×1.0 |
| **Envy-greed** | Copying neighbors | Fix the hub they are copying | 45 | 0.35 | all ×1.0 | all ×1.0 |

Specials: fair/generous **goods** to fear people add *Steady supply* −7 (4d); debts weigh ×1.5 on fear; flattery is the fastest corrupter of pride (×1.8); envy tips first from neighbors and heals fastest when its hub falls in line.

District mapping (adopted from the notes): **Docks fear-greed, The Hill pride-greed, Market Square and Tavern Row envy-greed, Counting House mixed pride/fear** (per-person seeded 2:1).

### 3.5 Trust

Trust = clamp(base_trust + Σ(fading trust reasons), 0, 100); base_trust generated 12–45 (secret people 32).

Earned: fair deals +3 (12d), generous +3 (12d), favors +7.8 (12d), protecting a secret +10 (15d), honest words +2 (8d), kind +1 (8d), promises +8 (10d), kept promises +6 (12d).
Lost: tilted −5 (8d), exploitative −10 (10d), flattering −1 (6d), threats −12 (10d), betrayal −25 (20d), exposing a secret −20 (15d), player-greed gossip −2 (6d), **relapse scorn −18 (16d)** — a person you healed and left tips back with *"You healed me, then left me"*.

Unlocks: trust ≥ 25 → fuzzy greed estimate + top-2 reasons; trust ≥ 40 → secret hint; trust ≥ 60 → exact reason list, true tip threshold, and their tip number.

### 3.6 Relapse — healing is never permanent (locked causes: neglect, greedy neighbors, betrayal)

A narrow person tracks their last positive contact. After a **2-day grace**, neglect re-adds *Old habit creeping back* **+8 per day (+10 if at least half their neighbors are greedy)**, fading over 3 days and stacking to ≈ +16/day of pressure, **cleared entirely by any positive contact**. Neglect alone drifts a healed person to an uneasy plateau; the relapse **completes** when any greedy pressure (neighbors, gossip, an event) joins them. Betrayal (+18) completes it instantly.

Three compounding costs make neglect expensive:

1. **Scorn** — the person you healed and left tips back with trust −18 (16d).
2. **Weariness** — each relapse adds 18% (max 42%) weakness to all future healing on that person, decaying 2%/day. The city learns your routine.
3. **The base** — healed people's wants narrow (base floor 15), but the greedy base climbs back +3.5/day, and the shield rots when you stay away (§3.3).

**Stated guarantee (measured, 100 forced cases):** a neglected narrow person **under active neighbor pressure** (their contagion threshold crossed) relapses within **14 days** of the last positive contact (measured mean 12.1, max 15); a neglected person without pressure drifts to an uneasy plateau and holds until pressure arrives; a fully narrow neighborhood holds as long as the shield stands.

### 3.7 Danger — "too rich" (locked: all four rules)

Danger is hidden. Daily update:

```
gain_raw = (3.5 × max(0,(wealth−40)/100) + 2 × max(0, wealth/median_person_wealth − 3) + distrust)
           × (1.4 − 0.8 × mean_trust/100)
gain     = min(gain_raw, 14)          # a mob needs time to organize
danger  += gain − decay               # decay 4 if wealth < 100 else 2
```

1. **Low trust makes it sooner** — distrust +1.5 if mean trust < 40, +1.5 more if < 25; the trust mitigation multiplies everything.
2. **The gap** — wealth over 3× the median person's.
3. **The fixed wealth limit** — 100 coins; the base term bites above 40.
4. **Hidden; only warning signs** — stage 1 at 30 (*stares and whispers*), 2 at 50 (*overcharging and snubs*), 3 at 70 (*threats and break-ins*; thieves events), 4 at 90 (*the mob gathers*). **Death at 100** — the city kills the player. The 14/day gain cap guarantees **at least 5 days of warnings** between stage 1 and death (measured: minimum gap exactly 5, median ~7).

### 3.8 The safety valve and the dying zone

- **City ≥ 76 (dying zone):** the collapse timer runs. Held there **8 consecutive days → Doom (city collapsed)**.
- **City ≥ 80:** the dying city's standards collapse — everyone's base sinks 1.5/day (replacing the greedy base climb-back). The rot eats the want itself.
- **City ≥ 85 (valve):** despair peaks — healing multipliers ×2, greed gains ×0.5, contagion thresholds +0.05 harder, extra heat decay −1/day, and the storyteller triples *Market crash* and *Scandal* and doubles *Festival*. Everyone's standards keep sinking while the desperation holds.

Darkness is a race between the collapse timer and the city's own despair: the timer usually wins if nobody works the city; the despair usually wins if someone does. Nothing is a point of no return.

### 3.9 Hidden-secret people (locked)

**4 of the 30**, one each in 4 seeded districts, never hubs. They appear immune to greed but hide a secret: they are greedy about **food or money** specifically. Mechanics:

- **Immune-looking:** contagion-tagged reasons (neighbors, prices, gossip, rumor, stranger tales) at ×0.3 while un-corrupted.
- **Discovery:** trust ≥ 40 reveals the hint (*you have seen where they stash bread/coins*); checked nightly.
- **Corruption:** a tilted/exploitative deal in their weak-spot item (food = goods; money = any coin deal) adds *Taste of easy coin* +12 (10d), removes the immunity, and sets **greed growth ×1.5 forever** — fragile and easy to corrupt, exactly as designed.
- **Protection:** protect-secret action: trust +10, their secret can never be exposed.
- **At peace:** a protected secret person healed below narrow reaches base floor 10 — the hardest cure, the longest hold.

### 3.10 Endings and what each carries into the next city

Checked nightly in priority order. Conditions (locked four, exact bars):

| Priority | Ending | Condition | Carries into… |
|---|---|---|---|
| 1 | **Doom — killed** | danger ≥ 100 | **An heir inherits the shop in the SAME city.** All greed, trust and heat carry; active reason durations halved; every person gains *The last shop owner was killed* +6 (20d); trust reset to 0.5×current (a new face, but the city remembers the family). Heir starts: wealth 40, greed 20, danger 0, ledger readable. |
| 2 | **Doom — city collapsed** | city ≥ 76 held 8 consecutive days | **The player flees to a new city with nothing:** wealth 20, greed 15. |
| 3 | **Healer** | day ≥ 12 AND city ≤ 20 AND every hub narrow AND player greed < 40 AND peak < 55 AND mean trust ≥ 30 | **New city.** Reputation precedes you: trust +10 for everyone; wealth = 20 + 0.2×final; greed min(30, final); trinket *Fenn's Scale* (see fair prices). |
| 4 | **Fallen Healer** | city ≤ 20 AND player greed peak ≥ 55 | **New city.** Your greed came with you (carried peak); trust −5 everyone; rumors preceded you. You may be the one who spreads it (hostile ripple ×1.25 from day one). |
| 5 | **Tycoon** | wealth ≥ 250 AND danger ≤ 40 AND day ≥ 12 | **New city.** You arrive rich: wealth = max(120, 0.6×final); **danger starts at 30** — the gap and the danger are there on day one. |
| — | Day cap | day > 68 | New city; wealth = 20 + 0.3×final; greed halved. The road goes on. |

A cured city with player greed 40–54 and wealth < 250 keeps playing: the player must choose who they become.

### 3.11 The storyteller and the event deck

One roll per day at 60% chance; weighted pick among eligible events. RimWorld-style pacing: pressure events dominate in dark cities, kindness events in healing ones, and it eases off when the player is drowning.

| Event | Weight | Condition | Effect |
|---|---|---|---|
| Famine | 10 | city < 75 | *Hungry* +8 (3d) on 4 people (Docks-biased), heat +8 |
| Festival | 8 | city > 60 | *Festival warmth* −6 (2d) all, heat −6 |
| Tax collector | 10 | wealth > 120 | takes 12%; *Someone richer paid the tax* −4 (2d) all |
| A stranger arrives | 11 | always (14 when city < 40) | *Stranger's tales of riches* +10 (6d) on one person |
| A rumor | 10 | a greedy hub exists | *Rumor of new riches* +4 (2d) on 4 people |
| Supply shortage | 7 | heat < 70 | *Shortage* +5 (3d) on 4 (Docks/Market bias), heat +6 |
| Break-in | 12 | danger ≥ 65 | player loses 12 coins |
| Market crash | 14 (×3 valve) | city ≥ 85 | heat −25; *Market crash* −10 (3d) on Market + Hill |
| A scandal | 12 (×3 valve) | city ≥ 85 | a greedy hub falls: −20 instantly; envy people −6 (3d) |
| Kindness spreads | 10 | city ≤ 35 AND mean trust ≥ 50 | *Neighborly warmth* −4 (3d) on everyone below 40 |
| A wedding | 4 | two narrow people share a district | both −3 (3d), trust +4 |
| A quiet day | 10 | fallback | nothing |

### 3.12 New-city generation (adopted: "a new city every run")

Seeded by `gen_seed` (rng key `city-<seed>`) — the same rules every time, shuffled every time:

- **5 districts × 6 people = 30.** Districts are locked in character: Market Square (prices, envy), Tavern Row (gossip, envy), Counting House (debts, pride/pride/fear per person), Docks (poverty, fear), The Hill (wealth, pride). First listed person of each district is its hub.
- **Name and role pools** (30 fixed identities, §4) — the same souls, reshuffled into new arrangements? No: the pools are per-district and fixed; the generator shuffles types within the Counting House, secret placement, bases, tips, wealth, and cross-district ties. The city name is prefix+suffix from seeded pools (canonical seed 0: **Grelwater**).
- **Secrets:** 4 of the 5 districts get one seeded non-hub secret-keeper with a seeded kind (food/money).
- **Bases:** normal(type mean 60–64, σ6) clamped [15,75]; secret-keepers 22. **Tips:** type tip ±6. **Trust:** normal(28, σ6) clamped [12,45]. **Wealth** by district: Docks 10–26, Market 18–40, Tavern 16–34, Counting 30–58, Hill 55–95.
- **Neighbors:** ring within district plus 6 seeded cross-district pairs (hubs count double in contagion).
- **Heat start:** uniform 55–70 — prices are already climbing when you arrive.
- **Player start:** wealth 50, greed 30, danger 0.
- **Previous owner:** Uncle Fenn (locked), death day 40–55, final wealth 300–450 (seeded). The ledger holds his last month: early fair prices, then tilted deals, warnings logged and ignored, last entry: *"They were at the door. The ledger goes to whoever reads it. Don't be me."*
- The canonical city (seed 0) is frozen into `game_model.json → canonical_city` and asserted against the generator every run.

### 3.13 The shop, upgrades, and progression

The shop is the player's hub. Its look reflects player greed tiers (plain → polished → gilded → sickly gold). Upgrades: **Shelf** (40c, +1 trade slot, buy prices 10% better), **Sign** (60c, fair-deal ripple +50%), **Back Room** (80c, secrets safe from thieves), **Teapot** (120c, a 5th action every other day). The **ledger** unlocks on day 3 and holds Uncle Fenn's last month; after a death it also holds the previous run's summary. The **wall of owners** hangs one portrait per finished run. Meta-trinkets per ending: Fenn's Scale (healer), Iron Key (tycoon), Gilded Mirror (fallen), Heir's Ledger (killed). Sim coverage: upgrades are abstracted out of `sim.py` (economy depth, not loop math); everything else numeric in this document is simulated.

---

## 4. The city — five districts, thirty named people

Every run generates a new city with the same rules; below is the **canonical city (gen_seed 0): Grelwater** (heat start 68.9; Uncle Fenn died day 50 with 361 coins). Base greed = starting settled want; tip = the person's tipping point. "Secret" = hidden-secret person (§3.9).

**Market Square — the price layer (envy-greed)**

| Name | Role | Hub | Greed type | Base | Tip | Secret |
|---|---|---|---|---|---|---|
| Marla Vess | Stall Matriarch | ★ | envy | 62.0 | 43.4 | — |
| Tov Blake | Baker | | envy | 22.0 | 41.7 | **food** |
| Sela Finch | Fishmonger | | envy | 72.2 | 50.8 | — |
| Durn Cobb | Spice Trader | | envy | 53.9 | 44.7 | — |
| Pem Willet | Stall Apprentice | | envy | 54.2 | 40.2 | — |
| Hessa Vess | Preserve Seller | | envy | 65.0 | 45.4 | — |

**Tavern Row — the gossip layer (envy-greed)**

| Name | Role | Hub | Greed type | Base | Tip | Secret |
|---|---|---|---|---|---|---|
| Old Cuttle | Barkeep | ★ | envy | 62.0 | 47.4 | — |
| Ryn Ash | Bard | | envy | 59.2 | 48.4 | — |
| Dova Mott | Card Shark | | envy | 56.5 | 50.7 | — |
| Bram Tull | Dockhand | | envy | 54.5 | 39.9 | — |
| Ida Spoon | Cook | | envy | 58.7 | 45.1 | — |
| Kes Needle | Tailor | | envy | 22.0 | 45.0 | **food** |

**Counting House — where debts live (pride, one fear)**

| Name | Role | Hub | Greed type | Base | Tip | Secret |
|---|---|---|---|---|---|---|
| Odara Vail | Ledgermistress | ★ | pride | 66.0 | 44.2 | — |
| Juno Pask | Clerk | | pride | 61.7 | 44.6 | — |
| Hal Forty | Appraiser | | fear | 65.6 | 49.1 | — |
| Sib Ranter | Moneylender | | pride | 56.7 | 52.6 | — |
| Weck Dole | Notary | | pride | 59.7 | 47.4 | — |
| Mote | Errand Runner | | fear | 64.6 | 50.0 | — |

**Docks — the poor and desperate (fear-greed)**

| Name | Role | Hub | Greed type | Base | Tip | Secret |
|---|---|---|---|---|---|---|
| Mother Brine | Soup-Keeper | ★ | fear | 64.0 | 51.0 | — |
| Oll Pike | Deckhand | | fear | 22.0 | 56.2 | **food** |
| Maren Salt | Netmender | | fear | 65.2 | 58.8 | — |
| Corvo Lash | Netmaker | | fear | 54.1 | 55.6 | — |
| Rutt Barrow | Stevedore | | fear | 62.7 | 55.3 | — |
| Wick | Oyster Girl | | fear | 59.9 | 59.1 | — |

**The Hill — the wealthy (pride-greed)**

| Name | Role | Hub | Greed type | Base | Tip | Secret |
|---|---|---|---|---|---|---|
| Ambrose Vane | Squire | ★ | pride | 66.0 | 48.4 | — |
| Odile Charm | Widow | | pride | 67.3 | 53.8 | — |
| Dorian Sull | Merchant Prince | | pride | 58.6 | 48.0 | — |
| Lady Pyne | Collector | | pride | 22.0 | 53.0 | **money** |
| Gray | Butler | | pride | 74.7 | 49.0 | — |
| Silky Drew | Tailor to the Rich | | pride | 56.4 | 47.9 | — |

---

## 5. UI readability (pillar: the cause is always visible)

### 5.1 The "why they feel this way" list

Tapping a person shows name, role, district, and their **active reasons in plain language, strongest first, with remaining days**:

> **Sela Finch — Fishmonger**
> Greedy neighbors +15 (2d left)
> Prices rising +5 (1d left)
> You overcharged her +8 (3d left)
> Gossip: someone struck it rich +4 (1d left)
> *Her settled want: 72 → she tips at 51*

Locked behind trust: below 25 shows *???*; at 25+ a fuzzy estimate (calm / uneasy / greedy) and the top 2 reasons; at 60+ everything, their true tip, and any secret hint. Player-facing numbers never appear for people — the reasons are the numbers.

### 5.2 The morning report

Every morning, plain language, generated from the night's diffs:

> *Day 12. Tipped to greed: Durn Cobb, Ida Spoon. Recovered: Pem Willet. Prices rose (heat 71). A rumor made the rounds — 4 people heard it. 6 pieces of gossip changed hands. Last night: a stranger arrived. Your danger: stares and whispers.*

It names who tipped, who recovered, the heat, the event, the gossip volume, and the player's warning stage. It is generated by `sim.py` for every run — sample outputs are in `test_report.md`.

### 5.3 Meters

City greed and player greed: always visible, bar + number. Market heat: visible with a flame trend. Person greed/trust: never shown as numbers, only through the why-list gates. Danger: never a number — only the four warning banners.

---

## 6. Tag-based dialogue system

The simulation logic reads **only tags**; the prose is presentation.

```json
{ "menu_choice": "Fair price, same as always. Bread keeps well, you know.",
  "tags": { "topic": "price", "tone": "honest", "intent": "heal",
            "item": "goods", "secret_flag": false } }
```

- Every menu choice ships pre-tagged. Character voice = plain data (formality, greed vocabulary, pet phrases) — the logic never reads prose.
- **v1.1 (post-launch):** a small on-device model (1) turns free-typed text into the same tags, (2) rewrites tag-shaped lines in each character's voice. If it is slow or low-confidence, the game falls back to the menu choices with no logic change.
- Character memory (trust, reasons, secrets, promise state) stays plain data either way.

---

## 7. Art and audio direction for the greed-driven tone shift

- **Palette bands** follow city greed: 0–25 warm pastel dawn (hopeful) → 25–50 amber daylight (ordinary) → 50–75 burnt orange, rust, hard shadows (tense) → 75–100 ashen violet, black water, gold-only highlights (dark).
- **Sprites:** personal tint follows personal greed; narrow people gain one small warm pixel accent — their *small want*.
- **Music:** layered chiptune rounds that lose a layer every 15 city-greed points; below 50 a detuned counter-melody fades in; at valve range only percussion and one thin lead remain. Healing restores layers, never instantly.
- **Barks:** lines get shorter and crueler with city greed; hubs stop greeting you at danger stage 2.
- **Scars:** healed districts keep 1–2 scar pixels — healing is never permanent, visually.
- **SFX:** coin pitch rises with player greed; at danger stage 3 the night ambience gains a crowd murmur.

---

## 8. Decisions log

Every item from the notes, labeled. **LOCKED** = notes §1–19 (design decisions made before this document; implemented as stated). **ADOPTED / MODIFIED / REJECTED** = notes §20 proposals. **NEW** = open questions (notes §21) decided here.

| # | Item | Status | Decision & one-line reason |
|---|---|---|---|
| 1 | Premise, format, 2D pixel art, top-down | LOCKED | As designed. |
| 2 | Trade affects greed via deal + words, four layers | LOCKED | Values now exact (§3.2). |
| 3 | Greed spreads via prices + gossip + neighborhoods | LOCKED | All three channels implemented and tested (§3.3). |
| 4 | Three greed types with their cures | LOCKED | Exact matrices added (§3.4). |
| 5 | Meters: city + player visible, people hidden, danger hidden | LOCKED | Why-list gates implemented (§5.1). |
| 6 | Day-by-day, limited actions, two clocks | LOCKED | 2 actions days 1–2, then 4; day cap 68. |
| 7 | Relapse via neglect / greedy neighbors / betrayal | LOCKED | Habit mechanic + scorn + weariness (§3.6); guarantee measured. |
| 8 | Four endings | LOCKED | Exact conditions + priority (§3.10); all four reachable, each mainly by its intended strategy. |
| 9 | Tone darkens with greed | LOCKED | Palette bands + music layers (§7). |
| 10 | 5 districts, 30 people, hubs | LOCKED | Canonical Grelwater frozen (§4). |
| 11 | Hidden-secret people: few, fragile, food/money | LOCKED | 4 of 30, mechanics (§3.9). |
| 12 | Inherited shop; Fenn got rich and was killed; same for player | LOCKED | Ledger content written; heir path simulated (§3.10). |
| 13 | "Too rich" via low trust + gap + fixed limit + warnings | LOCKED | Exact danger formula, 4 stages, death at 100 (§3.7). |
| 14 | Trust via fair deals, protected secrets, promises, honest words | LOCKED | Catalog (§3.5). |
| 15 | Dialogue: choices now, small model later | LOCKED | Tag schema + v1.1 plan (§6). |
| 16 | Reasons-based approach (RimWorld/CK/threshold models) | LOCKED | Implemented end-to-end. |
| 17 | Every ending leads somewhere; heir or flee | LOCKED | Carry-over table (§3.10); 3-run chains tested. |
| 18 | §20: base trade table (draft) | MODIFIED | Structure kept; "fair is greed-neutral" added; exact values (§3.2). |
| 19 | §20: layer details (type reactions, item types, trust mult, witnesses, "your side") | ADOPTED | All five, exact (§3.2). |
| 20 | §20: district→type mapping (fear Docks, pride Hill, envy Market+Tavern) | ADOPTED | Counting House added as pride/fear mix. |
| 21 | §20: city collapse trigger = city meter max | MODIFIED | Dying zone at 76 held 8 days; standards collapse at 80; valve at 85 (§3.8). |
| 22 | §20: greed vs danger separation | ADOPTED | Greed = behavior, danger = wealth+trust (§3.7). |
| 23 | §20: warning stages (stares → overcharging → threats → mob) | ADOPTED | At danger 30/50/70/90 (§3.7). |
| 24 | §20: morning report | ADOPTED | Generated from diffs (§5.2). |
| 25 | §20: shop as hub, look reflects greed, upgrades, ledger | ADOPTED | 4 upgrades + ledger + wall (§3.13). |
| 26 | §20: healing = narrowing the want, not erasing it | ADOPTED | The base/hysteresis system (§3.1) — the want narrows and re-widens. |
| 27 | §20: tempting secret people in their weak spot corrupts them | ADOPTED | Corruption seed mechanic (§3.9). |
| 28 | §20: secrets can be traded but protecting earns trust | ADOPTED | Expose vs protect actions (§3.2, §3.9). |
| 29 | §20: healing hubs/neighborhoods holds longer | ADOPTED | Content shield (§3.3) — and it decays when you stay away. |
| 30 | §20: dynamic tone details (palettes, music, cruel dialogue, scars) | ADOPTED | §7. |
| 31 | §20: ending carry-overs (reputation / rich / greed) | ADOPTED | Carry table (§3.10), tested in 3-run chains. |
| 32 | §20: wall of owners | ADOPTED | One portrait per run (§3.13). |
| 33 | §20: three play loops (moment/day/arc) | ADOPTED | §2. |
| 34 | §20: storyteller | ADOPTED | 12-event deck, weights, valve boosts (§3.11). |
| 35 | §20: new city every run | ADOPTED | Seeded generation (§3.12); 24-city distribution test. |
| 36 | §20: long-term goals (upgrades, new items, seasons) | MODIFIED | Upgrades + new items kept; **seasons REJECTED** for 1.0 — the city generation already varies runs. |
| 37 | §20: small-model preparation (tags, rewrite, fallback, memory) | ADOPTED | §6. |
| 38 | §21: game title | NEW | **Small Wants** — the healing theme is narrowing greed to one small want. Alternatives rejected: *The Greedy City* (generic), *Ledger & Lamp* (cozy, wrong tone). |
| 39 | §21: exact trade numbers | NEW | §3.2 tables; tuned against 1,200+ seeded runs. |
| 40 | §21: reasons list, sizes, durations | NEW | §3.1 catalog. |
| 41 | §21: type thresholds and neighbor groups | NEW | Fear 0.60 / pride 0.50 / envy 0.35; ring + 6 cross-ties, hubs double. |
| 42 | §21: how the safety valve works | NEW | Despair teeth (heal ×2, greed ×0.5, base sink 1.5/day at 80+, shock events) — §3.8. |
| 43 | §21: district/people types | NEW | §4 mapping + Counting House mix. |
| 44 | §21: secret count and discovery | NEW | 4 of 30; trust ≥ 40 hint, nightly check (§3.9). |
| 45 | §21: what raises/lowers player greed | NEW | §3.2 (tilted +10, exploitative +12, expose +10, betray +5, hoarding +2/day; generous −1, give-away −2). |
| 46 | §21: wealth limit, warning signs, death | NEW | Limit 100; stages at 30/50/70/90; death at 100; mob-organizing cap 14/day (§3.7). |
| 47 | §21: opening and tutorial | NEW | Fenn's letter (day 0), 2-action days 1–2, guided first trades with Marla and Old Cuttle, ledger on day 3. |
| 48 | §21: shop and progression | NEW | §3.13 upgrades, costs 40/60/80/120. |
| 49 | §21: Fenn's story and ledger contents | NEW | Death day 40–55, wealth 300–450 (seeded); ledger = his last month + run summaries after deaths (§3.12). |
| 50 | §21: named characters | NEW | 30 names + roles (§4). |
| 51 | §21: number of in-game days | NEW | Cap 68; typical run 11–69 days by path; session ≈ one week of game days. |
| 52 | §21: platform, session length, music/sound | NEW | PC/Steam/itch, 15–25 min sessions, layered chiptune (§1.3, §7). |
| 53 | §21: when the small model is added | NEW | v1.1 post-launch; fallback to menus (§6). |
| 54 | §21: ending carry-overs and between-run carry | NEW | Carry table (§3.10); wall of owners + trinkets persist. |
| 55 | §21: how each new city is generated | NEW | §3.12; canonical seed 0 frozen and asserted. |
| 56 | §21: storyteller and its event list | NEW | §3.11 deck. |
| 57 | §21: long-term goals across runs | NEW | Wall of owners + 4 ending trinkets (§3.13). |
| 58 | §21: wall of owners | NEW | Yes — adopted and spec'd (§3.13). |

**Known deviations from "by the book" tuning (deliberate, measured):** fair deals are greed-neutral (the notes' draft had them lowering greed — they pay the bills, they do not purify); tilted deals corrupt the player hard (+10) so the fallen path is playable; the peak-greed latch (§3.10) makes "you became greedy" a fact that finishing the cure cannot erase; the relapse guarantee is pressure-conditional (neglect opens the door, greedy neighbors walk through it) — this is what the 100-case forced test actually shows, and it is stated that way rather than pretended otherwise.
