from akizacore.core.exceptions import AkizaError, InsufficientFunds, QuotaExceeded


def test_default_message_and_status() -> None:
    err = InsufficientFunds()
    assert err.user_message == "Koin kamu tidak cukup."
    assert err.http_status == 400
    assert isinstance(err, AkizaError)


def test_custom_message() -> None:
    err = QuotaExceeded("Kuota AI harian habis")
    assert str(err) == "Kuota AI harian habis"
    assert err.http_status == 429
