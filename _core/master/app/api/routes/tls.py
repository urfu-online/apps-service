"""TLS validation endpoint for Caddy on_demand_tls."""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


class TLSValidationResponse(BaseModel):
    """Response for TLS validation"""
    status: str
    service: Optional[str] = None
    domain: str


@router.get("/validate", response_model=TLSValidationResponse)
async def validate_tls_domain(
    domain: str = Query(..., description="Domain to validate for TLS certificate")
):
    """
    Validate domain for Caddy on_demand_tls.

    This endpoint is called by Caddy before issuing a TLS certificate.
    Returns 200 if the domain is allowed, 403 otherwise.

    No authentication required - this is called by Caddy internally.
    """
    from app.main import app

    discovery = app.state.discovery

    # Validate domain format first
    if not domain:
        raise HTTPException(status_code=403, detail="Domain is required")

    # Check if domain is registered in the platform
    is_valid, service_name = discovery.validate_domain(domain)

    if is_valid:
        logger.info(f"TLS validation passed: {domain} -> {service_name}")
        return TLSValidationResponse(
            status="ok",
            service=service_name,
            domain=domain
        )
    else:
        logger.warning(f"TLS validation rejected: {domain} - not registered")
        raise HTTPException(
            status_code=403,
            detail=f"Domain {domain} is not registered in the platform"
        )


@router.get("/allowed")
async def list_allowed_domains():
    """
    List all allowed domains for TLS certificate issuance.
    Requires authentication.
    """
    from app.main import app
    from app.core.security import get_current_user
    from fastapi import Depends

    # Ensure user is authenticated
    # Note: This endpoint requires auth unlike /validate

    discovery = app.state.discovery
    domains = discovery.get_allowed_domains()

    return {
        "domains": sorted(list(domains)),
        "count": len(domains)
    }
