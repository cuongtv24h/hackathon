# === TASK:WP-008:START ===
from pathlib import Path
from ..models import SourceRecord
from ..errors import ValidationError

ROOT = Path(__file__).resolve().parents[6]

def validate_source(src: SourceRecord, current_date_str: str = "2026-07-18") -> None:
    # 1. Registry identity
    if not src.source_id:
        raise ValidationError("Source is missing source_id")
        
    # 2. Path existence
    if src.path:
        full_path = ROOT / src.path
        if not full_path.is_file() and not src.is_mock:
            raise ValidationError(f"Source {src.source_id} path not found: {src.path}")
            
    # 3. Ingestibility
    if not src.ingestible:
        raise ValidationError(f"Source {src.source_id} is marked as non-ingestible")
        
    # 4. Approval status
    valid_approvals = {"approved_for_pilot", "approved", "mock"}
    if src.approval_status not in valid_approvals:
        raise ValidationError(f"Source {src.source_id} has invalid approval status: {src.approval_status}")
        
    # 5. Active state
    if not src.is_active:
        raise ValidationError(f"Source {src.source_id} is inactive")
        
    # 6. Effective date
    if src.effective_date:
        if src.effective_date > current_date_str:
            raise ValidationError(
                f"Source {src.source_id} is not effective yet: "
                f"effective date {src.effective_date} is after {current_date_str}"
            )
# === TASK:WP-008:END ===
