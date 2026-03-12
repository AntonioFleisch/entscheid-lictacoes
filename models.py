from pydantic import BaseModel, EmailStr, Field, model_validator
from enum import Enum
from typing import Optional, List, Any
from datetime import datetime

class WorkflowStatus(str, Enum):
    watching = "watching"
    participating = "participating"
    won = "won"
    lost = "lost"
    discarded = "discarded"

class IngestAction(str, Enum):
    watch = "watch"
    participate = "participate"
    discard = "discard"

class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str

class WorkflowItemCreate(BaseModel):
    tender_id: str
    status: WorkflowStatus = WorkflowStatus.watching
    action: IngestAction = IngestAction.watch

class WorkflowItemUpdate(BaseModel):
    status: WorkflowStatus

class WorkflowItemResponse(BaseModel):
    id: str
    user_email: str
    tender_id: str
    status: WorkflowStatus
    created_at: datetime
    updated_at: datetime


class PNCPItem(BaseModel):
    # Minimal validation: We allow flexible ingestion but track failures later if key fields are missing.
    # We don't enforce strict types on all fields to allow partial data.
    numeroControlePNCP: Optional[str] = None
    external_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    
    class Config:
        extra = "allow"

class PNCPBatch(BaseModel):
    source: Optional[str] = None
    run_id: Optional[str] = None
    window: Optional[dict] = None
    meta: Optional[dict] = None
    items: List[dict] # Accepting dicts to allow flexible parsing before validation, or PNCPItem
    
    @model_validator(mode='before')
    @classmethod
    def normalize_envelope(cls, data: Any) -> Any:
        if isinstance(data, dict):
            meta = data.get("meta", {})
            
            # 1. Normalize run_id
            if not data.get("run_id") and meta.get("run_id"):
                data["run_id"] = meta.get("run_id")
                
            # 2. Normalize source
            if not data.get("source") and meta.get("source"):
                data["source"] = meta.get("source")
                
            # 3. Normalize window
            if not data.get("window") and meta.get("window"):
                data["window"] = meta.get("window")
                
        return data

    @model_validator(mode='after')
    def validate_requirements(self) -> "PNCPBatch":
        if not self.items:
             # This will trigger 422 if items is missing or not a list (Pydantic handles type check above)
             # But if it's an empty list, is that an error? Requirements say "if items is not a list -> 422".
             # Users might send empty batch? Let's allow empty batch but type must be list.
             # Pydantic `items: List[dict]` enforces list type.
             pass
        
        # Check required envelope fields
        if not self.run_id or not self.source:
            raise ValueError("Missing required fields: run_id, source (in meta or top-level)")
        if self.window is None:
             raise ValueError("Missing required fields: window (in meta or top-level)")
             
        return self

# Read API Schemas

class PaginatedResponse(BaseModel):
    page: int
    page_size: int
    total: int
    items: List[dict]
    facets: Optional[dict] = None

class RunLog(BaseModel):
    run_id: str
    source: str
    window: dict
    status: str
    counts: dict
    created_at: str
    errors: Optional[List[dict]] = None

class PaginatedRuns(BaseModel):
    page: int
    page_size: int
    total: int
    runs: List[RunLog]

# Segmentation Pydantic Models
class TermCreate(BaseModel):
    term: str
    term_type: str # include, exclude, required
    group_id: Optional[str] = None

class SegmentCreate(BaseModel):
    slug: str
    name: str
    priority: int = 0
    match_mode: str = "ANY"

class SegmentUpdate(BaseModel):
    name: Optional[str] = None
    priority: Optional[int] = None
    match_mode: Optional[str] = None
    is_active: Optional[bool] = None



