"""The XOR factor graph of Wu et al. (NAACL 2025) as an exact integer program. Needs PuLP (with its bundled CBC).

Variables (binary): x0 = "A has power", x1 = "B has power", then one per reason, rebuttal and relation (98 in total,
laid out as in scripts/convert_released_cache.py).

Objective: maximise the sum of weight * variable, with
  reason    20 * round(P(valid) * P(grounded), 2)
  rebuttal  18 * round(P(valid) * P(rebuttal), 2)
  relation  its score in [0, 1]
The weights 20 and 18 are the values in the released code. `validity` and `grounding` are passed as log-probabilities.

Constraints come from the released rule file, one factor per line:
  XOR  a b          exactly one of the two literals is true (power A / power B; a reason / its rebuttal)
  OR   a b c        at least one literal is true (literals may be negated, written with a minus sign)
  OROUT a .. z out  out is true exactly when at least one input is true (a speaker has power iff one of their reasons holds)

An argument that is not supplied has its variable fixed to 0, and a reason/rebuttal XOR factor is dropped when either
end is missing (used for the "reasons only" variant). Supplying no relations leaves the relation variables free with
zero weight, which makes their factors inactive.

The paper solves the LP relaxation with AD3; this solves the integer program exactly with CBC, and reproduces the
published 54.3% on the released cache. Adapted from quote_power.inference.xor in KrishMay05/nlp_research.
"""
import math
import pulp


def xor(arguments, relations, rules, n_variables=98):
    """Return 'A' or 'B'. arguments: dicts with variable, kind, validity, grounding. relations: dicts with variable, score."""
    if not any(a["kind"] == "reason" for a in arguments): return "A"
    active = {a["variable"] for a in arguments}
    model = pulp.LpProblem("power", pulp.LpMaximize)
    x = [pulp.LpVariable(f"x{i}", 0, 1, cat="Binary") for i in range(n_variables)]
    weights = {a["variable"]: (20 if a["kind"] == "reason" else 18) * round(math.exp(a["validity"] + a["grounding"]), 2) for a in arguments}
    weights.update({r["variable"]: r["score"] for r in relations})
    model += pulp.lpSum(w * x[i] for i, w in weights.items())
    argument_variables = {2 + 24 * a + k for a in range(4) for k in range(12)}
    for v in argument_variables - active: model += x[v] == 0
    for line in rules.splitlines():
        if not line.strip(): continue
        kind, count, *tokens = line.split(); variables = [int(t) for t in tokens]
        assert int(count) == len(variables), "malformed rule line"
        if kind == "XOR" and variables != [1, 2] and any(abs(i) - 1 not in active for i in variables): continue
        literals = [x[i - 1] if i > 0 else 1 - x[-i - 1] for i in variables]
        if kind == "XOR": model += pulp.lpSum(literals) == 1
        elif kind == "OR": model += pulp.lpSum(literals) >= 1
        elif kind == "OROUT":
            *inputs, output = literals
            for v in inputs: model += v <= output
            model += output <= pulp.lpSum(inputs)
        else: raise ValueError(f"unknown factor {kind}")
    if model.solve(pulp.PULP_CBC_CMD(msg=False, threads=1)) != pulp.LpStatusOptimal: raise RuntimeError("CBC did not find an optimum")
    return "A" if pulp.value(x[0]) >= pulp.value(x[1]) else "B"
