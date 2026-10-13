class AkizaError(Exception):
    """Basis semua error domain. Dipetakan ke pesan Discord dan kode HTTP."""

    user_message = "Terjadi kesalahan."
    http_status = 500

    def __init__(self, message: str | None = None) -> None:
        self.user_message = message or type(self).user_message
        super().__init__(self.user_message)


class ProviderUnavailable(AkizaError):
    """Provider AI gagal / tidak tersedia. `detail` hanya untuk log, bukan untuk user."""

    user_message = "AI sedang tidak tersedia, coba lagi nanti."
    http_status = 503

    def __init__(self, detail: str | None = None, *, retryable: bool = True) -> None:
        super().__init__()
        self.detail = detail
        self.retryable = retryable


class NotFound(AkizaError):
    user_message = "Data tidak ditemukan."
    http_status = 404


class ValidationFailed(AkizaError):
    user_message = "Input tidak valid."
    http_status = 400


class PermissionDenied(AkizaError):
    user_message = "Kamu tidak punya izin untuk ini."
    http_status = 403


class InsufficientFunds(AkizaError):
    user_message = "Koin kamu tidak cukup."
    http_status = 400


class QuotaExceeded(AkizaError):
    user_message = "Kuota habis, coba lagi nanti."
    http_status = 429


class Unauthorized(AkizaError):
    user_message = "Kamu belum login."
    http_status = 401
