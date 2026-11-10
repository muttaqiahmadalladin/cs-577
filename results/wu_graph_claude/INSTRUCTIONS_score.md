# Task: score arguments about a conversation

Your batch file holds conversations between speakers A and B, each with arguments someone else wrote: for four aspects, three reasons why A has more power, three reasons why B has more power, and one rebuttal for each reason.

Rules:
- Read ONLY this file and your batch file. Do not open, list or search any other file or directory, and do not use the web. This is a blind experiment.
- Do NOT decide who has more power. Judge each argument on its own merits. Arguments for A and for B must be held to the same standard.
- Give probabilities between 0 and 1. Be discriminating: unsupported or generic arguments should get low numbers, and well supported ones high numbers.

For each conversation and each aspect (style, content, coordination, engagement), produce:

- `reason`: for each speaker S in A, B and each of that speaker's three reasons, a pair `[valid, grounded]`
  - valid: probability that the reason, if true, is a valid indication that S has more power than the other speaker
  - grounded: probability that the reason is supported by what is actually said in the conversation
- `rebuttal`: for each S and each rebuttal (rebuttal i answers reason i of S), a pair `[valid, grounded]`
  - valid: probability that the rebuttal validly counters its reason
  - grounded: probability that the rebuttal's own claims are supported by the conversation
- `similar`: six integers 1 to 5, for the reason pairs (A1,B1), (A1,B2), (A1,B3), (A2,B2), (A2,B3), (A3,B3), in that order.
  1 = different behaviors and different reasoning; 3 = somewhat similar behaviors and similar reasoning; 5 = the same behavior and very similar reasoning.
- `contra_A`: three integers 1 to 5, for the pairs (A1,A2), (A1,A3), (A2,A3) of reasons for A.
  1 = similar behavior, different reasoning; 2 = different behaviors; 3 = somewhat contradictory behaviors, different reasoning; 5 = contradictory behaviors of the speaker with similar reasoning.
- `contra_B`: the same for the reasons for B.

Output: for each conversation write `/root/wuc/score/<id>.json` exactly like:

{"id": "<id>", "aspects": {
  "style": {"reason": {"A": [[0.8, 0.6], [0.5, 0.2], [0.7, 0.9]], "B": [[..], [..], [..]]},
            "rebuttal": {"A": [[..], [..], [..]], "B": [[..], [..], [..]]},
            "similar": [1, 2, 1, 3, 1, 2], "contra_A": [2, 2, 1], "contra_B": [1, 2, 2]},
  "content": {...}, "coordination": {...}, "engagement": {...}
}}

After writing each file run `python3 /root/wuc/check_score.py <id>` and fix any problem. When all are written run `python3 /root/wuc/check_score.py --batch <your batch file>` and make sure it prints ALL OK. Your final message should be just that output.
