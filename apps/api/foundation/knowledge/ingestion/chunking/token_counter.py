# === TASK:WP-008:START ===
import re
from ..settings import HARD_MAX_TOKENS, TARGET_MIN_TOKENS, TARGET_MAX_TOKENS, PROSE_OVERLAP_TOKENS, CHAR_CEILING

class TokenCounter:
    """Deterministic token counter based on Unicode words and punctuation marks."""

    def __init__(
        self,
        target_min: int = TARGET_MIN_TOKENS,
        target_max: int = TARGET_MAX_TOKENS,
        hard_max: int = HARD_MAX_TOKENS,
        overlap_max: int = PROSE_OVERLAP_TOKENS,
        char_ceiling: int = CHAR_CEILING
    ):
        self.target_min = target_min
        self.target_max = target_max
        self.hard_max = hard_max
        self.overlap_max = overlap_max
        self.char_ceiling = char_ceiling

    def count(self, text: str) -> int:
        if not text:
            return 0
        # Split on word boundaries or individual punctuation marks, ignoring whitespace
        tokens = re.findall(r'\w+|[^\w\s]', text, re.UNICODE)
        return len(tokens)
# === TASK:WP-008:END ===
