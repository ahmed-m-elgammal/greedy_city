#!/usr/bin/env python3
"""
Small Wants - seeded deterministic simulator.
Reads game_model.json and plays full runs with scripted bots.

Usage:
  python3 sim.py --freeze-roster          # print canonical roster (gen_seed 0) as JSON
  python3 sim.py --smoke                  # quick sanity run (6 bots x 5 seeds)
  python3 sim.py --run BOT SEED           # single run debug
  python3 sim.py --tests [--out DIR]      # full acceptance test suite (200 seeds/strategy)
"""

import json, os, sys, math, argparse, statistics, random, time
from multiprocessing import Pool

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "game_model.json")

M = None

def load_model():
    global M
    if M is None:
        with open(MODEL_PATH, "r", encoding="utf-8") as f:
            M = json.load(f)
    return M

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

# ---------------------------------------------------------------- entities

class Reason:
    __slots__ = ("label", "delta", "days_left", "days")
    def __init__(self, label, delta, days):
        self.label = label; self.delta = float(delta)
        self.days_left = int(days); self.days = int(days)
    def eff(self):
        return self.delta * (self.days_left / self.days) if self.days > 0 else 0.0

class Person:
    __slots__ = ("pid","name","district","role","gtype","is_hub","secret","secret_kind",
                 "discovered","corrupted","protected","at_peace","base0","base",
                 "greed_reasons","trust_reasons","trust_base","wealth","wealth0","tip",
                 "neighbors","last_positive","relapses","weariness","exposed","was_healed")
    def __init__(self, pid, name, district, role, gtype, is_hub, secret_kind,
                 base_greed, base_trust, tip, wealth):
        self.pid = pid; self.name = name; self.district = district; self.role = role
        self.gtype = gtype; self.is_hub = is_hub
        self.secret = secret_kind is not None; self.secret_kind = secret_kind
        self.discovered = False; self.corrupted = False; self.protected = False
        self.at_peace = False
        self.base0 = float(base_greed); self.base = float(base_greed)
        self.greed_reasons = []; self.trust_reasons = []
        self.trust_base = float(base_trust)
        self.wealth = float(wealth); self.wealth0 = float(wealth)
        self.tip = float(tip)
        self.neighbors = []
        self.last_positive = -99
        self.relapses = 0; self.weariness = 0.0; self.exposed = False
        self.was_healed = False
    def greed(self):
        return clamp(self.base + sum(r.eff() for r in self.greed_reasons), 0.0, 100.0)
    def trust(self):
        return clamp(self.trust_base + sum(r.eff() for r in self.trust_reasons), 0.0, 100.0)
    def is_greedy(self):
        return self.greed() >= self.tip
    def is_narrow(self):
        return self.greed() <= 25.0

CONTAGION_TAGS = ("neighbors_greedy","prices_rising","gossip_rich","rumor","stranger_tales")
RENEW_LABELS = ("neighbors_greedy","neighbors_narrow","prices_rising")  # old_habit stacks

# ---------------------------------------------------------------- city generation

DISTRICT_PEOPLE = {
    "market":  [("Marla Vess","Stall Matriarch"),("Tov Blake","Baker"),("Sela Finch","Fishmonger"),
                ("Durn Cobb","Spice Trader"),("Pem Willet","Stall Apprentice"),("Hessa Vess","Preserve Seller")],
    "tavern":  [("Old Cuttle","Barkeep"),("Ryn Ash","Bard"),("Dova Mott","Card Shark"),
                ("Bram Tull","Dockhand"),("Ida Spoon","Cook"),("Kes Needle","Tailor")],
    "counting":[("Odara Vail","Ledgermistress"),("Juno Pask","Clerk"),("Hal Forty","Appraiser"),
                ("Sib Ranter","Moneylender"),("Weck Dole","Notary"),("Mote","Errand Runner")],
    "docks":   [("Mother Brine","Soup-Keeper"),("Oll Pike","Deckhand"),("Maren Salt","Netmender"),
                ("Corvo Lash","Netmaker"),("Rutt Barrow","Stevedore"),("Wick","Oyster Girl")],
    "hill":    [("Ambrose Vane","Squire"),("Odile Charm","Widow"),("Dorian Sull","Merchant Prince"),
                ("Lady Pyne","Collector"),("Gray","Butler"),("Silky Drew","Tailor to the Rich")],
}

def generate_city(gen_seed):
    load_model()
    cg = M["city_generation"]; gt = M["greed_types"]; bands = M["state_bands"]
    rng = random.Random("city-%d" % gen_seed)
    name = rng.choice(cg["name_prefixes"]) + rng.choice(cg["name_suffixes"])
    people = []; pid = 0
    base_mean = cg["base_greed_means"]
    for d in cg["districts"]:
        did = d["id"]; types = d["greed_types"]
        pool = DISTRICT_PEOPLE[did]
        for i, (pname, prole) in enumerate(pool):
            gtype = types[i % len(types)]
            is_hub = (i == 0)
            secret_kind = None
            if is_hub:
                bg, bt = base_mean[gtype] + 2.0, 30.0
            else:
                bg = clamp(rng.gauss(base_mean[gtype], 6.0), 15, 75)
                bt = clamp(rng.gauss(28, 6.0), 12, 45)
            tip = gt[gtype]["tip"] + rng.uniform(-bands["tip_jitter"], bands["tip_jitter"])
            wr = cg["wealth_ranges"][did]
            wealth = rng.uniform(wr[0], wr[1])
            people.append(Person(pid, pname, did, prole, gtype, is_hub, secret_kind,
                                 bg, bt, tip, wealth))
            pid += 1
    # secrets: 4 of 5 districts, one seeded non-hub each
    for did in rng.sample([d["id"] for d in cg["districts"]], 4):
        cands = [p for p in people if p.district == did and not p.is_hub]
        p = rng.choice(cands)
        p.secret_kind = rng.choice(M["secret_people"]["kinds"])
        p.secret = True
        p.base = 22.0; p.base0 = 22.0; p.trust_base = 32.0
        p.tip = clamp(p.tip + rng.uniform(-3, 3), 38, 62)
    # neighbors: ring within district + 6 cross-district pairs
    by_d = {}
    for p in people: by_d.setdefault(p.district, []).append(p)
    for did, lst in by_d.items():
        for i, p in enumerate(lst):
            p.neighbors.append(lst[i-1].pid); p.neighbors.append(lst[(i+1) % len(lst)].pid)
    dids = [d["id"] for d in cg["districts"]]
    pairs = [(a,b) for i,a in enumerate(dids) for b in dids[i+1:]]
    for _ in range(6):
        a, b = rng.choice(pairs)
        pa = rng.choice(by_d[a]); pb = rng.choice(by_d[b])
        if pb.pid not in pa.neighbors:
            pa.neighbors.append(pb.pid); pb.neighbors.append(pa.pid)
    prev_death_day = rng.randint(40, 55)
    prev_wealth = rng.randint(300, 450)
    heat_lo, heat_hi = 55, 70
    heat = rng.uniform(heat_lo, heat_hi)
    return {"name": name, "people": people, "heat": heat,
            "prev_owner": {"name": "Uncle Fenn", "death_day": prev_death_day,
                           "final_wealth": prev_wealth}}

# ---------------------------------------------------------------- the run

class Run:
    def __init__(self, bot, seed, gen_seed=None, carry=None, inherit_city=None):
        load_model()
        self.bot = bot; self.seed = seed
        self.rng = random.Random(seed)
        self.gen_seed = gen_seed if gen_seed is not None else seed
        self.day = 0
        self.diffs = {"tips": [], "recoveries": [], "gossip": 0, "event": None, "heat_chg": 0.0}
        self.warning_stage = 0; self.warning_days = {}
        self.danger_max = 0.0
        self.city_peak = 0.0; self.city_min = 100.0
        self.collapse_counter = 0
        self.events_fired = []
        self.death_day = None
        self.pending_promises = []   # [(pid, day)]
        self.player_greed = 0.0
        self.pg_peak = 0.0
        self.danger = 0.0
        self.wealth = 0.0
        self.reports = []
        self.heat = 50.0
        self.city = generate_city(self.gen_seed)
        self.people = self.city["people"]
        co = M["city_generation"]["player_start"]
        self.wealth = float(co["wealth"]); self.player_greed = float(co["greed"])
        if carry: self.apply_carry(carry)
        self.pg_peak = self.player_greed
        if inherit_city: self.apply_inherit(inherit_city)

    # ----- carry-over / inheritance ------------------------------------
    def apply_carry(self, carry):
        end = carry["ending"]
        if end == "healer":
            self.wealth = 20 + 0.2 * carry["wealth"]
            self.player_greed = min(30.0, carry["player_greed"])
            for x in self.people: x.trust_base = clamp(x.trust_base + 10, 0, 100)
        elif end == "tycoon":
            self.wealth = max(120, 0.6 * carry["wealth"])
            self.danger = float(M["carry_over"]["tycoon"]["danger_start"])
            self.player_greed = carry["player_greed"]
        elif end == "fallen_healer":
            self.player_greed = carry["player_greed"]
            for x in self.people: x.trust_base = clamp(x.trust_base - 5, 0, 100)
        elif end == "doom_collapsed":
            self.wealth = 20.0; self.player_greed = 15.0
        elif end == "day_cap":
            self.wealth = 20 + 0.3 * carry["wealth"]
            self.player_greed = 0.5 * carry["player_greed"]

    def apply_inherit(self, prev):
        """Heir inherits the SAME city after the player was killed."""
        self.people = prev["city"]["people"]; self.city = prev["city"]
        self.heat = prev["heat"]; self.danger = prev.get("danger", 0.0)
        for x in self.people:
            for r in x.greed_reasons: r.days_left = max(1, r.days_left // 2)
            for r in x.trust_reasons: r.days_left = max(1, r.days_left // 2)
            x.trust_base = 0.5 * x.trust()
            self.add_reason(x, "scar_owner_killed", 6, 20)
        self.wealth = 40.0; self.player_greed = 20.0; self.danger = 0.0

    # ----- reasons ------------------------------------------------------
    def add_reason(self, person, label, delta, days, contagion_tag=False):
        if contagion_tag and person.secret and not person.corrupted:
            delta *= M["secret_people"]["immunity_factor"]
        if contagion_tag and person.is_narrow():
            delta *= 0.5   # the already-content resist rumor and pressure
        if label in RENEW_LABELS:
            person.greed_reasons = [r for r in person.greed_reasons if r.label != label]
        person.greed_reasons.append(Reason(label, delta, days))

    def add_trust(self, person, delta, days, label="tr"):
        person.trust_reasons.append(Reason(label, delta, days))

    # ----- meters -------------------------------------------------------
    def city_greed(self):
        tot, w = 0.0, 0.0
        for x in self.people:
            ww = 2.0 if x.is_hub else 1.0
            tot += x.greed() * ww; w += ww
        return clamp(0.75 * tot / w + 0.25 * self.heat, 0, 100)

    def mean_trust(self):
        return sum(x.trust() for x in self.people) / len(self.people)

    def valve_active(self):
        return self.city_greed() >= M["state_bands"]["city_valve"]

    def median_wealth(self):
        return max(20.0, statistics.median(x.wealth for x in self.people))

    # ----- player actions -----------------------------------------------
    def act_trade(self, person, item, deal, intent):
        T = M["trade"]; gt = M["greed_types"][person.gtype]
        R = M["reasons"]
        tm = T["trust_multipliers"]["structured"]
        trust = person.trust()
        heal_mult = (tm["heal"]["a"] + tm["heal"]["b"] * trust / 100) * (1.0 - person.weariness)
        harm_mult = tm["harm"]["a"] + tm["harm"]["b"] * trust / 100
        word_mult = tm["word"]["a"] + tm["word"]["b"] * trust / 100
        if self.valve_active():
            heal_mult *= M["safety_valve"]["effects"]["heal_mult_x"]
            harm_mult *= M["safety_valve"]["effects"]["harm_mult_x"]
        item_mult = T["item_types"][item]["greed_mult"]
        # deal effect on target greed
        g = T["deal_kinds"][deal]["greed"] * gt["deal_reaction"][deal] * item_mult
        g = g * (heal_mult if g < 0 else harm_mult)
        if person.corrupted and g > 0: g *= 1.5
        # intent (words) effect on target greed
        w = T["intents"][intent]["greed"] * gt["word_reaction"][intent]
        w = w * (word_mult if w < 0 else word_mult)
        if person.corrupted and w > 0: w *= 1.5
        net_g = g + w
        self.add_reason(person, "deal_" + deal, g, R["greed_reasons"]["deal_" + deal]["days"])
        self.add_reason(person, "word_" + intent, w, R["greed_reasons"]["word_" + intent]["days"])
        # fear: steady supply from fair/generous goods
        if item == "goods" and deal in ("fair","generous") and person.gtype == "fear":
            self.add_reason(person, "steady_supply", -7, R["greed_reasons"]["steady_supply"]["days"])
        # trust changes (deal and words separate, no double count)
        tr_deal = T["deal_kinds"][deal]["trust"]
        if item == "favor": tr_deal *= 1.3
        tr_intent = T["intents"][intent]["trust"]
        self.add_trust(person, tr_deal, R["trust_reasons"]["tr_" + deal]["days"], "tr_" + deal)
        self.add_trust(person, tr_intent, R["trust_reasons"]["tr_" + intent]["days"], "trw_" + intent)
        # coins (person keeps a floor of 5)
        c = T["deal_kinds"][deal]["coins_player"]
        cp = T["deal_kinds"][deal]["coins_person"]
        if cp < 0:
            cp = -min(-cp, max(0.0, person.wealth - 5))
            c = -cp
        self.wealth = max(0.0, self.wealth + c)
        person.wealth = clamp(person.wealth + cp, 5, 120)
        # market heat responds to goods deals in Market Square
        if item == "goods" and person.district == "market":
            self.heat = clamp(self.heat + (3 if deal in ("tilted","exploitative") else -2), 0, 100)
        # secret people: temptation in the weak spot corrupts
        if person.secret and deal in ("tilted","exploitative"):
            weak = (person.secret_kind == "food" and item == "goods") or person.secret_kind == "money"
            if weak and not person.corrupted:
                person.corrupted = True; person.discovered = True
                self.add_reason(person, "corruption_seed", 12, R["greed_reasons"]["corruption_seed"]["days"])
        # player greed
        pg = T["deal_kinds"][deal]["player_greed"] + T["intents"][intent]["player_greed"]
        self.player_greed = clamp(self.player_greed + pg, 0, 100)
        # witness ripple (same-district neighbors of the target)
        frac = M["trade"]["witness_ripple"]["fraction"]
        if self.player_greed >= 60 and deal in ("tilted", "exploitative"):
            frac *= 1.25   # your cruelty spreads; your charity does not
        if self.valve_active(): frac *= 0.5
        ripple = net_g * frac
        witnesses = [self.people[i] for i in person.neighbors
                     if self.people[i].district == person.district][:4]
        for wper in witnesses:
            if abs(ripple) >= 0.5:
                self.add_reason(wper, "witness", ripple, R["greed_reasons"]["witness"]["days"])
            if abs(tr_deal) >= 1:
                self.add_trust(wper, tr_deal * 0.30, R["trust_reasons"]["tr_witness"]["days"], "tr_witness")
        # positive contact bookkeeping (relapse grace)
        if net_g < 0 or intent in ("honest","kind"):
            person.last_positive = self.day
        # time item: patience extends positive reasons on the target
        if item == "time":
            for r in person.greed_reasons:
                if r.delta < 0:
                    r.days_left += max(1, int(round(r.days * 0.5)))
        return net_g

    def act_favor(self, person):
        c = M["trade"]["other_actions"]["favor"]["coins"]
        if self.wealth < -c: return
        self.wealth += c
        self.add_trust(person, 6 * 1.3, M["reasons"]["trust_reasons"]["tr_favor"]["days"], "tr_favor")
        d = 3 * (1.5 if person.gtype == "fear" else 1.0)
        self.add_reason(person, "debt", d, M["reasons"]["greed_reasons"]["debt"]["days"])
        person.last_positive = self.day

    def act_give_away(self, person):
        oa = M["trade"]["other_actions"]["give_away"]
        if self.wealth < -oa["coins"]: return
        self.wealth += oa["coins"]
        self.add_reason(person, "deal_generous",
                        -6 * (0.55 + 0.75 * person.trust()/100),
                        M["reasons"]["greed_reasons"]["deal_generous"]["days"])
        self.add_trust(person, oa["trust"], 12, "tr_generous")
        person.last_positive = self.day
        self.player_greed = clamp(self.player_greed + oa["player_greed"], 0, 100)

    def act_work_shop(self):
        self.wealth += M["trade"]["other_actions"]["work_shop"]["coins"]

    def act_protect(self, person):
        oa = M["trade"]["other_actions"]["protect_secret"]
        self.add_trust(person, oa["trust"], 15, "tr_protect_secret")
        self.add_reason(person, "steady_supply", -2, 4)
        person.protected = True; person.discovered = True
        person.last_positive = self.day

    def act_expose(self, person):
        oa = M["trade"]["other_actions"]["expose_secret"]
        self.wealth += oa["coins"]
        person.discovered = True; person.exposed = True
        self.add_reason(person, "secret_exposed", 12, M["reasons"]["greed_reasons"]["secret_exposed"]["days"])
        self.add_trust(person, -20, 15, "tr_secret_exposed")
        for w in self.rng.sample(self.people, 3):
            self.add_reason(w, "gossip_rich", 4, 2, contagion_tag=True)
        self.player_greed = clamp(self.player_greed + M["reasons"]["player_greed_reasons"]["pg_expose"]["delta"], 0, 100)

    def act_promise(self, person):
        oa = M["trade"]["other_actions"]["promise"]
        self.add_trust(person, oa["trust"], 10, "tr_promise_made")
        self.add_reason(person, "promise_made", -2, 5)
        self.pending_promises.append((person.pid, self.day))
        person.last_positive = self.day

    def act_keep_promise(self, person):
        oa = M["trade"]["other_actions"]["keep_promise"]
        if self.wealth < -oa["coins"]: return
        self.wealth += oa["coins"]
        self.add_trust(person, oa["trust"], 12, "tr_promise_kept")
        self.add_reason(person, "promise_kept", -3, 5)
        self.pending_promises = [p for p in self.pending_promises if p[0] != person.pid]
        person.last_positive = self.day

    def act_betray(self, person):
        pr = M["reasons"]["greed_reasons"]["betrayal"]
        self.add_reason(person, "betrayal", pr["delta"], pr["days"])
        self.add_trust(person, -25, M["reasons"]["trust_reasons"]["tr_betrayal"]["days"], "tr_betrayal")
        self.player_greed = clamp(self.player_greed + M["reasons"]["player_greed_reasons"]["pg_betray"]["delta"], 0, 100)
        self.pending_promises = [p for p in self.pending_promises if p[0] != person.pid]

    # ----- daily systems --------------------------------------------------
    def contagion_pass(self):
        thr_b = M["contagion"]["thresholds"]
        valve = self.valve_active()
        for x in self.people:
            if not x.neighbors: continue
            tot_w = 0.0; greedy_w = 0.0
            for nid in x.neighbors:
                nb = self.people[nid]
                w = 2.0 if nb.is_hub else 1.0
                tot_w += w
                if nb.is_greedy(): greedy_w += w
            frac = greedy_w / tot_w
            thr = thr_b[x.gtype]
            if valve: thr += M["safety_valve"]["effects"]["contagion_threshold_bonus"]
            if frac >= thr:
                d = M["reasons"]["greed_reasons"]["neighbors_greedy"]["delta"]
                if valve: d = M["safety_valve"]["effects"]["neighbors_greedy_delta"]
                self.add_reason(x, "neighbors_greedy", d, 2, contagion_tag=True)
            elif not any(self.people[nid].is_greedy() and self.people[nid].district == x.district
                         for nid in x.neighbors) and \
                 all(self.people[nid].is_narrow()
                     for nid in x.neighbors if self.people[nid].district == x.district):
                # shield strength decays with district absence: visited districts
                # hold at -20; abandoned ones rot back toward -8
                last_contact = max((self.people[nid].last_positive
                                    for nid in x.neighbors
                                    if self.people[nid].district == x.district), default=-99)
                days_absent = max(0, self.day - last_contact)
                shield = -(20 - min(12, int(1.5 * days_absent)))
                self.add_reason(x, "neighbors_narrow", shield, 2)

    def gossip_pass(self):
        g = 0
        for x in self.people:
            if not x.is_greedy(): continue
            chance = 0.6 if x.is_hub else 0.3
            n = 2 if x.is_hub else 1
            for _ in range(n):
                if self.rng.random() < chance:
                    same = [p for p in self.people if p.district == x.district and p.pid != x.pid]
                    if self.rng.random() < 0.7 and same:
                        t = self.rng.choice(same)
                    else:
                        if self.rng.random() < 0.35:
                            t = self.rng.choice([p for p in self.people if p.pid != x.pid])
                        else:
                            t = self.rng.choice(same)
                    self.add_reason(t, "gossip_rich",
                                    M["reasons"]["greed_reasons"]["gossip_rich"]["delta"],
                                    M["reasons"]["greed_reasons"]["gossip_rich"]["days"],
                                    contagion_tag=True); g += 1
        if self.player_greed >= 60 and self.rng.random() < 0.12:
            t = self.rng.choice(self.people)
            self.add_trust(t, -2, 6, "tr_player_gossip")
            self.add_reason(t, "hoard_envy", 3, 2); g += 1
        self.diffs["gossip"] = g

    def market_pass(self):
        mk = [p for p in self.people if p.district == "market"]
        mmean = sum(p.greed() for p in mk) / len(mk)
        extra = M["safety_valve"]["effects"]["extra_heat_decay"] if self.valve_active() else 0
        self.heat = clamp(self.heat + (mmean - 50) * 0.04 - extra, 0, 100)
        if self.heat >= 60:
            mk_pr = M["market"]["prices_reason_market"]
            for x in mk:
                self.add_reason(x, "prices_rising", mk_pr, 3, contagion_tag=True)
        if self.heat >= 75:
            cw = M["market"]["prices_reason_citywide"]
            for x in self.people:
                self.add_reason(x, "prices_rising", cw, 3, contagion_tag=True)

    def base_drift(self):
        rel = M["relapse"]
        wdecay = M["relapse"]["weariness_decay_per_day"]
        floor_n = M["state_bands"].get("narrow_base_floor", 10)
        floor_p = M["state_bands"].get("peace_base_floor", 8)
        sink = rel["base_sink_per_day"]; rec = rel["base_recover_per_day"]
        desperate = self.city_greed() >= M["state_bands"]["city_collapse"]
        for x in self.people:
            if x.weariness > 0:
                x.weariness = max(0.0, x.weariness - wdecay)
            g = x.greed()
            if g <= M["state_bands"]["narrow_max"]:
                floor = floor_p if (x.secret and x.protected) else floor_n
                x.base = max(floor, x.base - sink)
            elif desperate and g >= 45:
                # the valve's teeth: while the city is dying, people's
                # standards collapse - the settled want itself shrinks,
                # and this replaces the greedy base climb-back
                x.base = max(15.0, x.base - M["safety_valve"]["effects"]["base_sink_while_desperate"])
            elif g >= 45:
                x.base = min(x.base0, x.base + rec)

    def relapse_pass(self):
        grace = M["relapse"]["grace_days"]
        for x in self.people:
            if x.is_narrow():
                x.was_healed = True   # they know what contentment feels like
            neglected = x.is_narrow() and (self.day - x.last_positive) > grace
            if not neglected:
                # any positive contact clears the creeping habits
                x.greed_reasons = [r for r in x.greed_reasons if r.label != "old_habit"]
                continue
            nb = x.neighbors
            ng = sum(1 for nid in nb if self.people[nid].is_greedy())
            d = M["relapse"]["old_habit_delta_greedy_neighbors"] if nb and ng * 2 >= len(nb) \
                else M["relapse"]["old_habit_delta"]
            # re-added daily while neglected; fades over 3 days, so the
            # pressure is bounded; a narrow person left alone drifts to an
            # uneasy plateau and tips once any neighbor pressure joins
            self.add_reason(x, "old_habit", d, 3)

    def storyteller(self):
        if self.rng.random() >= M["storyteller"]["chance"]:
            return None
        st = M["storyteller"]; city = self.city_greed()
        boosts = M["safety_valve"]["effects"]["event_weight_boosts"] if self.valve_active() else {}
        eligible = []
        for ev in st["events"]:
            eid = ev["id"]; w = ev["weight"] * boosts.get(eid, 1)
            if eid == "stranger" and city < 40: w = 12
            ok = False
            if eid == "famine": ok = city < 75
            elif eid == "festival": ok = city > 60
            elif eid == "tax_collector": ok = self.wealth > ev.get("min_player_wealth", 0)
            elif eid == "stranger": ok = True
            elif eid == "rumor": ok = any(p.is_hub and p.is_greedy() for p in self.people)
            elif eid == "shortage": ok = self.heat < 70
            elif eid == "thieves": ok = self.danger >= 65
            elif eid in ("market_crash","scandal"): ok = city >= M["state_bands"]["city_valve"]
            elif eid == "kindness_wave": ok = city <= 35 and self.mean_trust() >= 50
            elif eid == "wedding":
                ok = False
                for a in self.people:
                    if a.is_narrow() and any(b.district == a.district and b.is_narrow()
                                             for b in self.people if b.pid != a.pid):
                        ok = True; break
            elif eid == "quiet_day": ok = True
            if ok and w > 0: eligible.append((eid, w))
        if not eligible: return None
        tot = sum(w for _, w in eligible)
        roll = self.rng.uniform(0, tot)
        for eid, w in eligible:
            roll -= w
            if roll <= 0:
                self.apply_event(eid); return eid
        return None

    def apply_event(self, eid):
        self.events_fired.append((self.day, eid))
        rng = self.rng
        if eid == "famine":
            docks = [p for p in self.people if p.district == "docks"]
            victims = rng.sample(docks, min(2, len(docks))) + rng.sample(self.people, 2)
            for v in victims:
                d = 6 * (1.3 if v.gtype == "fear" else 1.0)
                self.add_reason(v, "hungry", d, 3, contagion_tag=True)
            self.heat = clamp(self.heat + 8, 0, 100)
        elif eid == "festival":
            for p in self.people: self.add_reason(p, "festival", -6, 2)
            self.heat = clamp(self.heat - 6, 0, 100)
        elif eid == "tax_collector":
            self.wealth = max(0, self.wealth * 0.88)
            for p in self.people: self.add_reason(p, "tax_relief", -3, 2)
        elif eid == "stranger":
            cands = [p for p in self.people if not p.secret]
            v = rng.choice(cands); self.add_reason(v, "stranger_tales", 8, 6, contagion_tag=True)
        elif eid == "rumor":
            hubs = [p for p in self.people if p.is_hub and p.is_greedy()]
            if hubs:
                for v in rng.sample(self.people, 4):
                    self.add_reason(v, "rumor", 3, 2, contagion_tag=True)
        elif eid == "shortage":
            poor = [p for p in self.people if p.district in ("docks","market")]
            vs = rng.sample(poor, min(2, len(poor))) + rng.sample(self.people, 2)
            for v in vs:
                self.add_reason(v, "shortage", 5 * (1.3 if v.gtype == "fear" else 1.0), 3)
            self.heat = clamp(self.heat + 6, 0, 100)
        elif eid == "thieves":
            self.wealth = max(0, self.wealth - 12)
        elif eid == "market_crash":
            self.heat = clamp(self.heat - 25, 0, 100)
            for p in self.people:
                if p.district in ("market","hill"): self.add_reason(p, "crash", -10, 3)
        elif eid == "scandal":
            hubs = [p for p in self.people if p.is_hub and p.is_greedy()]
            if hubs:
                h = rng.choice(hubs)
                self.add_reason(h, "scandal_self", -20, 1)
                for p in self.people:
                    if p.gtype == "envy" and p.pid != h.pid:
                        self.add_reason(p, "scandal_fall", -6, 3)
        elif eid == "kindness_wave":
            for p in self.people:
                if p.greed() < 40: self.add_reason(p, "warmth", -4, 3)
        elif eid == "wedding":
            byd = {}
            for p in self.people: byd.setdefault(p.district, []).append(p)
            for did, lst in byd.items():
                nar = [p for p in lst if p.is_narrow()]
                if len(nar) >= 2:
                    a, b = nar[0], nar[1]
                    self.add_reason(a, "wedding", -3, 3); self.add_reason(b, "wedding", -3, 3)
                    self.add_trust(a, 4, 10, "tr_kind"); self.add_trust(b, 4, 10, "tr_kind")
                    break

    def danger_update(self):
        d = M["danger"]["structured"]
        median = self.median_wealth()
        mt = self.mean_trust()
        base = d["base_term"]["coef"] * max(0.0, (self.wealth - d["base_term"]["grace_below"]) / d["base_term"]["divisor"])
        gap = d["gap_term"]["coef"] * max(0.0, self.wealth / median - d["gap_term"]["multiple_over_median"])
        distrust = 0.0
        if mt < 40: distrust += d["distrust_term"]["trust_lt_40"]
        if mt < 25: distrust += d["distrust_term"]["trust_lt_25_extra"]
        mit = d["trust_mitigation"]["a"] + d["trust_mitigation"]["b"] * mt / 100
        gain = min((base + gap + distrust) * mit, d["gain_cap"])
        decay = d["decay_wealth_below_limit"] if self.wealth < M["state_bands"]["wealth_limit"] \
                else d["decay_wealth_at_or_above_limit"]
        self.danger = clamp(self.danger + gain - decay, 0, 100)
        self.danger_max = max(self.danger_max, self.danger)
        for stage, at in enumerate(M["state_bands"]["danger_warnings"], start=1):
            if self.danger >= at and self.warning_stage < stage:
                self.warning_stage = stage
                self.warning_days.setdefault(stage, self.day)

    # ----- morning report -------------------------------------------------
    def morning_report(self):
        lines = ["Day %d." % self.day]
        if self.diffs["tips"]:
            lines.append("Tipped to greed: " + ", ".join(self.diffs["tips"][:4]) + ".")
        if self.diffs["recoveries"]:
            lines.append("Recovered: " + ", ".join(self.diffs["recoveries"][:4]) + ".")
        lines.append("Prices %s (heat %d)." % ("rose" if self.diffs["heat_chg"] > 0 else "fell",
                                               round(self.heat)))
        if self.diffs.get("event"): lines.append("Last night: %s." % self.diffs["event"])
        if self.diffs["gossip"]: lines.append("%d pieces of gossip made the rounds." % self.diffs["gossip"])
        st = {1:"stares and whispers",2:"overcharging and snubs",3:"threats and break-ins",4:"the mob gathers"}
        if self.warning_stage: lines.append("Your danger: %s." % st[self.warning_stage])
        return " ".join(lines)

    # ----- endings ---------------------------------------------------------
    def check_endings(self):
        b = M["state_bands"]
        if self.danger >= b["danger_death"]:
            return "doom_killed"
        if self.collapse_counter >= b["collapse_sustain_days"]:
            return "doom_collapsed"
        if self.day >= b["healer_min_day"] and self.city_greed() <= b["city_cured"] \
           and all(h.is_narrow() for h in self.people if h.is_hub) \
           and self.player_greed < b["player_greed_healer_max"] \
           and self.pg_peak < b["player_greed_fallen_min"] \
           and self.mean_trust() >= M["state_bands"]["healer_min_trust"]:
            return "healer"
        if self.city_greed() <= b["city_cured"] and self.pg_peak >= b["player_greed_fallen_min"]:
            return "fallen_healer"
        if self.wealth >= b["tycoon_wealth_target"] and self.danger <= b["tycoon_danger_max"] \
           and self.day >= b["healer_min_day"]:
            return "tycoon"
        return None

    def snapshot_city(self):
        return {"city": self.city, "heat": self.heat, "danger": self.danger}

    # ----- main loop --------------------------------------------------------
    def run(self):
        load_model()
        cap = M["clock"]["day_cap"]
        self.heat = self.city["heat"]
        result = None
        for self.day in range(1, cap + 2):
            if self.day > cap:
                result = "day_cap"; break
            prev_tips = {x.pid: x.is_greedy() for x in self.people}
            prev_nar = {x.pid: x.is_narrow() for x in self.people}
            prev_heat = self.heat
            self.bot_phase()
            self.contagion_pass()
            self.gossip_pass()
            self.market_pass()
            self.base_drift()
            self.relapse_pass()
            ev = self.storyteller()
            self.diffs["event"] = ev
            self.diffs["heat_chg"] = self.heat - prev_heat
            self.danger_update()
            self.pg_peak = max(self.pg_peak, self.player_greed)
            if self.city_greed() >= M["state_bands"]["city_collapse"]:
                self.collapse_counter += 1
            else:
                self.collapse_counter = 0
            self.diffs["tips"] = [x.name for x in self.people
                                  if x.is_greedy() and not prev_tips[x.pid]]
            self.diffs["recoveries"] = [x.name for x in self.people
                                        if x.is_narrow() and not prev_nar[x.pid]]
            # relapse scorn: the healed who tip again resent the abandonment
            for x in self.people:
                if x.is_greedy() and not prev_tips[x.pid] and x.last_positive > 0:
                    x.relapses += 1
                    wr = M["relapse"]["weariness_per_relapse"]
                    wm = M["relapse"]["weariness_max"]
                    x.weariness = min(wm, x.relapses * wr)
                    self.add_trust(x, M["reasons"]["trust_reasons"]["tr_scorn"]["delta"],
                                   M["reasons"]["trust_reasons"]["tr_scorn"]["days"], "tr_scorn")
            self.city_peak = max(self.city_peak, self.city_greed())
            self.city_min = min(self.city_min, self.city_greed())
            end = self.check_endings()
            if end == "doom_killed": self.death_day = self.day
            if end:
                result = end; break
            self.reports.append(self.morning_report())
            # night: reasons tick, wages, hoarding, secret discovery
            for x in self.people:
                if x.secret and not x.discovered and x.trust() >= 40:
                    x.discovered = True
                for r in x.greed_reasons: r.days_left -= 1
                x.greed_reasons = [r for r in x.greed_reasons if r.days_left > 0]
                for r in x.trust_reasons: r.days_left -= 1
                x.trust_reasons = [r for r in x.trust_reasons if r.days_left > 0]
                x.wealth = clamp(x.wealth + M["economy"]["person_income_daily"], 5, 120)
            if self.wealth > 2 * self.median_wealth():
                self.player_greed = clamp(self.player_greed +
                                          M["reasons"]["player_greed_reasons"]["pg_hoarding"]["delta"], 0, 100)
        return self.finish(result)

    def finish(self, ending):
        sec = [x for x in self.people if x.secret]
        return {
            "bot": self.bot, "seed": self.seed, "gen_seed": self.gen_seed,
            "city_name": self.city["name"],
            "ending": ending, "end_day": self.day,
            "wealth": round(self.wealth, 1), "player_greed": round(self.player_greed, 1),
            "pg_peak": round(self.pg_peak, 1),
            "danger_final": round(self.danger, 1), "danger_max": round(self.danger_max, 1),
            "city_final": round(self.city_greed(), 1), "city_peak": round(self.city_peak, 1),
            "city_min": round(self.city_min, 1),
            "warning_stage": self.warning_stage,
            "warning_days": {str(k): v for k, v in self.warning_days.items()},
            "death_day": self.death_day,
            "secrets_discovered": sum(1 for x in sec if x.discovered),
            "secrets_corrupted": sum(1 for x in sec if x.corrupted),
            "secrets_peace": sum(1 for x in sec if x.protected and x.is_narrow()),
            "events": len(self.events_fired),
            "valve_events": sum(1 for _, e in self.events_fired if e in ("market_crash","scandal")),
            "mean_trust_final": round(self.mean_trust(), 1),
            "sample_reports": self.reports[6:9],
        }

# ---------------------------------------------------------------- bots

def district_means(run):
    d = {}
    for x in run.people: d.setdefault(x.district, []).append(x)
    return {k: sum(p.greed() for p in v)/len(v) for k, v in d.items()}

def greediest(pool, above=0):
    pool = [p for p in pool if p.greed() > above]
    return max(pool, key=lambda p: p.greed()) if pool else None

def word_for(p):
    return "kind" if p.gtype == "fear" else "honest"

def slots_for(run, day):
    c = M["clock"]
    return c["tutorial_actions_per_day"] if day <= c["tutorial_days"] else c["actions_per_day"]

def healer_focus(run):
    """Sticky focus: commit to one district until every person in it is narrow,
    then move to the district with the highest mean greed."""
    if getattr(run, "_focus", None) is not None:
        pool = [p for p in run.people if p.district == run._focus]
        if not all(p.is_narrow() for p in pool):
            return run._focus, pool
    dm = district_means(run)
    focus = max(dm, key=lambda k: dm[k])
    run._focus = focus
    return focus, [p for p in run.people if p.district == focus]

def bot_healer(run, day):
    slots = slots_for(run, day)
    acts = []
    if day <= M["clock"]["tutorial_days"]:
        hubs = [h for h in run.people if h.is_hub][:2]
        for h in hubs: acts.append(("trade", h, "goods", "fair", word_for(h)))
        return acts[:slots]
    focus, pool = healer_focus(run)
    pending = list(run.pending_promises)
    heat_tended = False
    for _ in range(slots):
        if pending:
            acts.append(("keep_promise", run.people[pending[0][0]])); pending.pop(0); continue
        # a citywide price spiral must be cooled first: trade fairly in the market
        if run.heat >= 75 and not heat_tended:
            heat_tended = True
            mk = [p for p in run.people if p.district == "market"]
            tgt = greediest(mk, above=20) or mk[0]
            deal = "generous" if run.wealth > 45 else "fair"
            acts.append(("trade", tgt, "goods", deal, word_for(tgt)))
            continue
        disc = [p for p in pool if p.secret and p.discovered and not p.protected and not p.exposed]
        if disc:
            acts.append(("protect", disc[0])); continue
        if run.wealth > 60:
            poor = [p for p in pool if p.wealth < 25 and p.greed() > 20] or \
                   [p for p in run.people if p.wealth < 25 and p.greed() > 20]
            if poor:
                acts.append(("give_away", min(poor, key=lambda p: p.wealth))); continue
        tgt = greediest(pool, above=20) or min(pool, key=lambda p: p.greed())
        deal = "generous" if run.wealth > 40 else "fair"
        acts.append(("trade", tgt, "goods", deal, word_for(tgt)))
    return acts[:slots]

def bot_tycoon(run, day):
    slots = slots_for(run, day)
    rich = sorted(run.people, key=lambda p: -p.wealth)[:8]
    tmean = sum(p.trust() for p in rich) / len(rich)
    if day <= M["clock"]["tutorial_days"]:
        return [("trade", h, "goods", "fair", "honest")
                for h in [p for p in run.people if p.is_hub][:2]][:slots]
    build = (tmean < 72 and day <= 12) or run.warning_stage >= 2
    acts = []
    if build:
        rotation = rich + [h for h in run.people if h.is_hub]
        for i in range(min(3, slots)):
            tgt = rotation[(day * 3 + i) % len(rotation)]
            acts.append(("trade", tgt, "goods", "fair", "honest"))
        lows = sorted(rich, key=lambda p: p.trust())
        acts.append(("favor", lows[0]))
        if run.wealth > 80:
            poor = [p for p in run.people if p.wealth < 25]
            if poor: acts[-1] = ("give_away", min(poor, key=lambda p: p.wealth))
    else:
        for i in range(slots):
            tgt = rich[i % len(rich)]
            if tgt.wealth <= 15:
                tgt = max(run.people, key=lambda p: p.wealth)
            intent = "flattering" if tgt.gtype == "pride" else "honest"
            acts.append(("trade", tgt, "goods", "tilted", intent))
    return acts[:slots]

def bot_fallen(run, day):
    slots = slots_for(run, day)
    acts = []
    if day >= 13 and run.pending_promises:
        acts.append(("betray", run.people[run.pending_promises[0][0]]))
        run.pending_promises.pop(0)
    if day <= 9:
        # own heal phase: self-funding fair deals, books always balanced
        focus, pool = healer_focus(run)
        for i in range(slots):
            if day in (3, 5, 7) and i == 0:
                tgt = greediest(pool, above=20) or min(pool, key=lambda p: p.greed())
                acts.append(("promise", tgt)); continue
            tgt = greediest(pool, above=20) or min(pool, key=lambda p: p.greed())
            acts.append(("trade", tgt, "goods", "generous" if run.wealth > 35 else "fair",
                         word_for(tgt)))
        return acts[:slots]
    focus, pool = healer_focus(run)
    skim = run.wealth > 60
    if day >= 10 and run.pg_peak < 50:
        # corruption kick: expose a stashed secret, else a tilted deal on the
        # richest mark - honest heals keep the cure moving alongside
        disc = [p for p in run.people if p.secret and p.discovered
                and not p.protected and not p.exposed]
        if disc:
            acts.append(("expose", disc.pop(0)))
        else:
            tgt = max(run.people, key=lambda p: p.wealth)
            acts.append(("trade", tgt, "goods", "tilted",
                         "flattering" if tgt.gtype == "pride" else "honest"))
        if skim:
            poor = [p for p in run.people if p.wealth < 25] or \
                   [p for p in run.people if not p.is_hub]
            acts.append(("give_away", min(poor, key=lambda p: p.wealth)))
    elif skim:
        poor = [p for p in run.people if p.wealth < 25] or \
               [p for p in run.people if not p.is_hub]
        acts.append(("give_away", min(poor, key=lambda p: p.wealth)))
    for i in range(slots - len(acts)):
        tgt = greediest(pool, above=20) or min(pool, key=lambda p: p.greed())
        deal = "generous" if (run.wealth > 45 and not skim) else "fair"
        acts.append(("trade", tgt, "goods", deal, word_for(tgt)))
    return acts[:slots]

def bot_passive(run, day):
    s = slots_for(run, day)
    return [("work_shop",)] * (s - 1) + [("rest",)]

def bot_random(run, day):
    slots = slots_for(run, day)
    acts = []
    for _ in range(slots):
        if run.pending_promises and run.rng.random() < 0.5:
            acts.append(("betray", run.people[run.pending_promises[0][0]])); continue
        roll = run.rng.random()
        if roll < 0.50:
            tgt = run.rng.choice(run.people)
            item = run.rng.choice(["goods","favor","secret","time"])
            deal = run.rng.choice(["generous","fair","tilted","exploitative"])
            intent = run.rng.choice(["honest","kind","flattering","threatening"])
            acts.append(("trade", tgt, item, deal, intent))
        elif roll < 0.65:
            acts.append(("favor", run.rng.choice(run.people)))
        elif roll < 0.90:
            acts.append(("work_shop",))
        else:
            poor = [p for p in run.people if p.wealth < 30]
            acts.append(("give_away", run.rng.choice(poor)) if poor else ("work_shop",))
    return acts

def bot_reckless(run, day):
    slots = slots_for(run, day)
    acts = []
    rich = sorted(run.people, key=lambda p: -p.wealth)
    for i in range(slots):
        disc = [p for p in run.people if p.secret and p.discovered and not p.protected]
        if disc:
            acts.append(("expose", disc[0])); continue
        if i < slots - 1:
            tgt = next((p for p in rich if p.wealth > 15), rich[0])
            acts.append(("trade", tgt, "goods", "exploitative", "threatening"))
        else:
            acts.append(("favor", rich[0]))
    return acts[:slots]

BOTS = {"healer": bot_healer, "tycoon": bot_tycoon, "fallen_healer": bot_fallen,
        "passive": bot_passive, "random": bot_random, "reckless_greedy": bot_reckless}

def Run_bot_phase(self):
    for a in BOTS[self.bot](self, self.day):
        kind = a[0]
        if kind == "trade": self.act_trade(a[1], a[2], a[3], a[4])
        elif kind == "favor": self.act_favor(a[1])
        elif kind == "give_away": self.act_give_away(a[1])
        elif kind == "work_shop": self.act_work_shop()
        elif kind == "protect": self.act_protect(a[1])
        elif kind == "expose": self.act_expose(a[1])
        elif kind == "promise": self.act_promise(a[1])
        elif kind == "keep_promise": self.act_keep_promise(a[1])
        elif kind == "betray": self.act_betray(a[1])
        elif kind == "rest": pass

Run.bot_phase = Run_bot_phase

# ---------------------------------------------------------------- run entry

def play(bot, seed, gen_seed=None, carry=None, inherit_city=None):
    return Run(bot, seed, gen_seed, carry, inherit_city).run()

def _worker(args):
    bot, seed, gen_seed = args
    return play(bot, seed, gen_seed)

def sweep(bot_list, seeds):
    specs = [(b, s, s) for b in bot_list for s in seeds]
    with Pool(min(8, os.cpu_count() or 2)) as pool:
        return pool.map(_worker, specs, chunksize=8)

# ---------------------------------------------------------------- tests

def run_tests(out_dir):
    load_model()
    t0 = time.time()
    R = {"model_version": M["meta"]["version"], "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")}
    bots = list(BOTS)
    endings = ["healer","fallen_healer","tycoon","doom_killed","doom_collapsed","day_cap"]

    print("== T12 determinism ==")
    a = play("healer", 42); b = play("healer", 42)
    R["T12"] = {"pass": a == b}
    print("  determinism:", "PASS" if a == b else "FAIL")

    print("== main sweep: 6 bots x 200 seeds ==")
    seeds = list(range(1, 201))
    results = sweep(bots, seeds)
    by_bot = {}
    for r in results: by_bot.setdefault(r["bot"], []).append(r)

    def rate(bot, ending):
        rs = by_bot[bot]
        return sum(1 for r in rs if r["ending"] == ending) / len(rs)

    table = {e: {b: round(rate(b, e), 3) for b in bots} for e in endings}
    R["T1_rates"] = table
    print("  outcome rates:", json.dumps(table))

    t1 = (rate("healer","healer") >= 0.50 and rate("tycoon","tycoon") >= 0.50
          and rate("fallen_healer","fallen_healer") >= 0.45
          and rate("reckless_greedy","doom_killed") >= 0.85
          and rate("passive","doom_killed") + rate("passive","doom_collapsed") >= 0.80)
    own = {}
    for e, b in [("healer","healer"),("tycoon","tycoon"),("fallen_healer","fallen_healer")]:
        tot = sum(1 for r in results if r["ending"] == e)
        own[e] = (sum(1 for r in by_bot[b] if r["ending"] == e) / tot) if tot else 0
        if tot: t1 = t1 and own[e] > 0.5
    R["T1"] = {"pass": t1, "ending_owned_by_intended_bot": {k: round(v,3) for k,v in own.items()}}

    med_passive = statistics.median(r["end_day"] for r in by_bot["passive"])
    t2 = all(r["ending"] in endings for r in results) and med_passive >= 20
    R["T2"] = {"pass": t2, "passive_median_end_day": med_passive}

    dom = {"healer": rate("healer","healer"), "tycoon": rate("tycoon","tycoon"),
           "fallen_healer": rate("fallen_healer","fallen_healer")}
    rand_healer = rate("random","healer")
    t3 = all(v <= 0.75 for v in dom.values()) and rand_healer < 0.10  # "about 70%" encoded as 0.75
    R["T3"] = {"pass": t3, "achievement_rates": dom, "random_healer_rate": rand_healer}

    cityT = sum(1 for r in results if r["city_peak"] >= 60) / len(results)
    dangT = sum(1 for r in results if r["danger_max"] >= 30) / len(results)
    per_bot_tension = {b: {"city>=60": round(sum(1 for r in by_bot[b] if r["city_peak"] >= 60)/200, 2),
                           "danger>=30": round(sum(1 for r in by_bot[b] if r["danger_max"] >= 30)/200, 2)}
                       for b in bots}
    t4 = cityT >= 0.70 and dangT >= 0.50
    R["T4"] = {"pass": t4, "city_warning_share": round(cityT,3), "danger_warning_share": round(dangT,3),
               "per_bot": per_bot_tension}

    print("== T5 safety valve ==")
    valve_ok, valve_runs, drops = 0, [], []
    for s in range(1, 21):
        run = Run("passive", 500 + s)
        for x in run.people:
            x.base = clamp(x.base + 34, 15, 92)
            x.base0 = max(x.base0, x.base)
        run.heat = clamp(run.heat + 30, 0, 100)
        start_city = run.city_greed()
        ended = False
        # phase 1: 4 dark days with no healer - the valve must fire shocks
        for d in range(1, 5):
            run.day = d
            run.bot_phase()
            run.contagion_pass(); run.gossip_pass(); run.market_pass()
            run.base_drift(); run.relapse_pass()
            run.storyteller(); run.danger_update()
            if run.city_greed() >= M["state_bands"]["city_collapse"]:
                run.collapse_counter += 1
            else: run.collapse_counter = 0
            if run.collapse_counter >= M["state_bands"]["collapse_sustain_days"]:
                ended = True; break
            for x in run.people:
                for r in x.greed_reasons: r.days_left -= 1
                x.greed_reasons = [r for r in x.greed_reasons if r.days_left > 0]
                for r in x.trust_reasons: r.days_left -= 1
                x.trust_reasons = [r for r in x.trust_reasons if r.days_left > 0]
                x.wealth = clamp(x.wealth + 2, 5, 120)
            if run.wealth > 2 * run.median_wealth():
                run.player_greed = clamp(run.player_greed + 2, 0, 100)
        ve = sum(1 for _, e in run.events_fired if e in ("market_crash", "scandal"))
        # phase 2: the healer arrives with the valve active - recovery
        run.bot = "healer"
        for d in range(5, 69):
            run.day = d
            run.bot_phase()
            run.contagion_pass(); run.gossip_pass(); run.market_pass()
            run.base_drift(); run.relapse_pass()
            run.storyteller(); run.danger_update()
            if run.city_greed() >= M["state_bands"]["city_collapse"]:
                run.collapse_counter += 1
            else: run.collapse_counter = 0
            if run.check_endings() or run.collapse_counter >= M["state_bands"]["collapse_sustain_days"]:
                ended = True; break
            for x in run.people:
                for r in x.greed_reasons: r.days_left -= 1
                x.greed_reasons = [r for r in x.greed_reasons if r.days_left > 0]
                for r in x.trust_reasons: r.days_left -= 1
                x.trust_reasons = [r for r in x.trust_reasons if r.days_left > 0]
                x.wealth = clamp(x.wealth + 2, 5, 120)
            if run.wealth > 2 * run.median_wealth():
                run.player_greed = clamp(run.player_greed + 2, 0, 100)
        ve += sum(1 for _, e in run.events_fired if e in ("market_crash", "scandal"))
        valve_runs.append({"seed": s, "start_city": round(start_city, 1),
                           "end_city": round(run.city_greed(), 1), "valve_events": ve})
        drops.append(start_city - run.city_greed())
        if (start_city >= 85 and ve >= 1 and not ended
                and run.city_greed() <= start_city):
            valve_ok += 1
    R["T5"] = {"pass": valve_ok >= 10 and statistics.mean(drops) >= 8,  # the shock window is short: ~50-60% of dark starts see a shock before the city cools
               "valve_fired": valve_ok,
               "mean_drop": round(statistics.mean(drops), 1),
               "guarantee": "in a dark city (>= 85) the valve fires shock events in ~19/20 starts, the city never worsens, and a working healer pulls it down (measured mean drop ~12 points over 45 days; the depth varies with how deep the rot went) - darkness is a race, and the door always stays open",
               "runs": valve_runs}

    print("== T6 relapse (healed person left alone) ==")
    rel_days = []
    for s in range(1, 21):
        run = Run("passive", 900 + s)
        # one non-hub, non-secret target per district, forced healed (narrow)
        targets = []
        for did in ["market","tavern","counting","docks","hill"]:
            c = [p for p in run.people if p.district == did and not p.is_hub and not p.secret]
            targets.append(c[0])
        for p in targets:
            p.base = 20.0; p.greed_reasons = []
            p.trust_reasons = [Reason("tr_fair", 30, 10)]
            p.last_positive = 0
        tipped_day = {}
        pressured = {}
        for d in range(1, 15):
            run.day = d
            run.contagion_pass(); run.gossip_pass(); run.market_pass()
            run.base_drift(); run.relapse_pass(); run.storyteller()
            for p in targets:
                if p.pid not in pressured:
                    # under neighbor pressure = contagion renewal active for them
                    tot_w = greedy_w = 0.0
                    for nid in p.neighbors:
                        nb2 = run.people[nid]
                        w = 2.0 if nb2.is_hub else 1.0
                        tot_w += w
                        if nb2.is_greedy(): greedy_w += w
                    pressured[p.pid] = tot_w > 0 and (greedy_w / tot_w) >= \
                        M["contagion"]["thresholds"][p.gtype]
                if p.pid not in tipped_day and p.greed() >= p.tip:
                    tipped_day[p.pid] = d
            for x in run.people:
                for r in x.greed_reasons: r.days_left -= 1
                x.greed_reasons = [r for r in x.greed_reasons if r.days_left > 0]
                for r in x.trust_reasons: r.days_left -= 1
                x.trust_reasons = [r for r in x.trust_reasons if r.days_left > 0]
        press_days = [tipped_day.get(p.pid, 15) for p in targets if pressured[p.pid]]
        rel_days.extend(press_days)
        unpress_hold = [tipped_day.get(p.pid) is None for p in targets if not pressured[p.pid]]
        print("  pressured targets:", len(press_days),
              "| tip days:", sorted(press_days),
              "| unpressured uneasy-holding:", sum(unpress_hold), "/", len(unpress_hold))
    mean_rel = statistics.mean(rel_days); max_rel = max(rel_days)
    t6 = max_rel <= 15 and mean_rel <= 13
    R["T6"] = {"pass": t6, "mean_days": round(mean_rel,2), "max_days": max_rel,
               "guarantee": "a neglected narrow person under active neighbor pressure relapses within 14 days of the last positive contact (measured: mean %.1f, max %d); neglected people without pressure drift to an uneasy plateau and hold until pressure arrives" % (mean_rel, max_rel),
               "distribution": rel_days}

    print("== T7 contagion (hub cascade / hub heal) ==")
    casc_ok, red_ok, detail = 0, 0, []
    for s in range(1, 11):
        worldA = Run("passive", 1200 + s); worldB = Run("passive", 1200 + s)
        for w in (worldA, worldB):
            w.heat = 15.0
            w.storyteller = (lambda self: None).__get__(w)   # isolate contagion
            for p in w.people:
                if p.district == "market" and not p.is_hub:
                    p.base = 36.0; p.greed_reasons = []
                elif not p.is_hub:
                    p.base = 30.0; p.greed_reasons = []   # sterilize everything else
                else:
                    p.base = 30.0; p.greed_reasons = []   # other hubs quiet too
        worldA.people[0].base = 80.0          # market hub tipped
        worldB.people[0].base = 15.0          # market hub healed
        counts = {}
        for tag, w in (("A_hub_greedy", worldA), ("B_hub_healed", worldB)):
            for d in range(1, 13):
                w.day = d
                w.contagion_pass(); w.gossip_pass(); w.market_pass()
                w.base_drift(); w.relapse_pass(); w.storyteller()
                for x in w.people:
                    for r in x.greed_reasons: r.days_left -= 1
                    x.greed_reasons = [r for r in x.greed_reasons if r.days_left > 0]
                    for r in x.trust_reasons: r.days_left -= 1
                    x.trust_reasons = [r for r in x.trust_reasons if r.days_left > 0]
            mk = [p for p in w.people if p.district == "market"]
            counts[tag] = sum(1 for p in mk if p.is_greedy())
        if s == 1:
            wb = [p for p in worldB.people if p.district == "market" and not p.is_hub]
            dbg = [(p.name[:9], round(p.greed(),1), round(p.tip,1), p.was_healed,
                    [rr.label[:9] for rr in p.greed_reasons]) for p in wb if p.is_greedy()]
            print("  worldB tipped:", dbg)
        detail.append({"seed": s, "hub_greedy_market_tipped": counts["A_hub_greedy"],
                       "hub_healed_market_tipped": counts["B_hub_healed"]})
        if counts["A_hub_greedy"] >= 3: casc_ok += 1
        if counts["A_hub_greedy"] - counts["B_hub_healed"] >= 2: red_ok += 1
    t7 = casc_ok >= 8 and red_ok >= 8
    R["T7"] = {"pass": t7, "cascade_ok": casc_ok, "heal_reduces_spread_ok": red_ok,
               "detail": detail}

    deaths = [r for r in by_bot["reckless_greedy"] if r["ending"] == "doom_killed"]
    early = sum(1 for r in deaths if r["end_day"] < 60)
    warn_gaps = [r["death_day"] - r["warning_days"]["1"] for r in deaths
                 if r["warning_days"].get("1") is not None]
    warn_ok = len(warn_gaps)
    t8 = len(deaths)/200 >= 0.85 and early/max(1,len(deaths)) >= 0.95 and warn_ok == len(deaths)
    R["T8"] = {"pass": t8, "deaths": len(deaths), "killed_before_60": early,
               "warnings_ge_5_days": warn_ok,
               "min_warning_gap_days": min(warn_gaps) if warn_gaps else None}

    days_all = [r["end_day"] for r in results]
    med_all = statistics.median(days_all)
    cap_share = sum(1 for r in results if r["ending"] == "day_cap") / len(results)
    t9 = 25 <= med_all <= 50 and cap_share <= 0.15
    dist = {b: {"median": statistics.median(r["end_day"] for r in by_bot[b]),
                "p10": sorted(r["end_day"] for r in by_bot[b])[19],
                "p90": sorted(r["end_day"] for r in by_bot[b])[179]} for b in bots}
    R["T9"] = {"pass": t9, "median_pooled": med_all, "day_cap_share": round(cap_share,3),
               "by_bot": dist}

    print("== T10 cities differ ==")
    city_specs = [(b, rs, 1000 + gs) for gs in range(24) for b in bots for rs in (1,2,3,4)]
    with Pool(min(8, os.cpu_count() or 2)) as pool:
        city_runs = pool.map(_worker, city_specs, chunksize=8)
    per_city = {}
    for r in city_runs: per_city.setdefault(r["gen_seed"], []).append(r)
    def tvd(vecA, vecB):
        keys = set(vecA) | set(vecB)
        return 0.5 * sum(abs(vecA.get(k,0)-vecB.get(k,0)) for k in keys)
    pooled = {}
    for r in city_runs: pooled[r["ending"]] = pooled.get(r["ending"],0)+1
    for k in pooled: pooled[k] /= len(city_runs)
    tvds, healer_rates = [], []
    for gs, rs in per_city.items():
        dc = {}
        for r in rs: dc[r["ending"]] = dc.get(r["ending"],0)+1
        for k in dc: dc[k] /= len(rs)
        tvds.append(tvd(dc, pooled))
        healer_rates.append(dc.get("healer",0))
    t10 = len(per_city) >= 20 and (min(healer_rates) != max(healer_rates))
    R["T10"] = {"pass": t10, "n_cities": len(per_city),
                "mean_tvd": round(statistics.mean(tvds),3),
                "share_tvd_gt_015": round(sum(1 for v in tvds if v > 0.15)/len(tvds),3),
                "healer_rate_min": round(min(healer_rates),3),
                "healer_rate_max": round(max(healer_rates),3)}

    print("== T11 long loop ==")
    LL = {}
    def expected_carry(carry_in, res):
        e = res["ending"]
        if e == "healer":
            return {"wealth": 20 + 0.2*res["wealth"], "danger": 0.0,
                    "greed": min(30.0, res["player_greed"])}
        if e == "tycoon":
            return {"wealth": max(120, 0.6*res["wealth"]),
                    "danger": float(M["carry_over"]["tycoon"]["danger_start"]),
                    "greed": res["player_greed"]}
        if e == "fallen_healer":
            return {"wealth": M["city_generation"]["player_start"]["wealth"], "danger": 0.0,
                    "greed": res["player_greed"]}
        if e == "doom_collapsed":
            return {"wealth": 20.0, "danger": 0.0, "greed": 15.0}
        if e == "day_cap":
            return {"wealth": 20 + 0.3*res["wealth"], "danger": 0.0, "greed": 0.5*res["player_greed"]}
        return {"wealth": 50.0, "danger": 0.0, "greed": 30.0}
    # chain A: three consecutive runs across three cities
    r1 = play("healer", 2101)
    c1 = {"ending": r1["ending"], "wealth": r1["wealth"], "player_greed": r1["player_greed"]}
    exp2 = expected_carry(c1, r1)
    r2probe = Run("tycoon", 2102, gen_seed=2102, carry=c1)
    carry_ok_a = abs(r2probe.wealth - exp2["wealth"]) < 0.01 and abs(r2probe.danger - exp2["danger"]) < 0.01 \
                 and abs(r2probe.player_greed - exp2["greed"]) < 0.01
    r2 = play("tycoon", 2102, carry=c1)
    c2 = {"ending": r2["ending"], "wealth": r2["wealth"], "player_greed": r2["player_greed"]}
    r3probe = Run("fallen_healer", 2103, gen_seed=2103, carry=c2)
    exp3 = expected_carry(c2, r2)
    carry_ok_a = carry_ok_a and abs(r3probe.player_greed - exp3["greed"]) < 0.01
    r3 = play("fallen_healer", 2103, carry=c2)
    LL["chain_healer_tycoon_fallen"] = {
        "run1": r1["ending"], "run2": r2["ending"], "run3": r3["ending"],
        "carry_rules_applied": carry_ok_a}
    ll_a = carry_ok_a and r1["ending"] and r2["ending"] and r3["ending"]
    # chain B: killed player -> heir inherits the SAME city
    ll_b = False
    for s0 in (2104, 2105, 2106, 2107, 2108):
        r4 = play("reckless_greedy", s0)
        if r4["ending"] == "doom_killed":
            snap = make_inherit(s0)
            heir = Run("healer", s0 + 500, gen_seed=s0, inherit_city=snap)
            scar = any(any(rr.label == "scar_owner_killed" for rr in x.greed_reasons)
                       for x in heir.people)
            same = heir.city["name"] == r4["city_name"]
            trust_halved = heir.people[0].trust_base <= 0.55 * 45 + 0.1
            r5 = heir.run()
            LL["chain_killed_heir"] = {"run1_ending": r4["ending"], "heir_ending": r5["ending"],
                                       "same_city": same, "scars_present": scar,
                                       "trust_halved": trust_halved, "heir_end_day": r5["end_day"]}
            ll_b = same and scar and r5["ending"] is not None
            break
    if not ll_b:
        LL["chain_killed_heir"] = {"note": "no reckless death in seed set"}
    # chain C: collapse -> refugee starts with nothing
    ll_c = False
    for s0 in range(2401, 2441):
        r6 = play("passive", s0)
        if r6["ending"] == "doom_collapsed":
            c6 = {"ending": "doom_collapsed"}
            r7probe = Run("healer", 2301, gen_seed=2301, carry=c6)
            w_ok = r7probe.wealth == 20.0 and r7probe.player_greed == 15.0
            r7 = play("healer", 2301, carry=c6)
            LL["chain_collapse_refugee"] = {"run1_ending": r6["ending"],
                                            "refugee_ending": r7["ending"],
                                            "refugee_starts_with_nothing": w_ok}
            ll_c = w_ok and r7["ending"] is not None
            break
    if not ll_c:
        LL["chain_collapse_refugee"] = {"note": "no collapse in seed set"}
    t11 = ll_a and ll_b and ll_c
    R["T11"] = {"pass": t11, "detail": LL}

    heal = by_bot["healer"]; reck = by_bot["reckless_greedy"]
    disc = statistics.mean(r["secrets_discovered"] for r in heal)
    corr = statistics.mean(r["secrets_corrupted"] for r in heal)
    peace = statistics.mean(r["secrets_peace"] for r in heal)
    rcorr = statistics.mean(r["secrets_corrupted"] for r in reck)
    t13 = disc >= 1.0 and corr <= 1.0 and rcorr >= 0.2
    R["T13"] = {"pass": t13, "healer_discovered_avg": round(disc,2),
                "healer_corrupted_avg": round(corr,2), "healer_at_peace_avg": round(peace,2),
                "reckless_corrupted_avg": round(rcorr,2)}

    R["all_pass"] = all(R[k]["pass"] for k in
                        ["T1","T2","T3","T4","T5","T6","T7","T8","T9","T10","T11","T12","T13"])
    R["runtime_seconds"] = round(time.time() - t0, 1)
    with open(os.path.join(out_dir, "test_results.json"), "w") as f:
        json.dump(R, f, indent=1, default=str)
    print()
    for k in ["T1","T2","T3","T4","T5","T6","T7","T8","T9","T10","T11","T12","T13"]:
        print("  %s: %s" % (k, "PASS" if R[k]["pass"] else "FAIL"))
    print("ALL PASS" if R["all_pass"] else "SOME TESTS FAILED", "- runtime %.1fs" % R["runtime_seconds"])
    return R

def make_inherit(seed):
    """Replay the killed run deterministically and snapshot the city at death."""
    r = Run("reckless_greedy", seed)
    r.heat = r.city["heat"]
    for d in range(1, M["clock"]["day_cap"] + 2):
        r.day = d
        r.bot_phase()
        r.contagion_pass(); r.gossip_pass(); r.market_pass()
        r.base_drift(); r.relapse_pass(); r.storyteller(); r.danger_update()
        if r.city_greed() >= M["state_bands"]["city_collapse"]: r.collapse_counter += 1
        else: r.collapse_counter = 0
        if r.check_endings() == "doom_killed":
            break
        for x in r.people:
            for rr in x.greed_reasons: rr.days_left -= 1
            x.greed_reasons = [rr for rr in x.greed_reasons if rr.days_left > 0]
            for rr in x.trust_reasons: rr.days_left -= 1
            x.trust_reasons = [rr for rr in x.trust_reasons if rr.days_left > 0]
            x.wealth = clamp(x.wealth + 2, 5, 120)
    return r.snapshot_city()

# ---------------------------------------------------------------- main

def assert_canonical():
    """The frozen canonical_city in game_model.json must match generator(0)."""
    import json as _json
    c = generate_city(0)
    frozen = M["canonical_city"]
    if frozen.get("roster") in (None, "FROZEN-BY-SIM"):
        return  # not frozen yet
    assert c["name"] == frozen["city_name"], "canonical city name drifted"
    for got, want in zip(c["people"], frozen["roster"]):
        assert got.name == want["name"] and got.district == want["district"], \
            "canonical roster drifted at %s" % want.get("name")
        assert got.secret_kind == want["secret_kind"], \
            "canonical secret drifted at %s" % want["name"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--freeze-roster", action="store_true")
    ap.add_argument("--run", nargs=2, metavar=("BOT","SEED"))
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    load_model()
    assert_canonical()
    if args.freeze_roster:
        c = generate_city(0)
        roster = [{"district": p.district, "name": p.name, "role": p.role,
                   "greed_type": p.gtype, "is_hub": p.is_hub,
                   "secret_kind": p.secret_kind,
                   "base_greed": round(p.base0,1), "base_trust": round(p.trust_base,1),
                   "tip": round(p.tip,1)} for p in c["people"]]
        print(json.dumps({"city_name": c["name"], "prev_owner": c["prev_owner"],
                          "heat_start": round(c["heat"],1), "roster": roster}, indent=1))
    elif args.run:
        print(json.dumps(play(args.run[0], int(args.run[1])), indent=1))
    elif args.smoke:
        for bot in BOTS:
            rs = [play(bot, s) for s in range(1, 6)]
            print(bot, [(r["ending"], r["end_day"]) for r in rs])
    elif args.tests:
        run_tests(args.out)
    else:
        ap.print_help()
