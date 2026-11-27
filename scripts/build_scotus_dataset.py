#!/usr/bin/env python3
"""Build a fresh, post-training-cutoff power dataset from U.S. Supreme Court oral arguments (October Term 2026).

Why: every model we evaluate may have seen the ICSI transcripts (online since the early 2000s) and Wu et al.'s
meeting.csv (GitHub, 2025). These arguments were heard and first published from 2026-10-05 to 2026-11-10, so the
dialogue text cannot be in any training set whose cutoff is before 2026-10-05. Gold labels are an official fact
(the court reporter's speaker header says who is a Justice and who is an advocate), not a judgment of the text.

Sources: the 13 official same-day transcripts listed in SOURCES (supremecourt.gov, Heritage Reporting Corporation).
They are downloaded into sources/scotus_ot2026/ (ignored by git) and verified by SHA-256.

Steps:
  1. Extract text from each PDF with pypdf; keep only the transcript lines of each page (between the
     "Official - Subject to Final Review" header and the "Heritage Reporting Corporation" footer), stop at
     "(Whereupon, ... the case was submitted.)".
  2. Split into turns at the reporter's speaker headers (CHIEF JUSTICE X:, JUSTICE X:, MR./MS./MRS./GENERAL/DR. X:).
     Stage directions such as "(Laughter.)" are removed. Each turn gets its argument section (which advocate is at
     the lectern) from the ORAL ARGUMENT OF / REBUTTAL ARGUMENT OF headings.
  3. Role: a speaker whose header starts with JUSTICE or CHIEF JUSTICE is a Justice (higher power); every other
     speaker is an advocate (lower power).
  4. Snippets: maximal runs of consecutive turns in which exactly one Justice and the advocate at the lectern talk to
     each other. A run is eligible when it has at least MIN_TURNS turns with at least two turns per person and none
     of its turns is procedural (an advocate's opening statement, the Chief Justice calling on colleagues or closing
     an argument). The first MAX_TURNS turns of each eligible run form the same-span snippet (the ICSI median is 6).
     Runs never overlap, so no two snippets share a turn.
  5. Context: 15 or 60 extra turns on each side, clipped to the same case. Other speakers are C, D, ... in order.
  6. Letters: a seeded shuffle puts the Justice at A in exactly half of the snippets (the other half has one more
     at B when the count is odd).
  7. Masking (see mask_text): names and titles of every Justice and advocate, forms of address ("Your Honor",
     "Mr. Chief Justice", vocative "Counsel"/"General"), and stage directions are replaced. A focal speaker named in
     the text becomes "Speaker A"/"Speaker B"; anyone else becomes "[PERSON]"; forms of address become "[ADDRESS]".
     Both raw and masked files are written.
  8. Split: whole cases go to dev or test (seeded), never both.
  9. Leak check: count any title/name token left in the masked text (written to the manifest; the build fails on
     an unmasked title).

Outputs (data/scotus_ot2026/):
  snippets_masked.jsonl   the dataset to evaluate (schema in docs/SCOTUS_DATA.md)
  snippets_raw.jsonl      the same snippets without masking (for the masked-vs-raw cue analysis)
  manifest.json           sources, hashes, counts, split membership, leak check, parameters

  python3 scripts/build_scotus_dataset.py --download     # fetch sources, verify, build
  python3 scripts/build_scotus_dataset.py --check        # rebuild and compare with the committed files
"""
import argparse, hashlib, json, random, re, sys, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://www.supremecourt.gov/oral_arguments/argument_transcripts/2026/"
# docket: (file, case name, argument date, sha256)
SOURCES = {
    "25-170": ("25-170_8m58.pdf", "Suncor Energy (U.S.A.) Inc. v. Commissioners of Boulder County", "2026-10-05", "0c6229f061b9fcca318510ce5d14092d1ab8be2834e4b9cd3c4d81ef1d0ce806"),
    "25-735": ("25-735_ca7d.pdf", "Johnson v. United States Congress", "2026-10-05", "c18f48073b16551db5c6d57491c58ce28ab0f0a3ad949b75395a5efa9a13e71a"),
    "25-498": ("25-498_febh.pdf", "Anderson v. Intel Corp. Investment Policy Committee", "2026-10-06", "2b20823a10f6287e5f1c7abc8cbc184de27a779691d743ad5cb0aeb577bc263f"),
    "25-579": ("25-579_e29g.pdf", "Department of Air Force v. Prutehi Guahan", "2026-10-07", "1a976672721672ba69912af6edb3750de10fcbc7c95bb2e4920a58126fd87554"),
    "25-5343": ("25-5343_4g15.pdf", "Beaird v. United States", "2026-10-13", "d09a6377e76d58516ddf83b18fc82acd960bbcdc362bdafd9c3381e75675e3a8"),
    "25-459": ("25-459_i425.pdf", "Salazar v. Paramount Global", "2026-10-14", "4b885a9c729446bdd059f516765c9b32ff0981523a0db1244bd4c87db71cb8da"),
    "25-5930": ("25-5930_bqmd.pdf", "Maxwell v. Dinis", "2026-11-02", "18424043431d967a999f3896e833f2df7c0af09d3c99a604146c893b204f9ddb"),
    "25-352": ("25-352_i32j.pdf", "Younge v. Fulton Judicial Circuit Dist. Attorney's Office", "2026-11-02", "aee7c5972dcfbe816838367bd4e343d2c6aac9d4e7933f987db337f9828552b8"),
    "25-581": ("25-581_6j36.pdf", "St. Mary Catholic Parish v. Roy", "2026-11-03", "9c79db107eace0476da7c88fc3d768b3b800e239127ff81b866cb5a74bf916ad"),
    "25-1003": ("25-1003_c9dh.pdf", "Guerrero v. Johnson", "2026-11-04", "903cca6f1e8b3c3ea162aafcaea736840f12fd033a13ae56da749a85c1627ac4"),
    "25-417": ("25-417_b81g.pdf", "Nielsen v. Watanabe", "2026-11-09", "3eb1a8b279ae88cc16272aab46dd1a3e628eb0f6d2f6126aec90bf0912683e61"),
    "25-159": ("25-159_5hdk.pdf", "Hoffmann v. WBI Energy Transmission, Inc.", "2026-11-09", "f8367b974dd48db0754ba1d195c72ebc2f5720905e5f8da1f7915617e910ca98"),
    "25-966": ("25-966_c07d.pdf", "Department of Labor v. Sun Valley Orchards, LLC", "2026-11-10", "4ce300f24747646e17bcc23f126d90ccfeedc0329641d7a7de5f67f919633429"),
}
EARLIEST_ALLOWED = "2026-10-01"   # every source must be first published on or after this date (see docs/SCOTUS_DATA.md)
MIN_TURNS, MAX_TURNS, MIN_EACH, MIN_WORDS = 4, 6, 2, 40
CONTEXTS = (("pm15", 15), ("pm60", 60))
SEED, DEV_CASES = 2026, 3
SETTING = ("Excerpt from a recorded institutional proceeding. Exactly one of the two speakers, A and B, "
           "holds the more powerful institutional role.")

HEADER = re.compile(r"^(CHIEF JUSTICE|JUSTICE|MR\.|MS\.|MRS\.|GENERAL|DR\.)\s+([A-Z][A-Za-z'\-]+(?:\s+[A-Z][A-Za-z'\-]+)?):\s*(.*)$")
SECTION = re.compile(r"^(?:ORAL|REBUTTAL) ARGUMENT OF\s+(.+)$")
STAGE = re.compile(r"\((?:Laughter|Pause|Recess|Inaudible|Crosstalk)[^)]*\.?\)", re.I)
END = re.compile(r"\(Whereupon,.*?(?:submitted|adjourned)\.?\)", re.I | re.S)


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""): h.update(chunk)
    return h.hexdigest()


def get_sources(dest, download):
    dest.mkdir(parents=True, exist_ok=True); ok = True
    for docket, (name, _, _, digest) in SOURCES.items():
        path = dest / name
        if not path.exists():
            if not download: sys.exit(f"missing {path}; run with --download")
            print(f"downloading {name}", flush=True)
            req = urllib.request.Request(BASE + name, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=300) as r: path.write_bytes(r.read())
        got = sha256(path); match = got == digest; ok &= match
        print(f"{'ok      ' if match else 'MISMATCH'} {name}  {got}")
    if not ok: sys.exit("At least one transcript does not match its recorded checksum (the Court may have posted a revised version).")


# ---------- step 1-3: transcript -> turns ----------

def page_lines(page_text):
    """Transcript lines of one page: drop the line-number gutter, the header and the footer."""
    lines = [l.strip() for l in page_text.splitlines()]
    try: start = next(i for i, l in enumerate(lines) if l.startswith("Official - Subject to Final Review")) + 1
    except StopIteration: return []
    out = []
    for l in lines[start:]:
        if l.startswith("Heritage Reporting Corporation"): break
        out.append(l)
    if out and re.fullmatch(r"\d+", out[0]): out = out[1:]          # page number printed under the header
    return [l for l in out if l]


def transcript_lines(pdf_path):
    from pypdf import PdfReader
    lines = []
    for page in PdfReader(str(pdf_path)).pages: lines.extend(page_lines(page.extract_text() or ""))
    return lines


def appearances(lines):
    """Advocate names from the APPEARANCES block, as lists of name tokens (for masking)."""
    names, on = [], False
    for l in lines:
        if l.startswith("APPEARANCES"): on = True; continue
        if on and (l.startswith("C O N T E N T S") or l.startswith("ORAL ARGUMENT OF")): break
        if on:
            m = re.match(r"^([A-Z][A-Za-z.\s'\-]+?),\s*(?:ESQUIRE|ESQ\.|Assistant|Deputy|Solicitor|Attorney|Principal|General|Counsel|Senior|Chief|Special|Professor)", l)
            if m: names.append(m.group(1).strip())
    return names


def surname_of(full_name):
    """'CHARLES L. McCLOUD' -> 'McCloud'; 'KEVIN JOEL PAGE' -> 'Page'."""
    tok = re.findall(r"[A-Za-z'\-]+", full_name)[-1]
    return tok if not tok.isupper() else tok.title()


def normalize_advocate(surname, advocate_surnames):
    """Map a reporter header surname to the APPEARANCES spelling; fixes header typos such as FEIGN for FEIGIN."""
    import difflib
    by_upper = {s.upper(): s for s in advocate_surnames}
    if surname.upper() in by_upper: return by_upper[surname.upper()]
    close = difflib.get_close_matches(surname.upper(), list(by_upper), n=1, cutoff=0.75)
    return by_upper[close[0]] if close else surname.title()


def parse_turns(lines, advocate_names=()):
    """Split proceedings into turns: [{'speaker': 'JUSTICE KAGAN', 'role': 'justice'|'advocate', 'section': i, 'text': str}]."""
    adv_surnames = [surname_of(n) for n in advocate_names]
    try: start = next(i for i, l in enumerate(lines) if l.replace(" ", "") == "PROCEEDINGS")
    except StopIteration: raise ValueError("no P R O C E E D I N G S heading")
    body = "\n".join(lines[start + 1:])
    m = END.search(body)
    if m: body = body[:m.start()]
    turns, section, cur = [], 0, None
    for l in body.splitlines():
        if SECTION.match(l) or re.match(r"^ON BEHALF OF|^FOR THE UNITED STATES|^SUPPORTING THE|^AS AMICUS|^CURIAE", l):
            if SECTION.match(l): section += 1
            cur = None; continue
        h = HEADER.match(l)
        if h:
            title, surname = h.group(1), h.group(2).strip()
            role = "justice" if title in ("JUSTICE", "CHIEF JUSTICE") else "advocate"
            surname = normalize_advocate(surname, adv_surnames) if role == "advocate" else surname.title()
            cur = {"speaker": f"{title} {surname.upper()}", "surname": surname, "role": role, "section": section, "text": h.group(3)}
            turns.append(cur)
        elif cur is not None:
            cur["text"] += " " + l
    for t in turns:
        t["text"] = " ".join(STAGE.sub(" ", t["text"]).split())
        t["procedural"] = is_procedural(t)
    return [t for t in turns if t["text"]]


def is_procedural(t):
    x = t["text"]
    if t["role"] == "advocate":
        return bool(re.search(r"may it please the Court", x, re.I))
    if t["speaker"].startswith("CHIEF JUSTICE"):
        w = len(x.split())
        if re.search(r"case is submitted|We will hear argument|Thank you,? counsel\.?$|Rebuttal|minute", x, re.I) and w <= 25: return True
        if re.fullmatch(r"(?:(?:Thank you,?\s*(?:counsel)?\.?|Mr\.|Ms\.|Mrs\.|General|Justice|[A-Z][a-z]+|[.,?]|\s)+)", x) and w <= 8: return True
    return False


# ---------- step 4-6: snippets ----------

def runs(turns):
    """Maximal runs of consecutive turns between exactly one Justice and one advocate (same section)."""
    out, i = [], 0
    while i < len(turns):
        j, people = i, set()
        while j < len(turns) and not turns[j]["procedural"] and turns[j]["section"] == turns[i]["section"]:
            p = people | {turns[j]["speaker"]}
            if len(p) > 2: break
            people = p; j += 1
        if j > i and len(people) == 2 and {turns[k]["role"] for k in range(i, j)} == {"justice", "advocate"}:
            out.append((i, j))
        i = max(j, i + 1)
    return out


def eligible(turns, i, j):
    span = turns[i:min(j, i + MAX_TURNS)]
    if len(span) < MIN_TURNS: return False
    counts = {}
    for t in span: counts[t["speaker"]] = counts.get(t["speaker"], 0) + 1
    if len(counts) != 2 or min(counts.values()) < MIN_EACH: return False
    return sum(len(t["text"].split()) for t in span) >= MIN_WORDS


def letter_turns(turns, focal):
    """focal: {'A': speaker, 'B': speaker}. Other speakers get C, D, ... in order of appearance."""
    of = {v: k for k, v in focal.items()}; nxt = ord("C"); out = []
    for t in turns:
        if t["speaker"] not in of: of[t["speaker"]] = chr(nxt); nxt += 1
        out.append({"speaker": of[t["speaker"]], "text": t["text"]})
    return out, of


# ---------- step 7: masking ----------

JUSTICE_SURNAMES = ["Roberts", "Thomas", "Alito", "Sotomayor", "Kagan", "Gorsuch", "Kavanaugh", "Barrett", "Jackson"]
DISTINCTIVE = {"Alito", "Sotomayor", "Kagan", "Gorsuch", "Kavanaugh"}   # never also a common party/case name


def build_masker(turns, advocate_names):
    """Return mask(text, letter_of) for one case. letter_of maps reporter speaker header -> letter."""
    justices = sorted({t["surname"] for t in turns if t["role"] == "justice"} | set(JUSTICE_SURNAMES))
    adv = sorted({surname_of(n) for n in advocate_names} | {t["surname"] for t in turns if t["role"] == "advocate"}, key=len, reverse=True)
    surname_header = {}
    for t in turns: surname_header.setdefault(t["surname"].lower(), t["speaker"])

    def who(surname, letter_of):
        sp = surname_header.get(surname.lower())
        if sp and letter_of.get(sp) in ("A", "B"): return f"Speaker {letter_of[sp]}"
        return "[PERSON]"

    jn = "|".join(map(re.escape, justices))
    an = "|".join(map(re.escape, adv)) or "(?!x)x"
    common = "|".join(sorted(set(justices) - DISTINCTIVE))
    voc = r"(^|[.?!,;:]\s*|--\s*)"            # start of a sentence/clause, for vocatives

    def mask(text, letter_of):
        x = text
        x = re.sub(r"\bMr\.\s+Chief\s+Justice\b", "[ADDRESS]", x, flags=re.I)
        x = re.sub(r",?\s*(?:and\s+)?may\s+it\s+please\s+the\s+Court\s*[:.,]?", "", x, flags=re.I)
        x = re.sub(r"\bChief\s+Justice(?:\s+(%s))?\b" % jn, lambda m: who(m.group(1), letter_of) if m.group(1) else "[PERSON]", x, flags=re.I)
        x = re.sub(r"\bJustices\s+(?:%s)(?:(?:,\s*and\s+|,\s*|\s+and\s+)(?:Justice\s+)?(?:%s))*\b" % (jn, jn), "[PERSON]", x, flags=re.I)
        x = re.sub(r"\bJustice\s+(%s)\b" % jn, lambda m: who(m.group(1), letter_of), x, flags=re.I)
        x = re.sub(r"\bJustice\s*(?=--)", "[PERSON] ", x)
        x = re.sub(r"\b(?:Mr|Ms|Mrs|Dr)\.\s+(%s)\b" % an, lambda m: who(m.group(1), letter_of), x, flags=re.I)
        x = re.sub(r"\bGeneral\s+(%s)\b" % an, lambda m: who(m.group(1), letter_of), x, flags=re.I)
        x = re.sub(r"\bYour\s+Honors?\b", "[ADDRESS]", x, flags=re.I)
        x = re.sub(voc + r"(Counsel|counsel|General|Justice|Chief)(?=\s*[,.?!])", lambda m: m.group(1) + "[ADDRESS]", x)
        x = re.sub(r"\b[Tt]he\s+Chief\b", "[PERSON]", x)
        x = re.sub(r"\b(%s)\b" % "|".join(sorted(DISTINCTIVE)), "[PERSON]", x, flags=re.I)
        x = re.sub(r"\b(%s)\b" % common, lambda m: m.group(0) if _case_name(x, m) else "[PERSON]", x)
        x = re.sub(r"\b(%s)\b" % an, lambda m: m.group(0) if _case_name(x, m) else "[PERSON]", x, flags=re.I)
        return " ".join(x.split())
    return mask


def _case_name(x, m):
    """True if a surname occurrence looks like part of a case name ('Jackson v. Virginia', 'v. Johnson', 'in Jackson')."""
    before, after = x[max(0, m.start() - 12):m.start()], x[m.end():m.end() + 4]
    return bool(re.match(r"\s+v\.", after) or re.search(r"(?:\bv\.\s+|\b(?:in|In|under|Under|see|See|cites?|citing)\s+)$", before))


LEAK_PATTERNS = {
    "current_justice_title": r"\b(?:Chief\s+)?Justice\s+(?:Roberts|Thomas|Alito|Sotomayor|Kagan|Gorsuch|Kavanaugh|Barrett|Jackson)\b",
    "vocative_chief": r"(?:^|[.?!,;:]\s*|--\s*)Chief\s*[,.?!]|\bMr\.\s+Chief\s+Justice\b|\b[Tt]he\s+Chief\b",
    "your_honor": r"\bYour\s+Honors?\b",
    "court_opening": r"may\s+it\s+please\s+the\s+Court",
    "vocative_counsel": r"(?:^|[.?!,;:]\s*|--\s*)[Cc]ounsel\s*[,.?!]",
}


def leak_counts(snips, names):
    """Count role/identity tokens remaining in the masked text, separately for same_span and for all windows."""
    out = {}
    for scope, keys in (("same_span", ("turns_same_span",)), ("all_windows", ("turns_same_span", "turns_pm15", "turns_pm60"))):
        c = {k: 0 for k in LEAK_PATTERNS}; c["participant_surnames"] = 0
        for s in snips:
            pat = re.compile(r"\b(%s)\b" % "|".join(map(re.escape, names[s["meeting"]])), re.I) if names[s["meeting"]] else None
            for key in keys:
                for t in s[key]:
                    for k, p in LEAK_PATTERNS.items(): c[k] += len(re.findall(p, t["text"]))
                    if pat:
                        c["participant_surnames"] += sum(1 for m in pat.finditer(t["text"]) if not _case_name(t["text"], m))
        out[scope] = c
    return out, []


# ---------- build ----------

def choose_dev_cases(cases, rng, k=DEV_CASES):
    """Pick k dev cases whose advocates do not appear in any test case (falls back to seeded order if impossible)."""
    dockets = sorted(cases); rng.shuffle(dockets)
    adv_of = {d: {surname_of(n) for n in cases[d]["advocates"]} for d in dockets}
    for i, a in enumerate(dockets):
        for j in range(i + 1, len(dockets)):
            for m in range(j + 1, len(dockets)):
                cand = {a, dockets[j], dockets[m]}
                dev_adv = set().union(*(adv_of[d] for d in cand))
                test_adv = set().union(*(adv_of[d] for d in dockets if d not in cand))
                if not (dev_adv & test_adv):
                    return cand
    return set(dockets[:k])


def build(src):
    cases, names_for_leak, all_snips = {}, {}, []
    for docket, (fname, case_name, date, _) in SOURCES.items():
        assert date >= EARLIEST_ALLOWED, docket
        lines = transcript_lines(src / fname)
        advocates = appearances(lines); turns = parse_turns(lines, advocates)
        cases[docket] = {"turns": turns, "advocates": advocates, "case": case_name, "date": date}
        names_for_leak[docket] = sorted({t["surname"] for t in turns} | {surname_of(n) for n in advocates} | set(JUSTICE_SURNAMES))
        for (i, j) in runs(turns):
            if not eligible(turns, i, j): continue
            k = min(j, i + MAX_TURNS)
            span = turns[i:k]
            justice = next(t["speaker"] for t in span if t["role"] == "justice")
            advocate = next(t["speaker"] for t in span if t["role"] == "advocate")
            all_snips.append({"docket": docket, "i": i, "k": k, "justice": justice, "advocate": advocate})
    for n, s in enumerate(all_snips): s["id"] = f"scotus-{s['docket']}-{s['i']:04d}"
    rng = random.Random(SEED)
    order = sorted(range(len(all_snips)), key=lambda n: all_snips[n]["id"]); rng.shuffle(order)
    justice_is_a = set(order[: len(order) // 2])
    dev = choose_dev_cases(cases, rng)
    raw, masked = [], []
    for n, s in enumerate(all_snips):
        c = cases[s["docket"]]; T = c["turns"]
        focal = {"A": s["justice"], "B": s["advocate"]} if n in justice_is_a else {"A": s["advocate"], "B": s["justice"]}
        windows = {"turns_same_span": (s["i"], s["k"])}
        for key, w in CONTEXTS: windows[f"turns_{key}"] = (max(0, s["i"] - w), min(len(T), s["k"] + w))
        mask = build_masker(T, c["advocates"])
        rec_raw = {"id": s["id"], "meeting": s["docket"], "case": c["case"], "argument_date": c["date"],
                   "split": "dev" if s["docket"] in dev else "test", "source": "supremecourt.gov OT2026 argument transcript",
                   "setting": SETTING,
                   "speakers": {"A": focal["A"], "B": focal["B"]},
                   "roles": {"A": "justice" if focal["A"] == s["justice"] else "advocate", "B": "justice" if focal["B"] == s["justice"] else "advocate"},
                   "professor": "A" if focal["A"] == s["justice"] else "B",
                   "turn_index": [s["i"], s["k"]], "n_turns": s["k"] - s["i"]}
        rec_masked = dict(rec_raw)
        for key, (a, b) in windows.items():
            lt, letter_of = letter_turns(T[a:b], focal)
            if key != "turns_same_span": lt = [t for t in lt if t["speaker"] in ("A", "B")]
            rec_raw[key] = lt
            rec_masked[key] = [{"speaker": t["speaker"], "text": mask(t["text"], letter_of)} for t in lt]
        rec_raw["masked"] = False; rec_masked["masked"] = True
        raw.append(rec_raw); masked.append(rec_masked)
    return raw, masked, cases, names_for_leak, dev


def dumps(rows): return "".join(json.dumps(r, ensure_ascii=False, sort_keys=False) + "\n" for r in rows)


def manifest(raw, masked, cases, names, dev, leaks, examples):
    import pypdf
    per_case = {d: {"case": c["case"], "argument_date": c["date"], "split": "dev" if d in dev else "test",
                    "file": SOURCES[d][0], "sha256": SOURCES[d][3], "url": BASE + SOURCES[d][0],
                    "turns": len(c["turns"]), "snippets": sum(r["meeting"] == d for r in raw),
                    "advocates_from_appearances": c["advocates"]} for d, c in cases.items()}
    def summ(rows):
        return {"snippets": len(rows), "justice_is_A": sum(r["professor"] == "A" for r in rows),
                "cases": len({r["meeting"] for r in rows}),
                "justice_advocate_pairs": len({(r["meeting"], r["speakers"]["A"], r["speakers"]["B"]) for r in rows}) if not rows or not rows[0]["masked"] else None}
    return {
        "dataset": "scotus_ot2026", "earliest_allowed_publication": EARLIEST_ALLOWED,
        "argument_dates": [min(c["date"] for c in cases.values()), max(c["date"] for c in cases.values())],
        "parameters": {"MIN_TURNS": MIN_TURNS, "MAX_TURNS": MAX_TURNS, "MIN_EACH": MIN_EACH, "MIN_WORDS": MIN_WORDS,
                       "contexts": dict(CONTEXTS), "seed": SEED, "dev_cases": DEV_CASES},
        "pypdf_version": pypdf.__version__,
        "totals": summ(raw), "dev": summ([r for r in raw if r["split"] == "dev"]), "test": summ([r for r in raw if r["split"] == "test"]),
        "justices_as_focal": {j: sum(j in r["speakers"].values() for r in raw) for j in sorted({v for r in raw for k, v in r["speakers"].items() if r["roles"][k] == "justice"})},
        "leak_check_masked": leaks, "leak_examples": examples, "cases": per_case,
        "files": {"snippets_raw.jsonl": hashlib.sha256(dumps(raw).encode()).hexdigest(),
                  "snippets_masked.jsonl": hashlib.sha256(dumps(masked).encode()).hexdigest()},
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sources", type=Path, default=ROOT / "sources" / "scotus_ot2026")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "scotus_ot2026")
    ap.add_argument("--download", action="store_true")
    ap.add_argument("--check", action="store_true", help="rebuild and compare with the committed files; write nothing")
    a = ap.parse_args()
    get_sources(a.sources, a.download)
    raw, masked, cases, names, dev = build(a.sources)
    leaks, examples = leak_counts(masked, names)
    man = manifest(raw, masked, cases, names, dev, leaks, examples)
    files = {"snippets_raw.jsonl": dumps(raw), "snippets_masked.jsonl": dumps(masked),
             "manifest.json": json.dumps(man, indent=2, ensure_ascii=False) + "\n"}
    t = man["totals"]
    print(f"cases: {t['cases']}; snippets: {t['snippets']} (dev {man['dev']['snippets']}, test {man['test']['snippets']}); "
          f"justice is A in {t['justice_is_A']}; leak check: {leaks}")
    hard = {s: {k: v for k, v in d.items() if v} for s, d in leaks.items()}
    if any(hard.values()): sys.exit(f"ERROR: role/identity tokens remain in masked text: {hard}")
    if a.check:
        bad = [n for n, body in files.items() if not (a.out / n).exists() or (a.out / n).read_text(encoding="utf-8") != body]
        if bad: sys.exit(f"check failed: {bad} differ from the committed files")
        print("check: rebuilt files match the committed files byte for byte"); return
    a.out.mkdir(parents=True, exist_ok=True)
    for n, body in files.items(): (a.out / n).write_text(body, encoding="utf-8")
    print(f"wrote {', '.join(files)} to {a.out}")


if __name__ == "__main__":
    main()
