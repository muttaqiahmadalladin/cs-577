# Task: write arguments about conversational power

You are given short conversations between two speakers, A and B (sometimes a third speaker C appears). For EACH conversation, do the three steps below and save one JSON file.

Rules:
- Read ONLY this file and your batch file. Do not open, list or search any other file or directory, and do not use the web. The task is a blind experiment.
- Never try to work out which speaker "really" has more power. You must argue both sides with equal effort.
- Process every conversation in the batch. Do not skip any.

## Step 1: aspect summaries
For each of the four aspects, write a summary of that aspect for A and for B, in this exact form (one string):
"<aspect> of A: ...\n<aspect> of B: ..."

Aspect definitions:
- style: Style encompasses the tone, manner, and language used during the conversation. It can range from formal to informal, polite to blunt, friendly to hostile, etc.
- content: Content is the substance or subject matter of the conversation. It includes the topics being discussed, the information exchanged, and the sentence type used.
- coordination: Coordination is how participants manage turn-taking, interruptions, and transitions between topics. It involves maintaining a balance between speaking and listening, ensuring everyone has a chance to contribute.
- engagement: Engagement is the level of interest and involvement of participants in the conversation. Engaging conversations often involve asking questions, sharing personal experiences, and expressing empathy.

## Step 2: reasons
For each aspect, using that aspect's summary, list three reasons why A has more power than B, and three reasons why B has more power than A. Each reason is one sentence.

## Step 3: rebuttals
For every reason from step 2, write one rebuttal: given the conversation and a reason that supports one speaker having more power, argue against that reason in favour of the OTHER speaker having more power. One or two sentences each.
rebuttals["A"][i] rebuts reasons["A"][i] (so it argues for B). rebuttals["B"][i] rebuts reasons["B"][i] (so it argues for A).

## Output
For each conversation write `/root/wuc/gen/<id>.json` (use the conversation's id) with exactly this structure:

{"id": "<id>", "aspects": {
  "style":        {"summary": "...", "reasons": {"A": ["...", "...", "..."], "B": ["...", "...", "..."]}, "rebuttals": {"A": ["...", "...", "..."], "B": ["...", "...", "..."]}},
  "content":      { same shape },
  "coordination": { same shape },
  "engagement":   { same shape }
}}

After writing each file run `python3 /root/wuc/check_gen.py <id>` and fix the file if it reports a problem. When all files are written, run `python3 /root/wuc/check_gen.py --batch <your batch file>` and make sure it prints ALL OK. Your final message should be just the output of that last command.
