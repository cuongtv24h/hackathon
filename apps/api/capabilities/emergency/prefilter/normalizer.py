# === TASK:WP-202:START ===
import unicodedata
from dataclasses import dataclass

@dataclass(frozen=True)
class NormalizedText:
    original: str
    normalized_nfc: str
    diacritic_free: str

def remove_vietnamese_diacritics(text: str) -> str:
    """Decompose characters and remove combining marks, mapping 'đ' -> 'd'."""
    decomposed = unicodedata.normalize("NFD", text)
    without_marks = "".join(c for c in decomposed if not unicodedata.combining(c))
    return without_marks.replace("đ", "d").replace("Đ", "D")

def normalize_text(text: str) -> NormalizedText:
    if not text:
        return NormalizedText("", "", "")
    nfc = unicodedata.normalize("NFC", text)
    lower_nfc = nfc.lower()
    diacritic_free = remove_vietnamese_diacritics(lower_nfc)
    return NormalizedText(
        original=text,
        normalized_nfc=lower_nfc,
        diacritic_free=diacritic_free
    )
# === TASK:WP-202:END ===
