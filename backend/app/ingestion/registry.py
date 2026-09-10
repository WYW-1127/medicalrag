import hashlib
from pathlib import Path

_DOC_TYPES = {".json": "drug_label", ".csv": "structured_table"}


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()[:16]


def doc_type_for(suffix: str) -> str:
    return _DOC_TYPES.get(suffix.lower(), "guideline")


def department_for(path: Path, data_root: Path) -> str:
    """科室 = 格式目录（pdf/markdown/...）下的子目录名；无子目录则为「综合」。"""
    rel = path.relative_to(data_root).parts
    if len(rel) >= 3:  # {format}/{department}/{file}
        return rel[-2]
    return "综合"
