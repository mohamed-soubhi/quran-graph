"""G4 gate (Phase 4): read-only checks on Neo4j and the span JSONL files.

Checks:
  1. L0/L1 unchanged: every G3 node/relationship count still exact (Phase 4 must not touch L0/L1).
  2. Span counts in Neo4j equal the JSONL files, per type, plus INSIDE edges.
  3. Coverage in Neo4j (test-queries 11.1-11.3): no gap, no overlap, child inside parent, one parent.
  4. Provenance: no relationship without source, method, confidence.
  5. Stored HADITH spans (the ones in the graph) against the gold set: precision, recall, mean IoU.
  6. Gate 4c on the JSONL files (scripts/gate_4c.py exit code).

Gate 4a (scripts/eval_4a.py) and Gate 4b (scripts/eval_4b.py --runs 3) run separately; see docs/tickets/G4.md.

Usage: .venv\\Scripts\\python.exe -X utf8 scripts\\gate_g4.py
Exit code 0 = every check passed. Never writes to Neo4j.
"""

from collections import Counter
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.gate_g3 import EXPECTED_NODES, EXPECTED_RELS  # noqa: E402
from src.extract.hadith_spans import match_spans_one_to_one  # noqa: E402
from src.graph.client import get_driver  # noqa: E402

SPANS = ROOT / "data" / "interim" / "spans"
GOLD = ROOT / "data" / "gold" / "phase4.jsonl"
SPAN_FILES = {"FOOTNOTE": "footnotes.jsonl", "QURAN": "quran.jsonl", "HADITH": "hadith.jsonl",
              "OTHER": "poetry.jsonl", "COMMENTARY": "commentary.jsonl"}

Q_COVER = """MATCH (g:TafsirSegment) OPTIONAL MATCH (g)-[:HAS_SPAN]->(s:Span) WHERE NOT (s)-[:INSIDE]->()
WITH g, sum(s.end - s.start) AS covered WHERE covered <> size(g.text) RETURN count(g) AS n"""
Q_OVERLAP = """MATCH (g:TafsirSegment)-[:HAS_SPAN]->(s:Span) WHERE NOT (s)-[:INSIDE]->()
WITH g, s ORDER BY s.start WITH g, collect(s) AS ss UNWIND range(0, size(ss) - 2) AS i
WITH ss[i] AS a, ss[i + 1] AS b WHERE a.end > b.start RETURN count(*) AS n"""
Q_OUTSIDE = "MATCH (c:Span)-[:INSIDE]->(p:Span) WHERE c.start < p.start OR c.end > p.end RETURN count(*) AS n"
Q_TWO_PARENTS = "MATCH (c:Span)-[r:INSIDE]->() WITH c, count(r) AS k WHERE k > 1 RETURN count(c) AS n"
Q_NO_PROV = ("MATCH ()-[r]->() WHERE r.source IS NULL OR r.method IS NULL OR r.confidence IS NULL "
             "RETURN count(r) AS n")


def count_lines(path: Path) -> int:
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def stored_hadith_vs_gold(driver) -> dict:
    """Score the HADITH spans stored in Neo4j that overlap the 50 gold windows."""
    windows = [json.loads(line) for line in open(GOLD, encoding="utf-8") if line.strip()]
    gold = [{"window_id": w["window_id"], "segment_id": w["segment_id"], **sp}
            for w in windows for sp in w["spans"] if sp["type"] == "HADITH"]
    rows = driver.execute_query(
        "MATCH (g:TafsirSegment)-[:HAS_SPAN]->(s:Span {type:'HADITH'}) WHERE g.segment_id IN $ids "
        "RETURN g.segment_id AS segment_id, s.start AS start, s.end AS end, s.kind AS kind",
        ids=sorted({w["segment_id"] for w in windows})).records
    pred = []
    for r in rows:
        for w in windows:
            if w["segment_id"] == r["segment_id"] and r["start"] < w["window_end"] and r["end"] > w["window_start"]:
                pred.append({**r.data(), "window_id": w["window_id"]})
                break
    pairs, fps, misses = [], [], []
    for wid in {w["window_id"] for w in windows}:
        p, fp, m = match_spans_one_to_one([x for x in pred if x["window_id"] == wid],
                                          [g for g in gold if g["window_id"] == wid], min_iou=0.5)
        pairs += p
        fps += fp
        misses += m
    n = len(pairs)
    return {
        "predicted": len(pred), "gold": len(gold), "matched": n,
        "precision": n / len(pred) if pred else 0.0,
        "recall": n / len(gold) if gold else 0.0,
        "mean_iou": sum(x[2] for x in pairs) / n if n else 0.0,
        "kind_accuracy": sum(1 for p, g, _ in pairs if p["kind"] == g["kind"]) / n if n else 0.0,
        "false_positives": [f"{x['segment_id']}#{x['start']}-{x['end']}" for x in fps],
        "misses": [f"{x['segment_id']}#{x['start']}-{x['end']} ({x['kind']})" for x in misses],
    }


def main() -> int:
    failures = []
    driver = get_driver()
    run = lambda q: driver.execute_query(q).records  # noqa: E731

    # 1. L0/L1 unchanged
    nodes = {r["l"]: r["n"] for r in run("MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS n")}
    rels = {r["t"]: r["n"] for r in run("MATCH ()-[r]->() WHERE type(r) <> 'NEXT' RETURN type(r) AS t, count(*) AS n")}
    rels.update({f"NEXT_{r['l']}": r["n"] for r in run("MATCH (a)-[:NEXT]->() RETURN labels(a)[0] AS l, count(*) AS n")})
    l01_nodes = {k: nodes.get(k) for k in EXPECTED_NODES}
    l01_rels = {k: rels.get(k) for k in EXPECTED_RELS}
    print("1. L0/L1 nodes:", "OK" if l01_nodes == EXPECTED_NODES else l01_nodes)
    print("   L0/L1 rels: ", "OK" if l01_rels == EXPECTED_RELS else l01_rels)
    if l01_nodes != EXPECTED_NODES or l01_rels != EXPECTED_RELS:
        failures.append("L0/L1 counts differ from the G3 table")
    uncovered = run("MATCH (a:Ayah) WHERE NOT (a)<-[:COVERS]-() RETURN count(a) AS n")[0]["n"]
    print("   ayat without a segment:", uncovered)
    if uncovered:
        failures.append(f"{uncovered} ayat without a segment")

    # 2. Span counts: Neo4j vs JSONL
    db = {r["t"]: r["n"] for r in run("MATCH (:TafsirSegment)-[:HAS_SPAN]->(s:Span) RETURN s.type AS t, count(*) AS n")}
    all_spans = run("MATCH (s:Span) RETURN count(s) AS n")[0]["n"]
    files = {t: count_lines(SPANS / f) for t, f in SPAN_FILES.items()}
    inside_db = rels.get("INSIDE", 0)
    inside_file = count_lines(SPANS / "parents.jsonl")
    print("2. spans (Neo4j / JSONL):")
    for t in SPAN_FILES:
        print(f"   {t:<10} {db.get(t, 0):>7,} / {files[t]:>7,}")
    print(f"   INSIDE     {inside_db:>7,} / {inside_file:>7,}")
    print(f"   Span nodes total {all_spans:,} (with HAS_SPAN {sum(db.values()):,})")
    if db != files or inside_db != inside_file or all_spans != sum(db.values()):
        failures.append("Neo4j span counts differ from the JSONL files")

    # 3. Coverage in Neo4j
    cov = {"11.1 segments not fully covered": run(Q_COVER)[0]["n"],
           "11.2 overlapping top-level pairs": run(Q_OVERLAP)[0]["n"],
           "11.3 child outside its parent": run(Q_OUTSIDE)[0]["n"],
           "11.3 child with 2+ parents": run(Q_TWO_PARENTS)[0]["n"]}
    print("3. coverage:", cov)
    failures += [f"{k} = {v}" for k, v in cov.items() if v]

    # 4. Provenance
    no_prov = run(Q_NO_PROV)[0]["n"]
    print("4. relationships without provenance:", no_prov)
    if no_prov:
        failures.append(f"{no_prov} relationships without provenance")

    # 5. Stored HADITH spans vs gold (same targets as Gate 4b)
    h = stored_hadith_vs_gold(driver)
    driver.close()
    print(f"5. stored HADITH vs gold: predicted {h['predicted']}, gold {h['gold']}, matched {h['matched']}; "
          f"P {h['precision']:.1%}, R {h['recall']:.1%}, mean IoU {h['mean_iou']:.4f}, kind {h['kind_accuracy']:.1%}")
    for x in h["false_positives"]:
        print("   false positive:", x)
    for x in h["misses"]:
        print("   missed:", x)
    if h["precision"] < 0.90 or h["recall"] < 0.80 or h["mean_iou"] < 0.90:
        failures.append("stored HADITH spans miss the Gate 4b targets")

    # 6. Gate 4c on the JSONL files
    res = subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts" / "gate_4c.py")], cwd=ROOT,
                         capture_output=True, text=True, encoding="utf-8")
    last = [line for line in res.stdout.splitlines() if "Overall" in line]
    print("6. gate 4c (JSONL):", last[-1].strip() if last else f"exit {res.returncode}")
    if res.returncode != 0:
        failures.append("gate 4c failed on the JSONL files")

    print("G4 checks:", "PASS" if not failures else "FAIL")
    for f in failures:
        print("  -", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
