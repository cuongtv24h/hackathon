# === TASK:WP-008:START ===
from dataclasses import dataclass, field
from typing import List, Optional

@dataclass
class ChunkRecord:
    chunk_id: str = ""
    content: str = ""
    domain: str = ""
    sub_topic: str = ""
    source_id: str = ""
    source_section: str = ""
    source_page: str = ""
    version: str = ""
    is_active: bool = True
    approval_status: str = ""
    effective_date: str = ""
    tags: List[str] = field(default_factory=list)
    is_mock: bool = False
    answerable: bool = False
    content_hash: str = ""
    source_path: str = ""
    persistence_uuid: str = ""
    
    # Metadata fields
    chunker_version: str = "1.0"
    token_count: int = 0
    embedding_provider: str = ""
    embedding_model: str = ""
    embedding_dimensions: Optional[int] = None

    def __init__(self, **kwargs):
        self.tags = []
        for k, v in kwargs.items():
            setattr(self, k, v)


@dataclass
class SourceRecord:
    source_id: str = ""
    title: str = ""
    source_type: str = ""
    path: Optional[str] = None
    domain_code: str = ""
    version: str = ""
    approval_status: str = ""
    effective_date: str = ""
    is_mock: bool = False
    ingestible: bool = True
    is_active: bool = True

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


@dataclass
class ImportPlan:
    to_insert: List[ChunkRecord] = field(default_factory=list)
    to_update: List[ChunkRecord] = field(default_factory=list)
    to_skip: List[ChunkRecord] = field(default_factory=list)
    to_retire: List[str] = field(default_factory=list)

    def __init__(self, **kwargs):
        self.to_insert = []
        self.to_update = []
        self.to_skip = []
        self.to_retire = []
        for k, v in kwargs.items():
            setattr(self, k, v)


@dataclass
class IngestionResult:
    total_chunks: int = 0
    answerable_chunks: int = 0
    mock_chunks: int = 0
    approved_chunks: int = 0
    errors: List[str] = field(default_factory=list)
    chunk_records: List[ChunkRecord] = field(default_factory=list)
    inserted: int = 0
    updated: int = 0
    retired: int = 0
    vector_dim: Optional[int] = None

    def __init__(self, **kwargs):
        self.errors = []
        self.chunk_records = []
        self.inserted = 0
        self.updated = 0
        self.retired = 0
        self.vector_dim = None
        for k, v in kwargs.items():
            setattr(self, k, v)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0
# === TASK:WP-008:END ===
