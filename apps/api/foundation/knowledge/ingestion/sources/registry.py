# === TASK:WP-008:START ===
import json
from pathlib import Path
from typing import List, Dict, Any
from ..models import SourceRecord

ROOT = Path(__file__).resolve().parents[6]
SEED_DIR = ROOT / "data" / "mvp" / "seed"

def load_seed_registry() -> Dict[str, Any]:
    path = SEED_DIR / "source-registry.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_knowledge_base() -> Dict[str, Any]:
    path = SEED_DIR / "knowledge-base.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_eligible_sources(registry: Dict[str, Any] = None) -> List[SourceRecord]:
    if registry is None:
        registry = load_seed_registry()
        
    sources = []
    for src in registry.get("sources", []):
        # We construct SourceRecord for all registry entries
        sources.append(SourceRecord(
            source_id=src.get("source_id", ""),
            title=src.get("title", ""),
            source_type=src.get("source_type", ""),
            path=src.get("path"),
            domain_code=src.get("domain_code", ""),
            version=src.get("version", "1.0"),
            approval_status=src.get("approval_status", ""),
            effective_date=src.get("effective_date", ""),
            is_mock=src.get("is_mock", False),
            ingestible=src.get("ingestible", True),
            is_active=src.get("is_active", True)
        ))
    return sources
# === TASK:WP-008:END ===
