import pytest
import respx
import httpx

from finacialsim_saas.services.cep_service import lookup_cep


@pytest.mark.asyncio
@respx.mock
async def test_cep_lookup_returns_brasilapi_response():
    respx.get("https://brasilapi.com.br/api/cep/v1/01310100").mock(
        return_value=httpx.Response(
            200,
            json={
                "cep": "01310100",
                "logradouro": "Av. Paulista",
                "complemento": "",
                "bairro": "Bela Vista",
                "localidade": "São Paulo",
                "uf": "SP",
            },
        )
    )
    result = await lookup_cep("01310-100")
    assert result["cep"] == "01310100"
    assert result["uf"] == "SP"


@pytest.mark.asyncio
@respx.mock
async def test_cep_lookup_fails_open_on_error():
    respx.get("https://brasilapi.com.br/api/cep/v1/99999999").mock(
        return_value=httpx.Response(404)
    )
    result = await lookup_cep("99999-999")
    assert result == {}


@pytest.mark.asyncio
async def test_cep_invalid_length_returns_empty():
    result = await lookup_cep("123")
    assert result == {}
