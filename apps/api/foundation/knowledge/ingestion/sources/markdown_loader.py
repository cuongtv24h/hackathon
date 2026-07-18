# === TASK:WP-008:START ===
from pathlib import Path
from typing import Dict, Tuple, Any

def read_markdown(path: Path) -> Tuple[Dict[str, Any], str]:
    """Read a markdown file, strip frontmatter, return (frontmatter_dict, body_text)."""
    content = path.read_text(encoding="utf-8")
    fm = {}
    body = content
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            fm_text = parts[1].strip()
            body = parts[2].strip()
            for line in fm_text.split("\n"):
                if ":" in line:
                    key, _, val = line.partition(":")
                    fm[key.strip()] = val.strip()
    return fm, body
# === TASK:WP-008:END ===
