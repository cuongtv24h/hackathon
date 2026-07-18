# === TASK:WP-008:START ===
from typing import List, Dict, Any

def split_table_chunks(content: str) -> List[Dict[str, Any]]:
    lines = content.splitlines()
    doc_title = ""
    section_heading = ""
    
    chunks = []
    
    i = 0
    while i < len(lines):
        line = lines[i]
        line_stripped = line.strip()
        
        if line_stripped.startswith("# ") and not line_stripped.startswith("##"):
            doc_title = line_stripped
            i += 1
            continue
        elif line_stripped.startswith("## ") and not line_stripped.startswith("###"):
            section_heading = line_stripped
            i += 1
            continue
        elif line_stripped.startswith("### "):
            section_heading = line_stripped
            i += 1
            continue
            
        # Check if table starts
        if line_stripped.startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i].strip())
                i += 1
            
            if len(table_lines) >= 3:
                header = table_lines[0]
                separator = table_lines[1]
                for data_row in table_lines[2:]:
                    # Skip empty or separator rows
                    cleaned_row = data_row.replace("|", "").replace("-", "").replace(":", "").strip()
                    if not any(c.isalnum() for c in cleaned_row):
                        continue
                    
                    # Construct chunk content
                    parts = []
                    if doc_title:
                        parts.append(doc_title)
                    if section_heading:
                        parts.append(section_heading)
                    parts.append(header)
                    parts.append(separator)
                    parts.append(data_row)
                    
                    chunk_text = "\n".join(parts)
                    
                    # Clean section heading for metadata
                    clean_section = section_heading.lstrip("#").strip() if section_heading else "general"
                    
                    chunks.append({
                        "content": chunk_text,
                        "sub_topic": clean_section,
                        "source_section": clean_section,
                    })
            continue
            
        i += 1
    return chunks
# === TASK:WP-008:END ===
