# === TASK:WP-008:START ===
from typing import List, Dict, Any
from .faq_chunker import split_faq_chunks
from .table_chunker import split_table_chunks
from .prose_chunker import split_prose_chunks
from .token_counter import TokenCounter
from ..errors import ValidationError

def select_chunker_and_split(
    source_id: str,
    path: str,
    content: str,
    token_counter: TokenCounter
) -> List[Dict[str, Any]]:
    path_str = str(path or "").lower()
    source_id_lower = source_id.lower()
    
    # 1. Detect FAQ
    if "faq" in path_str or "faq" in source_id_lower or "┌" in content:
        chunks = split_faq_chunks(content)
        if not chunks:
            raise ValidationError(f"Source {source_id} routed to FAQ chunker but no boxes found.")
        return chunks
        
    # 2. Detect Price/Table
    elif "price" in source_id_lower or "bieugia" in path_str or "bang_gia" in path_str or "table" in path_str:
        chunks = split_table_chunks(content)
        if not chunks:
            raise ValidationError(f"Source {source_id} routed to Table chunker but no valid tables found.")
        return chunks
        
    # 3. Detect Prose
    elif path_str.endswith(".md") or content:
        doc_title = ""
        for line in content.splitlines():
            if line.strip().startswith("# ") and not line.strip().startswith("##"):
                doc_title = line.strip().lstrip("#").strip()
                break
        chunks = split_prose_chunks(content, token_counter, doc_title=doc_title)
        return chunks
        
    else:
        raise ValidationError(f"Unsupported document form or unable to parse source {source_id} safely.")
# === TASK:WP-008:END ===
