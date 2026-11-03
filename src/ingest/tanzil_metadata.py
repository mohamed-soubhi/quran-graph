"""Parser for Tanzil Quran metadata XML (T3.1).

Parses quran-data.xml to extract surah metadata:
- index, ayas, start, name, tname, ename, type, order, rukus
"""

import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.log import get_logger

RAW_DIR = ROOT / "data" / "raw"
TANZIL_DIR = RAW_DIR / "tanzil"
DEFAULT_METADATA_PATH = TANZIL_DIR / "quran-data.xml"

logger = get_logger("tanzil_metadata")


def read_suras(path: Path | str = DEFAULT_METADATA_PATH) -> list[dict[str, Any]]:
    """Parse Tanzil quran-data.xml and return a list of surah dicts.

    Each dict contains:
    - index: int (1..114)
    - ayas: int
    - start: int (0-based starting ayah index across Quran)
    - name: str (Arabic surah name)
    - tname: str (transliterated name)
    - ename: str (English name)
    - type: str ("Meccan" or "Medinan")
    - order: int (chronological revelation order)
    - rukus: int (number of rukus)
    """
    path_obj = Path(path)
    if not path_obj.exists():
        raise FileNotFoundError(f"Tanzil metadata XML file not found at: {path_obj}")

    with open(path_obj, "r", encoding="utf-8") as f:
        tree = ET.parse(f)

    root = tree.getroot()
    suras_elements = root.findall(".//sura")

    suras: list[dict[str, Any]] = []
    for elem in suras_elements:
        suras.append(
            {
                "index": int(elem.attrib["index"]),
                "ayas": int(elem.attrib["ayas"]),
                "start": int(elem.attrib["start"]),
                "name": elem.attrib["name"],
                "tname": elem.attrib["tname"],
                "ename": elem.attrib["ename"],
                "type": elem.attrib["type"],
                "order": int(elem.attrib["order"]),
                "rukus": int(elem.attrib["rukus"]),
            }
        )

    logger.info("Parsed %d suras from %s", len(suras), path_obj)
    return suras
