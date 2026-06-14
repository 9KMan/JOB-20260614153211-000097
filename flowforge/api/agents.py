"""Agent (LLM) endpoints."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from flowforge.api.deps import get_current_user
from flowforge.api.schemas import AgentCreate, AgentOut, LLMCompleteRequest, LLMCompleteResponse
from flowforge.core.database import get_db
from flowforge.models.agent import Agent
from flowforge.models.user import User
from flowforge.services import audit, llm

router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("", response_model=AgentOut, status_code=status.HTTP_201_CREATED)
def create_agent(
    payload: AgentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Agent:
    agent = Agent(
        name=payload.name,
        description=payload.description,
        provider=payload.provider,
        model=payload.model,
        system_prompt=payload.system_prompt,
        temperature=payload.temperature,
        tools=payload.tools or {},
        owner_id=current_user.id,
    )
    db.add(agent)
    db.flush()
    audit.record(
        db,
        action="agent.create",
        actor_id=current_user.id,
        target_type="agent",
        target_id=agent.id,
        payload={"name": agent.name, "provider": agent.provider},
    )
    db.commit()
    db.refresh(agent)
    return agent


@router.get("", response_model=List[AgentOut])
def list_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Agent]:
    return (
        db.query(Agent)
        .filter(Agent.owner_id == current_user.id)
        .order_by(Agent.created_at.desc())
        .all()
    )


@router.get("/{agent_id}", response_model=AgentOut)
def get_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Agent:
    agent = db.get(Agent, agent_id)
    if not agent or agent.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="agent not found")
    return agent


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_agent(
    agent_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> None:
    agent = db.get(Agent, agent_id)
    if not agent or agent.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="agent not found")
    audit.record(
        db,
        action="agent.delete",
        actor_id=current_user.id,
        target_type="agent",
        target_id=agent.id,
    )
    db.delete(agent)
    db.commit()


@router.post("/complete", response_model=LLMCompleteResponse)
def llm_complete(
    payload: LLMCompleteRequest,
    current_user: User = Depends(get_current_user),
) -> LLMCompleteResponse:
    try:
        resp = llm.complete(
            payload.prompt,
            system=payload.system or "",
            temperature=payload.temperature,
            model=payload.model,
            provider=payload.provider,
        )
    except llm.LLMError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LLMCompleteResponse(
        text=resp.text,
        model=resp.model,
        provider=resp.provider,
        usage=resp.usage,
    )


@router.get("/_catalog/models")
def models_catalog() -> dict:
    """Expose the model catalog so the UI can show provider options."""
    return llm.list_models()
