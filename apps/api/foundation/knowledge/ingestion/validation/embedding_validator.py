# === TASK:WP-008:START ===
import math
from typing import Sequence
from ..errors import ValidationError

def validate_embedding(embedding: Sequence[float], expected_dim: int) -> None:
    if not isinstance(embedding, (list, tuple)):
        raise ValidationError("Embedding must be a list or tuple")
    if len(embedding) != expected_dim:
        raise ValidationError(
            f"Embedding dimension {len(embedding)} does not match expected {expected_dim}"
        )
    
    all_zeros = True
    for v in embedding:
        # Check type
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise ValidationError("Embedding values must be numeric")
        # Check finite
        if not math.isfinite(v):
            raise ValidationError("Embedding contains non-finite values (NaN or Infinity)")
        if v != 0.0:
            all_zeros = False
            
    if all_zeros:
        raise ValidationError("Production zero vectors are rejected")
# === TASK:WP-008:END ===
