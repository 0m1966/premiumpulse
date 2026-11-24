"""FastAPI REST application for PremiumPulse.

Exposes rating, quoting, what-if simulations, and guarded AI explainer endpoints.
Protected by X-API-Key authentication and SlowAPI rate limiting.
"""

import secrets
from typing import Any
from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from premiumpulse.ai.chains import AIExplanationService
from premiumpulse.config.settings import get_settings
from premiumpulse.db.client_factory import get_current_mode
from premiumpulse.domain.models import (
    DriverProfile,
    DriverQuote,
    DriverRiskScore,
    PortfolioSummary,
    QuoteSimulationRequest,
    QuoteSimulationResponse,
)
from premiumpulse.services.pricing_service import PricingService

# Rate limiter setup
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(
    title="PremiumPulse REST API",
    description="Telematics Underwriting and Dynamic Pricing Engine API",
    version="1.0.0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    """Validate X-API-Key header using constant-time string comparison."""
    settings = get_settings()
    expected_key = settings.PREMIUMPULSE_API_KEY

    if not api_key or not secrets.compare_digest(api_key, expected_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-API-Key header.",
        )
    return api_key


def get_service() -> PricingService:
    """Dependency provider for PricingService."""
    return PricingService()


def get_ai_service() -> AIExplanationService:
    """Dependency provider for AIExplanationService."""
    return AIExplanationService()


class QuestionRequest(BaseModel):
    """User question request body for guidelines Q&A."""
    question: str = Field(min_length=1, max_length=300, description="Underwriting guideline query")


# --- Endpoints ---

@app.get("/health", tags=["System"])
def health_check() -> dict[str, Any]:
    """Health status and current database operating mode (no auth required)."""
    settings = get_settings()
    return {
        "status": "healthy",
        "app_name": "PremiumPulse",
        "mode": get_current_mode(),
        "prompt_version": settings.PROMPT_VERSION,
        "scorecard_version": "v1",
    }


@app.get("/drivers", tags=["Underwriting"], dependencies=[Depends(verify_api_key)])
@limiter.limit("60/minute")
def list_drivers(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    service: PricingService = Depends(get_service),
) -> list[dict[str, Any]]:
    """List drivers with current pricing overview (paginated)."""
    if limit > 100 or limit < 1:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100.")
    if offset < 0:
        raise HTTPException(status_code=422, detail="Offset cannot be negative.")
    return service.list_drivers(limit=limit, offset=offset)


@app.get("/drivers/{driver_id}/score", tags=["Underwriting"], dependencies=[Depends(verify_api_key)])
@limiter.limit("60/minute")
def get_driver_score(
    driver_id: str,
    request: Request,
    service: PricingService = Depends(get_service),
) -> DriverRiskScore:
    """Fetch 30-day telematics scorecard evaluation for driver."""
    score = service.get_driver_score(driver_id.upper())
    if not score:
        raise HTTPException(status_code=404, detail=f"Score record for driver '{driver_id}' not found.")
    return score


@app.get("/drivers/{driver_id}/quote", tags=["Underwriting"], dependencies=[Depends(verify_api_key)])
@limiter.limit("60/minute")
def get_driver_quote(
    driver_id: str,
    request: Request,
    service: PricingService = Depends(get_service),
) -> DriverQuote:
    """Fetch official issued quote and full rating factor breakdown."""
    quote = service.get_driver_quote(driver_id.upper())
    if not quote:
        raise HTTPException(status_code=404, detail=f"Quote record for driver '{driver_id}' not found.")
    return quote


@app.post("/quote/simulate", tags=["Simulator"], dependencies=[Depends(verify_api_key)])
@limiter.limit("30/minute")
def simulate_quote(
    request: Request,
    body: QuoteSimulationRequest,
    service: PricingService = Depends(get_service),
) -> QuoteSimulationResponse:
    """Run deterministic what-if pricing simulation."""
    try:
        return service.simulate_quote(body)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@app.post("/drivers/{driver_id}/explain", tags=["AI Narration"], dependencies=[Depends(verify_api_key)])
@limiter.limit("15/minute")
def explain_driver_quote(
    driver_id: str,
    request: Request,
    service: PricingService = Depends(get_service),
    ai_service: AIExplanationService = Depends(get_ai_service),
) -> dict[str, Any]:
    """Generate verified, grounded AI explanation of driver quote."""
    quote = service.get_driver_quote(driver_id.upper())
    if not quote:
        raise HTTPException(status_code=404, detail=f"Driver '{driver_id}' quote not found.")
    score = service.get_driver_score(driver_id.upper())
    return ai_service.explain_quote(quote, score)


@app.post("/guidelines/ask", tags=["AI Narration"], dependencies=[Depends(verify_api_key)])
@limiter.limit("15/minute")
def ask_guidelines(
    request: Request,
    body: QuestionRequest,
    ai_service: AIExplanationService = Depends(get_ai_service),
) -> dict[str, Any]:
    """Query underwriting guidelines with grounded RAG retriever."""
    return ai_service.ask_guidelines(body.question)


@app.get("/portfolio/summary", tags=["Underwriting"], dependencies=[Depends(verify_api_key)])
@limiter.limit("60/minute")
def get_portfolio_summary(
    request: Request,
    service: PricingService = Depends(get_service),
) -> PortfolioSummary:
    """Aggregate portfolio metrics for underwriter dashboards."""
    return service.get_portfolio_summary()
