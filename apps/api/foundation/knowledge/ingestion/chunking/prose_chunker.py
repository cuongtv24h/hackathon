# === TASK:WP-008:START ===
from typing import List, Dict, Any
from .token_counter import TokenCounter

def split_prose_chunks(content: str, token_counter: TokenCounter, doc_title: str = "") -> List[Dict[str, Any]]:
    lines = content.splitlines()
    
    sections = []
    current_h2 = ""
    current_h3 = ""
    current_lines = []
    
    def flush_section():
        if current_lines:
            sections.append({
                "h2": current_h2,
                "h3": current_h3,
                "text": "\n".join(current_lines).strip()
            })
            current_lines.clear()
            
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith("## ") and not line_stripped.startswith("###"):
            flush_section()
            current_h2 = line_stripped[3:].strip()
            current_h3 = ""
        elif line_stripped.startswith("### "):
            flush_section()
            current_h3 = line_stripped[4:].strip()
        else:
            current_lines.append(line)
            
    flush_section()
    
    chunks = []
    
    for sec in sections:
        heading_parts = []
        if doc_title:
            heading_parts.append(f"# {doc_title}")
        if sec["h2"]:
            heading_parts.append(f"## {sec['h2']}")
        if sec["h3"]:
            heading_parts.append(f"### {sec['h3']}")
            
        heading_context = "\n".join(heading_parts) + "\n\n" if heading_parts else ""
        
        section_text = sec["text"]
        full_text = heading_context + section_text
        
        # If the entire section fits, keep it as a single chunk
        if token_counter.count(full_text) <= token_counter.hard_max:
            sub_topic = sec["h3"] or sec["h2"] or "general"
            source_section = sec["h2"] or "general"
            chunks.append({
                "content": full_text,
                "sub_topic": sub_topic,
                "source_section": source_section,
            })
        else:
            # Split section text by paragraph boundaries
            paragraphs = section_text.split("\n\n")
            current_chunk_parts = []
            
            sub_topic = sec["h3"] or sec["h2"] or "general"
            source_section = sec["h2"] or "general"
            
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                
                # Check if adding this paragraph exceeds the limit
                temp_text = heading_context + "\n\n".join(current_chunk_parts + [para])
                if token_counter.count(temp_text) <= token_counter.hard_max:
                    current_chunk_parts.append(para)
                else:
                    # Flush the current chunk
                    if current_chunk_parts:
                        chunk_content = heading_context + "\n\n".join(current_chunk_parts)
                        chunks.append({
                            "content": chunk_content,
                            "sub_topic": sub_topic,
                            "source_section": source_section,
                        })
                        
                        # Overlap: gather trailing paragraphs up to overlap_max tokens
                        overlap_parts = []
                        overlap_tokens = 0
                        for p in reversed(current_chunk_parts):
                            p_tok = token_counter.count(p)
                            if overlap_tokens + p_tok <= token_counter.overlap_max:
                                overlap_parts.insert(0, p)
                                overlap_tokens += p_tok
                            else:
                                break
                        current_chunk_parts = overlap_parts
                    
                    # Add paragraph. If a single paragraph is too large, split it by line
                    if token_counter.count(heading_context + para) > token_counter.hard_max:
                        sub_lines = para.split("\n")
                        for sl in sub_lines:
                            sl = sl.strip()
                            if not sl:
                                continue
                            temp_text = heading_context + "\n\n".join(current_chunk_parts + [sl])
                            if token_counter.count(temp_text) <= token_counter.hard_max:
                                current_chunk_parts.append(sl)
                            else:
                                if current_chunk_parts:
                                    chunk_content = heading_context + "\n\n".join(current_chunk_parts)
                                    chunks.append({
                                        "content": chunk_content,
                                        "sub_topic": sub_topic,
                                        "source_section": source_section,
                                    })
                                    current_chunk_parts = []
                                current_chunk_parts.append(sl)
                    else:
                        current_chunk_parts.append(para)
                        
            if current_chunk_parts:
                chunk_content = heading_context + "\n\n".join(current_chunk_parts)
                chunks.append({
                    "content": chunk_content,
                    "sub_topic": sub_topic,
                    "source_section": source_section,
                })
                
    return chunks
# === TASK:WP-008:END ===
