# api/schemas.py
from typing import List, Dict
from pydantic import BaseModel, Field, validator

class PredictRequest(BaseModel):
    features: List[float] = Field(..., example=[0.0]*45)

    @validator("features")
    def check_features_length(cls, v):
        if not isinstance(v, list):
            raise ValueError("features must be a list of floats")
        return v

class BatchPredictRequest(BaseModel):
    instances: List[List[float]] = Field(..., min_items=1, example=[[0.0]*45])

    @validator("instances")
    def check_instances_not_empty(cls, v):
        if not v:
            raise ValueError("instances list cannot be empty")
        return v

class PredictionResult(BaseModel):
    label: str
    confidence: float
    probabilities: Dict[str, float]

class PredictResponse(BaseModel):
    result: PredictionResult
    request_id: str

class BatchPredictResponse(BaseModel):
    results: List[PredictionResult]
    request_id: str

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    uptime_seconds: int

class ModelInfoResponse(BaseModel):
    features: List[str]
    classes: List[str]
    feature_count: int