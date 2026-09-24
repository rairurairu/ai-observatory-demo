from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

class ExtractedObservation(BaseModel):
    brand_id:str
    mention_order:int=Field(ge=1)
    explicit_rank:int|None=Field(default=None,ge=1)
    product:str|None=None
    sentiment:Literal["positive","negative","neutral","unknown"]="unknown"
    attributes:list[str]=Field(default_factory=list)
    evidence:str
    entity_type:Literal["brand","product","ambiguous","unknown"]="brand"

class StandardizedResponse(BaseModel):
    provider:str
    model_id:str
    prompt_id:str
    experiment_id:str
    run_id:str
    response_id:str
    timestamp:datetime
    response_text:str
    token_usage:dict=Field(default_factory=dict)
    latency_ms:float|None=None
    execution_status:Literal["success","failed","excluded"]
    error_message:str|None=None
    data_source:Literal["demo","live"]
    model_configuration:dict=Field(default_factory=dict)
    search_enabled:bool=False
    search_metadata:dict|None=None
