from datetime import date


class QuotaAlerter:
    """Menentukan kapan owner perlu diberi tahu bahwa kuota AI global hampir atau sudah habis.

    Satu peringatan per ambang (80% dan 100%) per hari. Hanya di memori: setelah bot restart,
    peringatan hari itu bisa terkirim sekali lagi.
    """

    THRESHOLDS = (100, 80)

    def __init__(self) -> None:
        self._sent: set[tuple[date, int]] = set()

    def next_alert(self, used: int, limit: int, today: date) -> int | None:
        """Kembalikan ambang (80 atau 100) yang baru tercapai dan belum diberitahukan, atau None."""
        if limit <= 0:
            return None
        self._sent = {key for key in self._sent if key[0] == today}  # buang catatan hari lama
        percent = used * 100 // limit
        for threshold in self.THRESHOLDS:
            if percent >= threshold:
                key = (today, threshold)
                if key in self._sent:
                    return None
                self._sent.add(key)
                return threshold
        return None
