"""Request and response models for the API"""

from pydantic import BaseModel, Field
from typing import Optional


class ChatRequest(BaseModel):
    """
    Model to validate chat requests

    Attributes:
        query: Process query
    """
    query: str = Field(
        default='',
        min_length=1,
        max_length=1000,
        description="Query for processing"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "query": "Which leads have no activity in 30 days with open deals above €20k?"
            }
        }


class LogQueryRequest(BaseModel):
    """Request model per loggare una query"""
    query: str
    response: str
    domain: str  # SALES | FINANCE | GENERAL
    used_db: bool
    trace_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    response: str
    domain: str
    used_db: bool
    status: str
    query: str


class LogQueryResponse(BaseModel):
    """Response model"""
    trace_id: str
    cost_usd: float
    status: str = "logged"
