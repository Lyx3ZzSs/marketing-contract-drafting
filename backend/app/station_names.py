"""Conservative, deterministic suggestions. Never infers official station aliases."""

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

RULE_VERSION = "2026-10-22.1"
KNOWN_TEMPLATE_SHA = "094d95c7471ba6295ca7f0d41fe587518c37d584c410eb398846cd17d62463f8"
WIND_COVER = {
    "station_suffix": "风电站",
    "product_line": "风电场功率预测系统V1.0",
    "document_line": "采购合同",
}
# Explicitly confirmed by the user; this does NOT authorize stripping other parentheses.
CONFIRMED_EXAMPLES = {"甘肃张掖市甘州区平山湖（中电建）风电场": "平山湖"}


@lru_cache
def region_paths() -> list[tuple[str, str, int]]:
    data = json.loads((Path(__file__).parent / "data/oa_regions.json").read_text())
    entries = data["entries"]
    paths = []
    for key in entries:
        parts: list[str] = []
        seen: set[str] = set()
        node = root = key
        while node in entries and node not in seen:
            seen.add(node)
            parts.insert(0, entries[node]["name"])
            root = node
            node = entries[node]["parent"]
        paths.append(("".join(parts), root, len(parts)))
    return sorted(paths, key=lambda item: len(item[0]), reverse=True)


def suggest_station(name: str, province_id: str | None) -> tuple[str, list[str]]:
    name = name.strip()
    if not name:
        return "", ["OA 未填写场站名称，请补充主体名"]
    if "光伏" in name or "集团侧" in name or not re.search(r"(?:风电场|风电站)$", name):
        return "", ["场站名称与风电模板不明确匹配，请核对后填写主体名"]
    if name in CONFIRMED_EXAMPLES:
        return CONFIRMED_EXAMPLES[name], []
    notes = []
    core = name
    match = next((p for p in region_paths() if name.startswith(p[0])), None)
    if match and match[2] == 3 and (not province_id or match[1] == province_id):
        core = name[len(match[0]) :]
    else:
        notes.append("行政区划未完整匹配或省份不一致，已保留前缀，请核对")
    # Only strip a terminal category, plus the explicitly observed duplicated suffixes.
    core = re.sub(r"(?:风电场|风电站)+$", "", core)
    if name.endswith("风电风电场"):
        core = re.sub(r"风电$", "", core)
    if re.search(r"[（(]", core):
        notes.append("括号可能含分期、编号或业主，已保留，请核对")
    if re.search(r"MW|万千瓦|集团|公司|中电建|国能|工程|项目|风电|风场|汇集站|升压站", core, re.I):
        notes.append("名称含业主、容量或项目描述，未自动删除，请核对")
    if re.search(r"[、,，/;&；]", core):
        notes.append("单条名称可能包含多个场站，请核对")
    if not core.strip():
        notes.append("提取后没有主体名，请手工填写")
    return core.strip(), notes


def group_stations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        code = str(row.get("station_code") or "").strip() or None
        name = str(row.get("station_name") or "").strip()
        # Missing names must remain separate rather than collapsing unrelated empty rows.
        key = f"code:{code}" if code else f"name:{name}" if name else f"row:{row['id']}"
        group = groups.setdefault(
            key, {"key": key, "station_code": code, "source_names": [], "provinces": []}
        )
        if name not in group["source_names"]:
            group["source_names"].append(name)
        province = str(row.get("province_id") or "").strip() or None
        if province not in group["provinces"]:
            group["provinces"].append(province)
    return list(groups.values())
