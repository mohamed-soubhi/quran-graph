"""G3 gate: two consecutive full loads give identical exact counts; no ayah without a tafsir segment.

Usage: .venv\\Scripts\\python.exe -X utf8 scripts\\gate_g3.py
Exit code 0 = every check passed.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.graph.client import get_driver  # noqa: E402
from src.graph.load import load_l0_l1  # noqa: E402

# docs/tickets/G3.md
EXPECTED_NODES = {"Surah": 114, "Ayah": 6236, "Word": 77429, "Lemma": 4832, "Root": 1642,
                  "Mufassir": 1, "TafsirBook": 1, "TafsirSegment": 1911}
EXPECTED_RELS = {"HAS_AYAH": 6236, "NEXT_Ayah": 6235, "HAS_WORD": 77429, "HAS_LEMMA": 74608, "HAS_ROOT": 49968,
                 "LEMMA_OF_ROOT": 4657, "WROTE": 1, "HAS_SEGMENT": 1911, "COVERS": 6236, "NEXT_TafsirSegment": 1910}


def snapshot(driver) -> dict:
    run = lambda q: driver.execute_query(q).records  # noqa: E731
    nodes = {r["l"]: r["n"] for r in run("MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS n")}
    rels = {r["t"]: r["n"] for r in run("MATCH ()-[r]->() WHERE type(r) <> 'NEXT' RETURN type(r) AS t, count(*) AS n")}
    rels.update({f"NEXT_{r['l']}": r["n"] for r in run(
        "MATCH (a)-[:NEXT]->() RETURN labels(a)[0] AS l, count(*) AS n")})
    checks = {
        "ayat_without_covers": run("MATCH (a:Ayah) WHERE NOT (a)<-[:COVERS]-() RETURN count(a) AS n")[0]["n"],
        "ayat_with_2_covers": run(
            "MATCH (a:Ayah)<-[c:COVERS]-() WITH a, count(c) AS k WHERE k > 1 RETURN count(a) AS n")[0]["n"],
        "rels_without_provenance": run(
            "MATCH ()-[r]->() WHERE r.source IS NULL OR r.method IS NULL OR r.confidence IS NULL "
            "RETURN count(r) AS n")[0]["n"],
        "kursi_segment": run("MATCH (:Ayah {ayah_id:'2:255'})<-[:COVERS]-(g) RETURN g.segment_id AS s")[0]["s"],
        "smw_lemmas": run("MATCH (:Root {root_id:'سمو'})<-[:LEMMA_OF_ROOT]-(l) RETURN count(l) AS n")[0]["n"],
        "smw_words": run("MATCH (:Root {root_id:'سمو'})<-[:HAS_ROOT]-(w) RETURN count(w) AS n")[0]["n"],
    }
    return {"nodes": nodes, "rels": rels, "checks": checks}


def main() -> int:
    driver = get_driver()
    results, failures = [], []
    for run_no in (1, 2):
        t0 = time.time()
        load_l0_l1(surah=None, driver=driver)
        snap = snapshot(driver)
        snap["seconds"] = round(time.time() - t0, 1)
        results.append(snap)
        print(f"run {run_no}: {snap['seconds']} s")
        print("  nodes:", snap["nodes"])
        print("  rels: ", snap["rels"])
        print("  checks:", snap["checks"])
    driver.close()

    first, second = results
    if first["nodes"] != EXPECTED_NODES:
        failures.append(f"node counts differ from G3 table: {first['nodes']}")
    if first["rels"] != EXPECTED_RELS:
        failures.append(f"relationship counts differ from G3 table: {first['rels']}")
    if (first["nodes"], first["rels"]) != (second["nodes"], second["rels"]):
        failures.append("second run changed the counts")
    expected_checks = {"ayat_without_covers": 0, "ayat_with_2_covers": 0, "rels_without_provenance": 0,
                       "kursi_segment": "ibn-kathir:2:255-255:1", "smw_lemmas": 6, "smw_words": 381}
    for snap in results:
        if snap["checks"] != expected_checks:
            failures.append(f"checks differ: {snap['checks']}")

    print("G3:", "PASS" if not failures else "FAIL")
    for f in failures:
        print("  -", f)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
