from fastapi import APIRouter

from finacialsim_saas.services.cep_service import lookup_cep

router = APIRouter(prefix="/api/v1/cep", tags=["cep"])


@router.get("/{cep}")
async def get_cep(cep: str) -> dict:
    return await lookup_cep(cep)
