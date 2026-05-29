from finacialsim_saas.errors import (
    AppError,
    AuthError,
    ConflictError,
    ExternalProviderError,
    NotFoundError,
    TenantAccessError,
    ValidationError,
)


def test_not_found_code_and_status():
    err = NotFoundError("simulation not found")
    assert err.code == "not_found"
    assert err.status_code == 404
    assert err.message == "simulation not found"
    assert err.details is None


def test_external_provider_degraded_flag():
    err = ExternalProviderError("FIPE unreachable", degraded=True)
    assert err.degraded is True
    assert err.status_code == 502


def test_all_six_errors_are_app_errors():
    for cls in [
        ValidationError,
        NotFoundError,
        ConflictError,
        AuthError,
        TenantAccessError,
        ExternalProviderError,
    ]:
        assert issubclass(cls, AppError), f"{cls.__name__} must extend AppError"
