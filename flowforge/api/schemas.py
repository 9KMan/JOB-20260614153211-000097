"""Pydantic schemas shared across the API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# ---------- Auth ----------


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    full_name: Optional[str] = None
    role: Optional[str] = "member"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: Optional[str]
    role: str
    is_active: bool
    created_at: datetime


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


# ---------- Workflows ----------


class StepDefinition(BaseModel):
    id: str
    name: str
    type: str
    config: Dict[str, Any] = Field(default_factory=dict)


class WorkflowDefinition(BaseModel):
    steps: List[StepDefinition] = Field(default_factory=list)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    trigger: str = "manual"
    schedule: Optional[str] = None
    definition: WorkflowDefinition = Field(default_factory=WorkflowDefinition)


class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    trigger: Optional[str] = None
    schedule: Optional[str] = None
    is_active: Optional[bool] = None
    definition: Optional[WorkflowDefinition] = None


class WorkflowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    trigger: str
    schedule: Optional[str]
    is_active: bool
    definition: Dict[str, Any]
    owner_id: str
    created_at: datetime
    updated_at: datetime


# ---------- Runs ----------


class RunTriggerRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)


class StepRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    position: int
    step_id: str
    name: str
    type: str
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    output: Optional[Dict[str, Any]]
    error: Optional[str]


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    workflow_id: str
    status: str
    trigger: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    duration_ms: Optional[int]
    error: Optional[str]
    outputs: Dict[str, Any]
    context: Dict[str, Any]
    created_at: datetime
    step_runs: List[StepRunOut] = Field(default_factory=list)


# ---------- Integrations ----------


class IntegrationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str
    config: Dict[str, Any] = Field(default_factory=dict)
    secret: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True


class IntegrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    kind: str
    config: Dict[str, Any]
    is_active: bool
    owner_id: str
    created_at: datetime
    updated_at: datetime


# ---------- Agents ----------


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    provider: str = "stub"
    model: str = "stub-1"
    system_prompt: Optional[str] = None
    temperature: float = 0.2
    tools: Dict[str, Any] = Field(default_factory=dict)


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    description: Optional[str]
    provider: str
    model: str
    system_prompt: Optional[str]
    temperature: float
    tools: Dict[str, Any]
    owner_id: str
    created_at: datetime
    updated_at: datetime


# ---------- ETL ----------


class ETLDryRunRequest(BaseModel):
    source: Dict[str, Any]
    transform: Optional[Dict[str, Any]] = None
    limit: int = 5


class ETLResultOut(BaseModel):
    total: int
    succeeded: int
    failed: int
    errors: List[Dict[str, Any]]
    started_at: str
    finished_at: Optional[str]
    duration_ms: int


# ---------- LLM ----------


class LLMCompleteRequest(BaseModel):
    prompt: str
    system: Optional[str] = None
    temperature: float = 0.2
    model: Optional[str] = None
    provider: Optional[str] = None


class LLMCompleteResponse(BaseModel):
    text: str
    model: str
    provider: str
    usage: Dict[str, int]


# ---------- Audit ----------


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    actor_id: Optional[str]
    action: str
    target_type: Optional[str]
    target_id: Optional[str]
    payload: Dict[str, Any]
    created_at: datetime
