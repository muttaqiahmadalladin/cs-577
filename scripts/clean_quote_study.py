#!/usr/bin/env python3
"""Prepare, annotate and evaluate a separately labeled exploratory clean quote study.

No network call occurs unless `collect --execute` is supplied. No human labels are
created by this program. Historical datasets, arguments and scores are read only.
"""
import argparse
import collections
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import sys
import time
import urllib.error
import urllib.request
import urllib.parse

ROOT = Path(__file__).resolve().parents[1]
ASPECTS = ("style", "content", "coordination", "engagement")
SEED = "clean-quote-study-v1-2026-11-17"
FIELDS = ("quote_present", "attribution_correct", "claim_supported",
          "rebuttal_answers_reason", "should_keep")
CHOICES = {"yes", "no", "uncertain"}
POLICY = {
    "status": "retrospective exploratory development; not prospective confirmation",
    "bank": "Terra clean same-span bank selected before filter evaluation",
    "primary_rule": "speaker-bound verbatim contiguous quote AND claim support AND correct attribution; rebuttals also answer their paired reason",
    "uncertainty": "uncertain in required quote/attribution/support (and rebuttal-answer) fields is rejected; holistic should_keep is an independent audit label, not a filter component; report both separately; no automatic adjudication",
    "selection": "do not select thresholds, policies or checker capacity by final role-label accuracy",
    "tie": "A when conditional objectives differ by at most 1e-9 objective units; shared post-audit evaluator",
    "human_gate": "two independent human annotators; model/proxy judgments cannot satisfy this gate",
    "confirmation_gate": "independent human evidence validation and genuinely fresh independently labeled participants/meetings plus a locked meaningful effect and precision target",
}


def jsonl(path):
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def write_jsonl(path, rows):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r, ensure_ascii=False, allow_nan=False) + "\n" for r in rows), encoding="utf-8")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def object_hash(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def context_digest(fixed_contexts):
    """Exact request_digest('fixed', records) algorithm used by Terra collection."""
    return hashlib.sha256(json.dumps(["fixed", fixed_contexts], sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def unique_index(rows, key="id", description="records"):
    result = {}
    for row in rows:
        value = row.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"{description}: nonempty string {key} required")
        if value in result:
            raise ValueError(f"{description}: duplicate {key} {value}")
        result[value] = row
    return result


def expected_score_keys():
    return {f"{a}|{kind}|{s}{i}" for a in ASPECTS for kind in ("rv", "rg", "bv", "bg", "ba") for s in "AB" for i in range(3)} | {
        f"{a}|sim|{i}{j}" for a in ASPECTS for i in range(3) for j in range(i, 3)} | {
        f"{a}|c{s}|{i}{j}" for a in ASPECTS for s in "AB" for i, j in ((0, 1), (0, 2), (1, 2))}


def validate_banks(data, arguments, scores, manifest):
    D = unique_index(data, description="transcripts")
    A = unique_index(arguments, description="arguments")
    S = unique_index(scores, description="scores")
    if not D or set(D) != set(A) or set(D) != set(S):
        raise ValueError("transcript/argument/score IDs must match bijectively")
    rows, crosswalk = [], []
    for id_ in sorted(D, key=lambda x: (int(x) if x.isdigit() else math.inf, x)):
        d, a, s = D[id_], A[id_], S[id_]
        speakers = d["speakers"]
        if not {"A", "B"} <= speakers.keys() or len(set(speakers.values())) != len(speakers):
            raise ValueError(f"{id_}: participant/letter crosswalk must be bijective")
        if d.get("professor") not in "AB" or d["professor"] not in speakers:
            raise ValueError(f"{id_}: professor label must identify a focal participant")
        turns = d["turns_same_span"]
        if not turns or any(t["speaker"] not in speakers or not t["text"].strip() for t in turns):
            raise ValueError(f"{id_}: transcript turn does not match participant crosswalk")
        fingerprint = manifest.get("run_fingerprint")
        if not fingerprint or a.get("run_fingerprint") != fingerprint or s.get("run_fingerprint") != fingerprint:
            raise ValueError(f"{id_}: argument/score fingerprint mismatch")
        answers = s["answers"]
        if set(answers) != expected_score_keys():
            raise ValueError(f"{id_}: exact 168 score keys required")
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not 0 <= v <= 1 for v in answers.values()):
            raise ValueError(f"{id_}: invalid probability")
        if set(a["aspects"]) != set(ASPECTS):
            raise ValueError(f"{id_}: incorrect aspect bank")
        crosswalk.append({"id": id_, "meeting": d["meeting"], "speakers": speakers,
                          "professor_letter": d["professor"], "professor_participant": speakers[d["professor"]],
                          "transcript_sha256": object_hash(turns)})
        for ai, aspect in enumerate(ASPECTS):
            part = a["aspects"][aspect]
            for kind, bank_name in (("reason", "reasons"), ("rebuttal", "rebuttals")):
                if set(part[bank_name]) != set("AB"):
                    raise ValueError(f"{id_}: incorrect side bank")
                for si, side in enumerate("AB"):
                    texts = part[bank_name][side]
                    if len(texts) != 3 or any(not isinstance(t, str) or not t.strip() for t in texts):
                        raise ValueError(f"{id_}: exactly three nonempty arguments per side/kind/aspect required")
                    for i, text in enumerate(texts):
                        rows.append({"argument_id": f"{id_}|{aspect}|{kind}|{side}|{i}", "snippet_id": id_,
                                     "aspect": aspect, "kind": kind, "target_side": side,
                                     "intended_side": side if kind == "reason" else ("B" if side == "A" else "A"),
                                     "index": i, "claim": text,
                                     "paired_reason": part["reasons"][side][i] if kind == "rebuttal" else "",
                                     "variable": 2 + 24 * ai + 3 * si + i + (6 if kind == "rebuttal" else 0),
                                     "transcript_sha256": object_hash(turns), "claim_sha256": object_hash(text)})
    return rows, crosswalk


def stratified_sample(rows, n=96):
    strata = collections.defaultdict(list)
    for row in rows:
        strata[(row["aspect"], row["kind"], row["intended_side"])].append(row)
    if n % len(strata) or any(len(v) < n // len(strata) for v in strata.values()):
        raise ValueError("sample size must balance the aspect/kind/side strata")
    sample = []
    for key, group in sorted(strata.items()):
        ranked = sorted(group, key=lambda r: hashlib.sha256((SEED + r["argument_id"]).encode()).hexdigest())
        sample.extend(ranked[:n // len(strata)])
    return sorted(sample, key=lambda r: hashlib.sha256((SEED + "worksheet" + r["argument_id"]).encode()).hexdigest())


def blind_row(row, transcript):
    view = {k: row[k] for k in ("argument_id", "snippet_id", "aspect", "kind", "intended_side", "claim", "paired_reason")}
    view["transcript_json"] = json.dumps(transcript["turns_same_span"], ensure_ascii=False)
    view.update({k: "" for k in ("annotator_id", "annotator_type", "quote", "quote_speaker", *FIELDS, "comment")})
    return view


def write_csv(path, rows, overwrite=False):
    path = Path(path)
    if path.exists() and not overwrite:
        # A rerun must never overwrite completed human work.
        if read_annotations(path) != rows:
            raise ValueError(f"refusing to replace existing worksheet {path}; choose a new output directory")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def read_annotations(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f, skipinitialspace=True)
            fields = reader.fieldnames or []
            if len(set(k.strip() for k in fields)) != len(fields):
                raise ValueError("CSV has duplicate normalized column names")
            rows = []
            for row in reader:
                if None in row or any(value is None for value in row.values()):
                    raise ValueError("CSV row width differs from header")
                rows.append({key.strip(): value.strip() for key, value in row.items()})
            return rows
    return jsonl(path)


def annotation_complete(row):
    required = FIELDS if row.get("kind") == "rebuttal" else tuple(k for k in FIELDS if k != "rebuttal_answers_reason")
    return bool(row.get("annotator_id")) and row.get("annotator_type") == "human" and all(row.get(k) in CHOICES for k in required) and (
        row.get("quote_present") != "yes" or bool(row.get("quote", "").strip() and row.get("quote_speaker", "").strip()))


def validate_annotation_identity(row, expected, require_case=True, allow_transcript_hash=False):
    """An ID cannot migrate to another claim, kind, side or transcript."""
    for field in ("snippet_id", "aspect", "kind", "intended_side", "claim", "paired_reason"):
        if (require_case and field not in row) or (field in row and row[field] != expected.get(field)):
            raise ValueError(f"{row.get('argument_id')}: immutable {field} mismatch")
    if require_case and "transcript_json" not in row:
        if not allow_transcript_hash or row.get("transcript_sha256") != object_hash(json.loads(expected["transcript_json"])):
            raise ValueError("immutable transcript missing or hash mismatch")
    if "transcript_json" in row:
        try:
            supplied = json.loads(row["transcript_json"])
            canonical = json.loads(expected["transcript_json"])
        except (TypeError, KeyError, json.JSONDecodeError):
            raise ValueError("immutable transcript must be valid canonical JSON") from None
        if supplied != canonical:
            raise ValueError("immutable transcript mismatch")


def annotation_report(first, second, predictions=None, canonical=None, expected_ids=None):
    A = unique_index(first, "argument_id", "first worksheet")
    B = unique_index(second, "argument_id", "second worksheet")
    if not A or set(A) != set(B):
        raise ValueError("worksheet argument IDs must match exactly")
    if expected_ids is not None and set(A) != set(expected_ids):
        raise ValueError("both worksheets must cover the complete frozen annotation packet")
    C = unique_index(canonical, "argument_id", "canonical cases") if canonical is not None else A
    if set(A) - set(C):
        raise ValueError("worksheet argument IDs absent from canonical bank")
    for k in A:
        validate_annotation_identity(A[k], C[k])
        validate_annotation_identity(B[k], C[k])
        turns = json.loads(C[k]["transcript_json"])
        for row in (A[k], B[k]):
            if row.get("quote_present") == "yes" and row.get("quote") and row.get("quote_speaker") and not speaker_bound_quote(row, turns):
                raise ValueError(f"{k}: human quote absent or on wrong speaker")
    identities = []
    for label, rows in (("first", first), ("second", second)):
        types = {r.get("annotator_type") for r in rows if r.get("annotator_type")}
        if types - {"human"}:
            raise ValueError(f"{label}: independent human annotations required; proxy/model labels are not human")
        ids = {r.get("annotator_id") for r in rows if r.get("annotator_id")}
        if len(ids) > 1:
            raise ValueError(f"{label}: worksheet must identify one annotator")
        identities.append(ids)
        for r in rows:
            if any(r.get(k, "") not in CHOICES | {""} for k in FIELDS):
                raise ValueError("judgment must be yes, no, uncertain or blank")
    if identities[0] & identities[1]:
        raise ValueError("two independent annotator identities required")
    counts = [sum(annotation_complete(r) for r in rows) for rows in (first, second)]
    report = {"n": len(A), "first_complete": counts[0], "second_complete": counts[1],
              "ready_for_human_conclusion": counts == [len(A), len(A)], "fields": {},
              "independence": "distinct self-attested human IDs; organizer must verify actual independent people",
              "uncertainty_policy": "uncertain is separate from binary disagreement and never adjudicated automatically"}
    for field in FIELDS:
        pairs = [(A[k].get(field), B[k].get(field)) for k in A if field != "rebuttal_answers_reason" or A[k].get("kind") == "rebuttal"]
        complete = [(a, b) for a, b in pairs if a in CHOICES and b in CHOICES]
        binary = [(a, b) for a, b in complete if a != "uncertain" and b != "uncertain"]
        observed = sum(a == b for a, b in complete) / len(complete) if complete else None
        expected = sum(sum(a == v for a, _ in complete) * sum(b == v for _, b in complete) for v in CHOICES) / len(complete) ** 2 if complete else None
        report["fields"][field] = {"complete_pairs": len(complete), "missing_pairs": len(pairs) - len(complete),
                                   "uncertain_pairs": sum("uncertain" in p for p in complete), "binary_pairs": len(binary),
                                   "agreement_three_value": observed,
                                   "agreement_binary": sum(a == b for a, b in binary) / len(binary) if binary else None,
                                   "cohen_kappa_three_value": (observed - expected) / (1 - expected) if expected is not None and expected < 1 else None,
                                   "disagreements": [k for k in A if A[k].get(field) in CHOICES and B[k].get(field) in CHOICES and A[k][field] != B[k][field]]}
    if predictions is not None:
        P = unique_index(predictions, "argument_id", "checker predictions")
        report["checker_coverage"] = {"predictions_available": len(P), "sample_cases_with_prediction": len(set(A) & set(P)),
                                      "sample_cases_without_prediction": len(set(A) - set(P)), "sample_total": len(A)}
        if canonical is not None and set(P) - set(C):
            raise ValueError("checker prediction IDs absent from canonical bank")
        for k in P:
            expected = C.get(k)
            if expected is None:
                continue  # Uncompared extra predictions still cannot contribute errors.
            validate_annotation_identity(P[k], expected, require_case=True, allow_transcript_hash=True)
            if any(P[k].get(field) not in CHOICES for field in FIELDS):
                raise ValueError("checker judgments must be yes/no/uncertain")
            turns = json.loads(expected["transcript_json"])
            validate_quote_answers([P[k]], [expected], turns)
        for label, H in (("first", A), ("second", B)):
            valid = [k for k in H if annotation_complete(H[k]) and H[k]["should_keep"] in {"yes", "no"} and k in P]
            def machine_keep(k):
                turns = json.loads(H[k]["transcript_json"])
                return strict_keep(P[k], turns)
            valid_yes = [k for k in valid if H[k]["should_keep"] == "yes"]
            valid_no = [k for k in valid if H[k]["should_keep"] == "no"]
            report[label + "_checker_errors"] = {"compared": len(valid), "human_keep": len(valid_yes), "human_reject": len(valid_no),
                                                   "false_rejections": sum(not machine_keep(k) for k in valid_yes),
                                                   "false_acceptances": sum(machine_keep(k) for k in valid_no),
                                                   "human_uncertain": sum(H[k].get("should_keep") == "uncertain" for k in H)}
    return report


def speaker_bound_quote(row, turns):
    quote, speaker = row.get("quote", ""), row.get("quote_speaker", "")
    return bool(isinstance(quote, str) and quote.strip() and speaker and any(t["speaker"] == speaker and quote in t["text"] for t in turns))


def strict_keep(row, turns):
    fields = ("quote_present", "attribution_correct", "claim_supported")
    return speaker_bound_quote(row, turns) and all(row.get(k) == "yes" for k in fields) and (
        row.get("kind") != "rebuttal" or row.get("rebuttal_answers_reason") == "yes")


def validate_quote_answers(answers, expected, turns, allow_reason_blank=False, enforce_strict_keep=True):
    A = unique_index(answers, "argument_id", "quote answers")
    E = unique_index(expected, "argument_id", "expected arguments")
    if set(A) != set(E):
        raise ValueError("quote answer IDs must cover the exact requested argument IDs")
    for id_, row in A.items():
        for field in ("snippet_id", "aspect", "kind", "intended_side", "claim", "paired_reason"):
            if field in row and field in E[id_] and row[field] != E[id_][field]:
                raise ValueError(f"{id_}: immutable {field} changed; annotations must refer to the same argument")
        if any(row.get(k) not in CHOICES for k in FIELDS if not (allow_reason_blank and E[id_]["kind"] == "reason" and k == "rebuttal_answers_reason" and row.get(k) in {None, ""})):
            raise ValueError(f"{id_}: every judgment must be yes/no/uncertain")
        if not isinstance(row.get("quote"), str) or not isinstance(row.get("quote_speaker"), str):
            raise ValueError(f"{id_}: quote and quote_speaker strings required")
        if row.get("quote_present") == "yes" and not speaker_bound_quote(row, turns):
            raise ValueError(f"{id_}: claimed present quote is empty, invented, or attributed to wrong speaker")
        if row.get("quote_present") == "no" and row["quote"]:
            raise ValueError(f"{id_}: absent quote must be empty")
        if enforce_strict_keep and row.get("should_keep") == "yes" and not strict_keep(dict(row, kind=E[id_]["kind"]), turns):
            raise ValueError(f"{id_}: should_keep=yes contradicts the frozen strict quote rule")
    return A


def check_candidate(candidate, old_meetings, old_participants, selected):
    return candidate["meeting"] not in old_meetings and not set(candidate["participants"]) & old_participants and not any(
        candidate["meeting"] == other["meeting"] and candidate["start_segment"] < other["end_segment"] and other["start_segment"] < candidate["end_segment"] for other in selected)


def load_inputs(root=ROOT):
    bank = root / "results/wu_graph_terra"
    paths = {"transcripts": root / "data/icsi_rebuilt_snippets.jsonl", "arguments": bank / "arguments.jsonl",
             "scores": bank / "jev_scores.jsonl", "collection_manifest": bank / "manifest.json",
             "collection_provenance": bank / "provenance.json", "contexts": root / "work/contexts.jsonl",
             "fixed_index": root / "work/fixed_index.json", "rules": root / "sources/rules.txt"}
    manifest = json.loads(paths["collection_manifest"].read_text())
    context_rows = jsonl(paths["contexts"])
    if context_digest([c for c in context_rows if c["cond"] == "fixed"]) != manifest["contexts_sha256"]:
        raise ValueError("clean fixed contexts differ from the bank's pinned generation request digest; rebuild work first")
    data, args, scores = (jsonl(paths[k]) for k in ("transcripts", "arguments", "scores"))
    normalized, crosswalk = validate_banks(data, args, scores, manifest)
    fixed_contexts = unique_index([c for c in context_rows if c["cond"] == "fixed"], description="fixed contexts")
    if set(fixed_contexts) != {d["id"] for d in data} or any(fixed_contexts[d["id"]]["state"]["turns"] != d["turns_same_span"] for d in data):
        raise ValueError("same-span transcripts differ from pinned argument generation contexts")
    fixed = unique_index(json.loads(paths["fixed_index"].read_text()), description="fixed index")
    for d in data:
        f = fixed[d["id"]]
        if {v: k for k, v in f["letters"].items()} != d["speakers"] or f["label"] != d["professor"] or f["meeting"] != d["meeting"]:
            raise ValueError("corpus participant/label crosswalk differs from rebuilt source index")
    hashes = {key: {"path": str(path.relative_to(root)), "sha256": sha256(path)} for key, path in paths.items()}
    return data, normalized, crosswalk, scores, manifest, hashes


def assess_corpus(data, root=ROOT):
    from build_dataset import load_corpus, load_education, window
    corpus = load_corpus(root / "sources")
    education = load_education(root / "sources")
    fixed = json.loads((root / "work/fixed_index.json").read_text())
    old_meetings = {d["meeting"] for d in data}
    same_people = {p for d in data for p in d["speakers"].values()}
    expanded_people = {s[1] for d in fixed for s in corpus[d["meeting"]][max(0, d["start"] - 60):d["start"] + d["n"] + 60]}
    all_people = {s[1] for segs in corpus.values() for s in segs}
    profs = {p for p in all_people if education.get(p) == "Professor"}
    new_profs = profs - expanded_people
    inventory = []
    fresh_candidates, strict_candidates, professor_disjoint_candidates = [], [], []
    eligible_focal_windows = 0
    for name, segs in sorted(corpus.items()):
        people = {s[1] for s in segs}
        inventory.append({"meeting": name, "segments": len(segs), "previously_used_meeting": name in old_meetings,
                          "participants": sorted(people), "professors": sorted(people & profs),
                          "new_participants_vs_expanded": sorted(people - expanded_people),
                          "known_nonprofessors_new": sorted(p for p in people - expanded_people if education.get(p) and education[p] != "Professor")})
        if name in old_meetings:
            continue
        candidates = []
        for start in range(0, len(segs) - 30 + 1, 15):
            stop = start + 30
            span = segs[start:stop]
            participants = {s[1] for s in span}
            present_profs = participants & profs
            nonprofs = {p for p in participants if education.get(p) and education[p] != "Professor"}
            if len(present_profs) != 1 or not nonprofs:
                continue
            professor = next(iter(present_profs))
            # Longest non-professor contribution, with lexical tie rule, uses no model output.
            counts = collections.Counter(s[1] for s in span)
            other = min(nonprofs, key=lambda p: (-counts[p], p))
            if counts[professor] < 3 or counts[other] < 3 or sum(len(s[2].split()) for s in span) < 100:
                continue
            first = next(s[1] for s in span if s[1] in {professor, other})
            letters = {first: "A", other if first == professor else professor: "B"}
            for p in dict.fromkeys(s[1] for s in span):
                if p not in letters:
                    letters[p] = chr(ord("A") + len(letters))
            candidate = {"id": f"fresh-{name}-{start:05d}", "meeting": name, "start_segment": start, "end_segment": stop,
                         "start_time": span[0][0], "n_segments": 30, "participants": sorted(participants),
                         "speakers": {v: k for k, v in letters.items()}, "professor": letters[professor],
                         "focal_participants": [first, other if first == professor else professor],
                         "old_participants_same_span": sorted(participants & same_people),
                         "old_participants_expanded": sorted(participants & expanded_people),
                         "focal_speaker_disjoint": not {professor, other} & expanded_people,
                         "all_speaker_disjoint": not participants & expanded_people,
                         "status": "fresh meeting exploratory candidate; selection uses source eligibility only; not preregistered confirmation",
                         "turns_same_span": window(corpus, {"meeting": name, "start": start, "n": 30, "letters": letters}, 0)}
            eligible_focal_windows += int(candidate["focal_speaker_disjoint"])
            candidates.append(candidate)
        ranked = sorted(candidates, key=lambda c: hashlib.sha256((SEED + c["id"]).encode()).hexdigest())
        for c in ranked:
            professor_id = c["speakers"][c["professor"]]
            if professor_id in new_profs and not any(c["meeting"] == s["meeting"] and c["start_segment"] < s["end_segment"] and s["start_segment"] < c["end_segment"] for s in professor_disjoint_candidates):
                professor_disjoint_candidates.append(dict(c, status="professor-disjoint only; shared nonprofessor/context participants; single new meeting; exploratory"))
                # Bound the diagnostic packet; no model output or role accuracy selects it.
                if sum(s["meeting"] == name for s in professor_disjoint_candidates) >= 4:
                    break
        for c in ranked:
            if check_candidate(c, old_meetings, expanded_people, strict_candidates):
                strict_candidates.append(c)
            if not any(c["meeting"] == s["meeting"] and c["start_segment"] < s["end_segment"] and s["start_segment"] < c["end_segment"] for s in fresh_candidates):
                fresh_candidates.append(c)
                break  # one independent window per meeting, at most
    newprof_meetings = {p: sorted(name for name, segs in corpus.items() if any(s[1] == p for s in segs)) for p in sorted(new_profs)}
    newprof_neighbors = {p: sorted({s[1] for name in newprof_meetings[p] for s in corpus[name]} - expanded_people - profs) for p in sorted(new_profs)}
    report = {"meetings_total": len(corpus), "meetings_used": len(old_meetings), "meetings_unused": len(corpus.keys() - old_meetings),
              "participants_total": len(all_people), "participants_same_span_used": len(same_people), "participants_expanded_used": len(expanded_people),
              "participants_new_vs_same_span": len(all_people - same_people), "participants_new_vs_expanded": len(all_people - expanded_people),
              "professors_total": len(profs), "professors_seen": sorted(profs & expanded_people), "professors_new": sorted(new_profs),
              "new_professor_meetings": newprof_meetings, "new_professor_nonprofessor_neighbors_unseen": newprof_neighbors,
              "new_professor_known_nonprofessor_unseen": {p: [q for q in neighbors if education.get(q) and education[q] != "Professor"] for p, neighbors in newprof_neighbors.items()},
              "fresh_meeting_candidate_windows": len(fresh_candidates), "fresh_candidate_meetings": sorted(c["meeting"] for c in fresh_candidates),
              "all_speaker_disjoint_eligible_windows": len(strict_candidates), "focal_disjoint_eligible_windows": eligible_focal_windows,
              "professor_disjoint_shared_nonprofessor_candidates": len(professor_disjoint_candidates),
              "professor_disjoint_candidate_ids": [c["id"] for c in professor_disjoint_candidates],
              "eligibility": "30 consecutive segments, 100 words, exactly one professor in span and known nonprofessor; >=3 segments each focal speaker; starts on 15-segment grid; at most one nonoverlapping selected window per unused meeting",
              "confirmation_blocker": "No additional professor co-occurs in an unused meeting with an unseen independently labeled nonprofessor. New professor IDs all occur only in Buw001 with seen participants and one unseen participant lacking education. Acquiring new labeled participants/corpus is required for a speaker-disjoint confirmatory study.",
              "membership_reference": "expanded ±60 participant set, conservative relative to same-span membership",
              "corpus_hashes": {p.name: sha256(p) for p in (root / "sources/icsi_mrt.zip", root / "sources/icsi_core_nxt.zip")},
              "meetings": inventory}
    return report, fresh_candidates, strict_candidates, professor_disjoint_candidates


def swap_turns(turns):
    return [dict(t, speaker={"A": "B", "B": "A"}.get(t["speaker"], t["speaker"])) for t in turns]


def prepare_controls(data, n=8):
    selected = sorted(data, key=lambda d: hashlib.sha256((SEED + "controls" + d["id"]).encode()).hexdigest())[:n]
    requests = []
    for d in selected:
        alternatives = sorted([o for o in data if o["meeting"] != d["meeting"] and not set(o["speakers"].values()) & set(d["speakers"].values())], key=lambda o: o["id"])
        # Same source corpus still shares many people. Meeting-disjoint context suffices
        # for this diagnostic, and the manifest reports all overlap explicitly.
        if not alternatives:
            alternatives = sorted([o for o in data if o["meeting"] != d["meeting"]], key=lambda o: o["id"])
        source = alternatives[0]
        relevant_extra = [t for t in d["turns_pm15"]]
        budget = sum(len(t["text"].split()) for t in relevant_extra)
        unrelated = []
        remaining = budget
        for t in source["turns_pm60"]:
            if remaining <= 0:
                break
            words = t["text"].split()[:remaining]
            unrelated.append({"speaker": "X" + t["speaker"], "text": " ".join(words)})
            remaining -= len(words)
        # Equal word count by truncating both to the available smaller budget.
        matched_budget = budget - remaining
        relevant, left = [], matched_budget
        for t in relevant_extra:
            if left <= 0:
                break
            words = t["text"].split()[:left]
            relevant.append(dict(t, text=" ".join(words)))
            left -= len(words)
        controls = {"same_span": d["turns_same_span"], "focal_only": [t for t in d["turns_same_span"] if t["speaker"] in "AB"],
                    "all_speakers_pm15": d["turns_pm15"], "relevant_context": relevant, "unrelated_context": unrelated,
                    "masked_context": [dict(t, text=re.sub(r"\b(professor|student|doctor|dr|phd)\b", "[STATUS]", t["text"], flags=re.I)) for t in d["turns_pm15"]]}
        for target in ("role", "behavioral_power"):
            question = ("Which focal speaker A or B is the professor? Other speakers are context only." if target == "role" else
                        "Which focal speaker A or B exercises more conversational influence in this excerpt? This is behavioral power, not academic role.")
            for condition, turns in controls.items():
                for swap in (False, True):
                    requests.append({"request_id": f"{d['id']}|{target}|{condition}|swap={int(swap)}", "snippet_id": d["id"], "target": target,
                                     "condition": condition, "swapped": swap, "question": question, "focal_excerpt": swap_turns(d["turns_same_span"]) if swap else d["turns_same_span"],
                                     "turns": swap_turns(turns) if swap else turns, "prediction_unmap": {"A": "B", "B": "A"} if swap else {"A": "A", "B": "B"},
                                     "context_source_id": source["id"] if condition == "unrelated_context" else d["id"],
                                     "context_source_meeting": source["meeting"] if condition == "unrelated_context" else d["meeting"],
                                     "context_words": sum(len(t["text"].split()) for t in turns), "model": None, "settings": None,
                                     "limitations": "behavioral-power gold absent; status masking removes literal status tokens only, not inferred identity/name information; no outcomes collected"})
        for order in ("A-first", "B-first"):
            for repeat in (1, 2):
                requests.append({"request_id": f"{d['id']}|judge|{order}|repeat={repeat}", "snippet_id": d["id"], "target": "behavioral_power",
                                 "condition": "judge_order", "order": order, "repeat": repeat,
                                 "turns": d["turns_same_span"], "argument_bank": "data/clean_quote_study/arguments.jsonl",
                                 "instruction": "Compare the same fixed clean reason/rebuttal bank, present all A-side arguments first or all B-side arguments first as specified, keep model/temperature/seed/settings matched across repeats and orders.",
                                 "model": None, "settings": None})
    return requests


def prepare(args):
    data, rows, crosswalk, scores, manifest, hashes = load_inputs()
    out = Path(args.out)
    sample = stratified_sample(rows, args.sample_size)
    D = unique_index(data)
    worksheet = [blind_row(r, D[r["snippet_id"]]) for r in sample]
    out.mkdir(parents=True, exist_ok=True)
    write_jsonl(out / "arguments.jsonl", rows)
    # Gold/label answer key is confined to ignored work/. Public participant
    # membership is useful for leakage checks, but is withheld from worksheets.
    write_jsonl(out / "participant_crosswalk.jsonl", [{k: v for k, v in r.items() if k not in {"professor_letter", "professor_participant"}} for r in crosswalk])
    legacy_generated = out / "participant_label_crosswalk.jsonl"
    if legacy_generated.exists():
        legacy_generated.unlink()
    write_csv(out / "annotator_1.csv", worksheet)
    write_csv(out / "annotator_2.csv", worksheet)
    # Answer key never enters a shareable worksheet, and work/ is gitignored.
    write_json(ROOT / "work/clean_quote_study/private_answer_key.json", {"sample_ids": [r["argument_id"] for r in sample], "crosswalk": crosswalk})
    inventory, candidates, strict, professor_disjoint = assess_corpus(data)
    write_json(out / "corpus_inventory.json", inventory)
    write_jsonl(out / "fresh_meeting_candidates.jsonl", candidates)
    write_jsonl(out / "speaker_disjoint_candidates.jsonl", strict)
    write_jsonl(out / "professor_disjoint_candidates.jsonl", professor_disjoint)
    controls = prepare_controls(data)
    write_jsonl(out / "diagnostic_requests.jsonl", controls)
    write_json(out / "filter_policy.json", POLICY)
    write_json(out / "annotation_schema.json", {"fields": list(worksheet[0]), "judgments": {k: sorted(CHOICES) for k in FIELDS},
                                               "quote": "copy a nonempty contiguous verbatim span from one turn, without adding/removing punctuation; quote_speaker identifies the actual speaker, which may differ from intended side",
                                               "source": "two independent humans; set annotator_type=human and unique annotator_id; no prefilled judgments",
                                               "reason_only": "rebuttal_answers_reason may remain blank on reason rows", "uncertain": "a valid completed judgment, not a binary no"})
    frozen = {"study": "clean-quote-study-v1", "status": POLICY["status"], "seed": SEED, "n_snippets": len(data), "n_arguments": len(rows),
              "n_sample": len(sample), "strata": "4 aspects x 2 kinds x 2 intended sides; 6 each for default96", "collection_model": manifest["model"],
              "scorer_model": manifest["jev_model"], "collection_fingerprint": manifest["run_fingerprint"], "inputs": hashes,
              "policy": POLICY, "blinding": "worksheet exports omit gold, professor field, participant IDs, model scores/predictions, model identities and audit notes; claim and unredacted transcript remain necessary evidence",
              "annotation_status": "blank independent human worksheets; no evidence judgments fabricated", "diagnostic_requests": len(controls),
              "private_label_crosswalk": "work/clean_quote_study/private_answer_key.json (gitignored; never commit or supply to annotators)",
              "fresh_meeting_candidates": len(candidates), "speaker_disjoint_candidates": len(strict), "script_sha256": sha256(Path(__file__))}
    write_json(out / "manifest.json", frozen)
    print(json.dumps({k: frozen[k] for k in ("n_snippets", "n_arguments", "n_sample", "diagnostic_requests", "fresh_meeting_candidates", "speaker_disjoint_candidates")}))


def make_request(snippet, arguments, model, max_tokens):
    payload_arguments = [{k: r[k] for k in ("argument_id", "kind", "aspect", "intended_side", "claim", "paired_reason")} for r in arguments]
    system = ("Audit evidence in the supplied transcript. Return only a JSON object with key annotations, a list containing exactly one object per requested argument_id. "
              "Each object must have argument_id, quote, quote_speaker, quote_present, attribution_correct, claim_supported, rebuttal_answers_reason, should_keep. "
              "All judgments are strings yes/no/uncertain. Quotes must be exact nonempty contiguous substrings of ONE transcript turn and quote_speaker must be its actual letter. "
              "The evidence speaker may differ from the argument's intended side. Do not force evidence onto that side. "
              "If no suitable quote exists use quote='', quote_speaker='', quote_present='no', attribution_correct='uncertain', claim_supported='no', should_keep='no'. "
              "claim_supported asks whether the quote supports the PARTICULAR claim, not merely its topic. attribution_correct asks whether the claim correctly attributes the quoted conduct/information. "
              "For rebuttals judge whether it answers paired_reason; for reasons set rebuttal_answers_reason='uncertain'. "
              "Set should_keep='yes' only if quote_present, attribution_correct and claim_supported are all yes, and for rebuttals rebuttal_answers_reason is yes. "
              "Use uncertain when evidence is ambiguous. No gold role labels or model predictions are supplied. Do not output participant roles or academic labels.")
    return {"model": model, "temperature": 0, "max_tokens": max_tokens, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": json.dumps({"transcript": snippet["turns_same_span"], "arguments": payload_arguments}, ensure_ascii=False)}]}


def collect(args):
    data, rows, _, _, _, _ = load_inputs()
    D = unique_index(data)
    by_id = collections.defaultdict(list)
    for row in rows:
        by_id[row["snippet_id"]].append(row)
    sample_ids = list(dict.fromkeys(r["snippet_id"] for r in stratified_sample(rows)))
    ids = args.ids.split(",") if args.ids else sample_ids
    if len(set(ids)) != len(ids) or any(id_ not in D for id_ in ids):
        raise ValueError("--ids must name unique existing snippet IDs")
    if not 1 <= args.max_requests <= 150:
        raise ValueError("--max-requests must be in 1..150")
    url = urllib.parse.urlsplit(args.base_url)
    if url.scheme != "https" or not url.netloc or url.username or url.password or url.query or url.fragment:
        raise ValueError("base URL must be HTTPS with no credentials, query or fragment")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", args.api_key_env):
        raise ValueError("--api-key-env must be an environment-variable name")
    if args.max_cost_usd is not None and (not math.isfinite(args.max_cost_usd) or args.max_cost_usd <= 0):
        raise ValueError("--max-cost-usd must be positive and finite")
    ids = ids[:args.max_requests]
    out = Path(args.out)
    metadata = {"requested_model": args.model, "base_url": args.base_url.rstrip("/"), "max_requests": args.max_requests,
                "selected_ids": ids, "dry_run": not args.execute, "requests": [], "actual_usd_reported": 0.0,
                "failed_requests": [], "network_attempts": 0, "cost_complete": True,
                "max_cost_usd": args.max_cost_usd, "cost_limit": "reported-cost stop after each response; one request can cross limit; no unsupported preflight cost estimate", "status": "prepared"}
    if not args.execute:
        write_json(out / "dry_run.json", metadata)
        print(json.dumps({"status": "dry_run", "selected_ids": ids, "request_bound": len(ids), "model": args.model}))
        return
    if (out / "collection_manifest.json").exists():
        raise ValueError("collection output already has evidence; choose a new --out directory (valid request caches are still reusable)")
    key = os.environ.get(args.api_key_env)
    if not key:
        raise ValueError(f"missing credential environment variable {args.api_key_env}; credential values are never printed")
    endpoint = args.base_url.rstrip("/") + "/chat/completions"
    if not endpoint.startswith("https://"):
        raise ValueError("collection endpoint must use HTTPS")
    accepted = []
    for id_ in ids:
        if args.max_cost_usd is not None and metadata["actual_usd_reported"] >= args.max_cost_usd:
            metadata["status"] = "reported_cost_cap_reached"
            break
        request = make_request(D[id_], by_id[id_], args.model, args.max_tokens)
        fingerprint = object_hash({"endpoint": endpoint, "request": request})
        cache = ROOT / "work/clean_quote_study/quote_cache" / (fingerprint + ".json")
        cached = cache.exists()
        start = time.monotonic()
        if cached:
            saved = json.loads(cache.read_text())
            if saved["request_sha256"] != fingerprint or saved["request"] != request:
                raise ValueError("cached request provenance mismatch")
            response = saved["response"]
        else:
            http_request = urllib.request.Request(endpoint, data=json.dumps(request).encode(), method="POST",
                                                  headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
            try:
                metadata["network_attempts"] += 1
                with urllib.request.urlopen(http_request, timeout=args.timeout) as response_stream:
                    response = json.load(response_stream)
            except urllib.error.HTTPError as e:
                metadata["status"] = f"stopped_http_{e.code}"
                metadata["cost_complete"] = False
                metadata["failed_requests"].append({"snippet_id": id_, "request_sha256": fingerprint, "http_status": e.code, "usage": None, "reported_cost_usd": None})
                write_json(out / "collection_manifest.json", metadata)
                raise ValueError(f"quote collection stopped: HTTP {e.code}; response body omitted to protect credentials") from None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
                metadata["status"] = "stopped_transport_or_json_failure"
                metadata["cost_complete"] = False
                metadata["failed_requests"].append({"snippet_id": id_, "request_sha256": fingerprint, "usage": None, "reported_cost_usd": None})
                write_json(out / "collection_manifest.json", metadata)
                raise ValueError("quote collection stopped: transport/JSON failure; raw error omitted") from None
        # Billing and exact response provenance exist even if evidence validation
        # fails. Account before validating; an invalid answer is still a paid call.
        usage = response.get("usage", {}) if isinstance(response, dict) else {}
        cost = response.get("cost", usage.get("cost", usage.get("total_cost"))) if isinstance(response, dict) else None
        if isinstance(cost, dict):
            cost = cost.get("total_cost", cost.get("total"))
        if isinstance(cost, (int, float)) and math.isfinite(cost) and cost >= 0:
            if not cached:
                metadata["actual_usd_reported"] += cost
        else:
            cost = None
            if not cached:
                metadata["cost_complete"] = False
        record = {"snippet_id": id_, "request_sha256": fingerprint, "cached": cached,
                  "response_id": response.get("id") if isinstance(response, dict) else None,
                  "served_model": response.get("model") if isinstance(response, dict) else None,
                  "usage": usage, "reported_cost_usd": cost, "elapsed_seconds": round(time.monotonic() - start, 3)}
        try:
            if response["choices"][0].get("finish_reason") not in {None, "stop"}:
                raise ValueError("incomplete response")
            content = json.loads(response["choices"][0]["message"]["content"])
            if set(content) != {"annotations"} or not isinstance(content["annotations"], list):
                raise ValueError("annotations list required")
            answers = validate_quote_answers(content["annotations"], by_id[id_], D[id_]["turns_same_span"])
            served_model = response.get("model")
            if not isinstance(served_model, str) or not served_model:
                raise ValueError("resolved response model required")
        except (KeyError, TypeError, IndexError, json.JSONDecodeError, ValueError):
            metadata["status"] = "stopped_invalid_answer_not_cached"
            quarantine = ROOT / "work/clean_quote_study/quarantine" / (fingerprint + "-" + object_hash(response) + ".json")
            write_json(quarantine, {"request_sha256": fingerprint, "request": request, "response": response, "validated": False})
            metadata["failed_requests"].append(dict(record, quarantine=str(quarantine.relative_to(ROOT))))
            if cached:
                cache.unlink()  # Invalid responses cannot remain in the reusable cache.
            write_json(out / "collection_manifest.json", metadata)
            raise ValueError(f"quote collection stopped at snippet {id_}: invalid/incomplete answer; not accepted or cached") from None
        if not cached:
            write_json(cache, {"request_sha256": fingerprint, "request": request, "response": response, "validated": True})
        metadata["requests"].append(record)
        for row in by_id[id_]:
            answer_fields = {k: answers[row["argument_id"]][k] for k in ("argument_id", "quote", "quote_speaker", *FIELDS)}
            accepted.append({**row, **answer_fields, "annotator_type": "model", "annotator_id": served_model,
                             "request_sha256": fingerprint})
        # Accepted partial progress survives a later fail-stop, and is always labeled pilot.
        write_jsonl(out / "model_annotations.jsonl", accepted)
        metadata["status"] = "partial_exploratory_pilot"
        write_json(out / "collection_manifest.json", metadata)
    if metadata["status"] != "reported_cost_cap_reached":
        metadata["status"] = "completed_bounded_exploratory_pilot"
    metadata["accepted_arguments"] = len(accepted)
    metadata["independent_human_gate"] = "not satisfied by model collection"
    write_json(out / "collection_manifest.json", metadata)
    print(json.dumps({"status": metadata["status"], "requests": len(metadata["requests"]), "arguments": len(accepted), "reported_cost_usd": metadata["actual_usd_reported"]}))


def metrics(predictions, gold):
    ids = list(predictions)
    recalls = {s: sum(predictions[i] == gold[i] for i in ids if gold[i] == s) / sum(gold[i] == s for i in ids) if any(gold[i] == s for i in ids) else None for s in "AB"}
    return {"n": len(ids), "correct": sum(predictions[i] == gold[i] for i in ids),
            "accuracy": sum(predictions[i] == gold[i] for i in ids) / len(ids), "per_class_recall": recalls,
            "balanced_accuracy": sum(recalls.values()) / 2 if all(v is not None for v in recalls.values()) else None}


def paired_meeting_interval(off, on, data, gold, draws=5000):
    groups = collections.defaultdict(list)
    for i in off:
        groups[data[i]["meeting"]].append(int(on[i] == gold[i]) - int(off[i] == gold[i]))
    values = list(groups.values())
    rng = random.Random(SEED)
    deltas = []
    for _ in range(draws):
        sampled = [v for _ in values for v in rng.choice(values)]
        deltas.append(sum(sampled) / len(sampled))
    deltas.sort()
    return {"unit": "meeting", "meetings": len(values), "draws": draws, "seed": SEED,
            "delta_accuracy": sum(int(on[i] == gold[i]) - int(off[i] == gold[i]) for i in off) / len(off),
            "percentile_95": [deltas[int(.025 * draws)], deltas[min(draws - 1, int(.975 * draws))]],
            "limitation": "few clusters and retrospective pilot selection limit uncertainty interpretation; not a confirmatory test"}


def evaluate(args):
    from post_audit_evaluation import conditional_objectives, choose, parse_rules
    data, rows, _, scores, _, hashes = load_inputs()
    D, S = unique_index(data), unique_index(scores)
    annotations = read_annotations(args.annotations)
    H = unique_index(annotations, "argument_id", "annotations")
    R = unique_index(rows, "argument_id", "normalized bank")
    if not H or set(H) - set(R):
        raise ValueError("annotations must name known normalized clean arguments")
    if any(r.get("annotator_type") != args.source for r in annotations):
        raise ValueError("annotation provenance must match --source; model/proxy outputs cannot be human labels")
    for k, annotation in H.items():
        canonical = blind_row(R[k], D[R[k]["snippet_id"]])
        validate_annotation_identity(annotation, canonical, allow_transcript_hash=args.source == "model")
    ids = sorted({R[k]["snippet_id"] for k in H})
    expected = [r for r in rows if r["snippet_id"] in ids]
    if set(H) != {r["argument_id"] for r in expected}:
        raise ValueError("paired inference requires all 48 arguments for every included snippet; sampled human worksheets alone do not suffice")
    if args.source == "human" and any(not annotation_complete(r) for r in annotations):
        raise ValueError("human inference requires completed human annotations")
    for id_ in ids:
        validate_quote_answers([H[r["argument_id"]] for r in expected if r["snippet_id"] == id_], [r for r in expected if r["snippet_id"] == id_], D[id_]["turns_same_span"], allow_reason_blank=args.source == "human", enforce_strict_keep=args.source == "model")
    pairs = parse_rules((ROOT / "sources/rules.txt").read_text())
    gold = {i: D[i]["professor"] for i in ids}
    predictions = {"off": {}, "on": {}}
    decision_rows, retention = [], collections.Counter()
    start = time.monotonic()
    for id_ in ids:
        snippet_rows = [r for r in expected if r["snippet_id"] == id_]
        active = {r["variable"] for r in snippet_rows if strict_keep(dict(H[r["argument_id"]], kind=r["kind"]), D[id_]["turns_same_span"])}
        for r in snippet_rows:
            retention["total_" + r["kind"]] += 1
            retention["kept_" + r["kind"]] += int(r["variable"] in active)
            required = ("quote_present", "attribution_correct", "claim_supported") + (("rebuttal_answers_reason",) if r["kind"] == "rebuttal" else ())
            retention["uncertain_filter_arguments"] += int(any(H[r["argument_id"]].get(f) == "uncertain" for f in required))
            retention["uncertain_holistic_keep"] += int(H[r["argument_id"]].get("should_keep") == "uncertain")
        record = {"id": id_, "meeting": D[id_]["meeting"], "gold": gold[id_], "active_variables": sorted(active), "retained": len(active)}
        for label, variables in (("off", None), ("on", active)):
            objective = conditional_objectives(S[id_]["answers"], "all", pairs, active_variables=variables)
            pred = choose(*objective["values"])
            predictions[label][id_] = pred
            record[label] = {"prediction": pred, "conditional_objectives": [v if math.isfinite(v) else None for v in objective["values"]],
                             "infeasible_sides": [s for s, v in zip("AB", objective["values"]) if not math.isfinite(v)],
                             "route": "default_A_no_reasons" if label == "on" and not any(r["kind"] == "reason" and r["variable"] in active for r in snippet_rows) else "equal_objective_A" if objective["values"][0] == objective["values"][1] else "conditional_objective"}
        decision_rows.append(record)
    elapsed = time.monotonic() - start
    report = {"status": "exploratory paired filter comparison", "annotation_source": args.source,
              "independent_human_gate": "requires separate two-human agreement report; model outputs do not satisfy it",
              "scope": {"n_snippets": len(ids), "ids": ids, "complete_bank": len(ids) == len(data)},
              "off": metrics(predictions["off"], gold), "on": metrics(predictions["on"], gold),
              "paired_meeting_uncertainty": paired_meeting_interval(predictions["off"], predictions["on"], D, gold),
              "argument_retention": dict(retention), "decision_routes": {label: dict(collections.Counter(r[label]["route"] for r in decision_rows)) for label in predictions},
              "compute": {"evaluation_elapsed_seconds": round(elapsed, 6), "model_calls_by_evaluation": 0, "annotation_collection": "see supplied model collection manifest, if applicable"},
              "held_fixed": ["transcript", "argument bank", "score bank", "relation scores", "graph rules", "deterministic conditional solver", "tie policy"],
              "policy": POLICY, "input_hashes": hashes, "annotations_sha256": sha256(args.annotations)}
    out = Path(args.out)
    write_jsonl(out / "paired_decisions.jsonl", decision_rows)
    write_json(out / "paired_evaluation.json", report)
    print(json.dumps({"n": len(ids), "off": report["off"]["accuracy"], "on": report["on"]["accuracy"], "source": args.source}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--out", default=str(ROOT / "data/clean_quote_study"))
    p.add_argument("--sample-size", type=int, default=96)
    p.set_defaults(func=prepare)
    p = sub.add_parser("agreement")
    p.add_argument("--first", required=True)
    p.add_argument("--second", required=True)
    p.add_argument("--predictions")
    p.add_argument("--out", default=str(ROOT / "results/clean_quote_study/human_agreement.json"))
    def agreement_command(args):
        data, rows, _, _, _, _ = load_inputs()
        D = unique_index(data)
        canonical = [blind_row(r, D[r["snippet_id"]]) for r in rows]
        report = annotation_report(read_annotations(args.first), read_annotations(args.second), read_annotations(args.predictions) if args.predictions else None, canonical=canonical,
                                   expected_ids={r["argument_id"] for r in stratified_sample(rows)})
        report["input_hashes"] = {"first": sha256(args.first), "second": sha256(args.second),
                                  "predictions": sha256(args.predictions) if args.predictions else None}
        write_json(args.out, report)
        print(json.dumps({k: report[k] for k in ("n", "first_complete", "second_complete", "ready_for_human_conclusion")}))
    p.set_defaults(func=agreement_command)
    p = sub.add_parser("collect")
    p.add_argument("--model", required=True)
    p.add_argument("--base-url", required=True, help="OpenAI-compatible HTTPS endpoint prefix, normally ending /v1")
    p.add_argument("--api-key-env", required=True, help="environment-variable NAME only; never pass a secret argument")
    p.add_argument("--max-requests", type=int, required=True)
    p.add_argument("--max-cost-usd", type=float)
    p.add_argument("--max-tokens", type=int, default=16000)
    p.add_argument("--timeout", type=int, default=180)
    p.add_argument("--ids", help="optional comma-separated snippet IDs; defaults to deterministic annotation-sample order")
    p.add_argument("--execute", action="store_true", help="actually call provider; omitted means dry run")
    p.add_argument("--out", default=str(ROOT / "results/clean_quote_study/pilot"))
    p.set_defaults(func=collect)
    p = sub.add_parser("evaluate")
    p.add_argument("--annotations", required=True)
    p.add_argument("--source", required=True, choices=("human", "model"))
    p.add_argument("--out", default=str(ROOT / "results/clean_quote_study/evaluation"))
    p.set_defaults(func=evaluate)
    args = parser.parse_args()
    try:
        args.func(args)
    except (ValueError, FileNotFoundError) as exc:
        parser.exit(2, "error: " + str(exc) + "\n")


if __name__ == "__main__":
    main()
