# === TASK:WP-008:START ===
from ..models import ChunkRecord
from ..errors import ValidationError

def validate_chunk(rec: ChunkRecord, hard_max_tokens: int = 800) -> None:
    if not rec.chunk_id:
        raise ValidationError("Chunk missing chunk_id")
    if not rec.content or not rec.content.strip():
        raise ValidationError(f"Chunk {rec.chunk_id} has empty content")
    if not rec.source_id:
        raise ValidationError(f"Chunk {rec.chunk_id} missing source_id")
    if not rec.domain:
        raise ValidationError(f"Chunk {rec.chunk_id} missing domain")
    if rec.token_count > hard_max_tokens:
        raise ValidationError(f"Chunk {rec.chunk_id} exceeds token limit: {rec.token_count} > {hard_max_tokens}")
    # Citation metadata check
    if rec.answerable and not rec.source_section and not rec.source_page:
        raise ValidationError(f"Chunk {rec.chunk_id} is answerable but missing structural citation locator")
# === TASK:WP-008:END ===
