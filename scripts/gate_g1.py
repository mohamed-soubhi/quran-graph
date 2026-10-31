"""Independent G1 gate check: ayah coverage per source + checksums of every raw file."""
import hashlib, json, re, zipfile
from pathlib import Path

RAW = Path("data/raw")
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()

def tanzil(name):
    keys = set()
    for l in (RAW / "tanzil" / name).read_text(encoding="utf-8").splitlines():
        p = l.split("|")
        if len(p) == 3 and p[0].isdigit():
            keys.add((int(p[0]), int(p[1])))
    return keys

ref = tanzil("quran-simple-clean.txt")
sets = {"tanzil uthmani": tanzil("quran-uthmani.txt"), "tanzil simple-clean": ref}
ik = RAW / "tafsir" / "ibn-kathir"
sets["ibn kathir files"] = {(int(p.parent.name), int(p.stem)) for p in ik.rglob("*.json")}
z = zipfile.ZipFile(RAW / "quranic-corpus" / "quranic-corpus-morphology-0.4.zip")
txt = z.read(z.namelist()[0]).decode("utf-8")
sets["quranic corpus"] = {tuple(map(int, m.groups())) for m in re.finditer(r"^\((\d+):(\d+):", txt, re.M)}
for k, s in sets.items():
    print(f"{k:20} surahs={len({a for a,_ in s}):3} ayat={len(s):4} same_as_tanzil={s == ref}")

# every raw file covered by CHECKSUMS.txt directly or via a MANIFEST listed there
listed = {}
for f in [RAW / "CHECKSUMS.txt", *RAW.rglob("MANIFEST.txt")]:
    for l in f.read_text(encoding="utf-8").splitlines():
        p = l.split()
        if len(p) >= 2 and re.fullmatch(r"[0-9a-f]{64}", p[0]):
            listed[p[1]] = p[0]
files = [p for p in RAW.rglob("*") if p.is_file() and p.name != "CHECKSUMS.txt"]
missing = [p for p in files if p.as_posix() not in listed]
bad = [p for p in files if p.as_posix() in listed and sha(p) != listed[p.as_posix()]]
print(f"raw files={len(files)} with checksum={len(files)-len(missing)} missing={len(missing)} mismatched={len(bad)}")
for p in missing[:10]: print("  missing:", p)
