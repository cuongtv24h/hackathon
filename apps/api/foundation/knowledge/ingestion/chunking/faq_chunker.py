# === TASK:WP-008:START ===
import re
from typing import List, Dict, Any


_FAQ_TOPIC_PATTERN = re.compile(
    r"CÂU\s+HỎI\s+\d+\s*:\s*.*?trường\s+hợp\s+(.+?)\s+số\s+\d+\s*;",
    re.IGNORECASE,
)


def _infer_faq_topic(parsed_text: str, fallback: str) -> str:
    """Infer the FAQ group from the question when source headings are missing.

    The canonical FAQ corpus changes topic every 100 questions but only contains
    one Markdown H2. Its question text consistently names the topic, so using the
    text is safer than relying on numeric ranges or one stale heading.
    """
    match = _FAQ_TOPIC_PATTERN.search(parsed_text)
    if not match:
        return fallback
    topic = " ".join(match.group(1).split()).strip(" .,:;-")
    return topic[0].upper() + topic[1:] if topic else fallback

def _parse_box_lines(lines: List[str]) -> str:
    paragraphs = []
    current_para = []
    for line in lines:
        cleaned = line.strip()
        if cleaned.startswith("│") and cleaned.endswith("│"):
            content = cleaned[1:-1].strip()
        else:
            content = cleaned
        
        if not content:
            if current_para:
                paragraphs.append(" ".join(current_para))
                current_para = []
        else:
            current_para.append(content)
            
    if current_para:
        paragraphs.append(" ".join(current_para))
        
    return "\n\n".join(paragraphs)


def split_faq_chunks(content: str) -> List[Dict[str, Any]]:
    chunks = []
    lines = content.splitlines()
    in_box = False
    box_lines = []
    current_section = "general"
    
    for line in lines:
        line_stripped = line.strip()
        if line_stripped.startswith("## "):
            current_section = line_stripped.lstrip("#").strip()
            continue
            
        # Start of box
        if line_stripped.startswith("┌") and line_stripped.endswith("┐"):
            in_box = True
            box_lines = []
        # End of box
        elif line_stripped.startswith("└") and line_stripped.endswith("┘"):
            if in_box:
                in_box = False
                parsed_text = _parse_box_lines(box_lines)
                if parsed_text:
                    chunk_topic = _infer_faq_topic(parsed_text, current_section)
                    chunks.append({
                        "content": parsed_text,
                        "sub_topic": chunk_topic,
                        "source_section": chunk_topic,
                    })
        elif in_box:
            box_lines.append(line)
            
    return chunks
# === TASK:WP-008:END ===
