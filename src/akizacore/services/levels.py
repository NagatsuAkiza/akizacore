import math


def xp_for_level(level: int) -> int:
    """Total XP minimum untuk mencapai level tertentu: 100 * (level - 1)^2."""
    return 100 * (level - 1) ** 2


def level_for_xp(xp: int) -> int:
    return math.isqrt(max(xp, 0) // 100) + 1


def level_progress(xp: int) -> tuple[int, int, int]:
    """Return (level, xp_di_level_ini, xp_dibutuhkan_untuk_level_berikutnya)."""
    level = level_for_xp(xp)
    base = xp_for_level(level)
    return level, xp - base, xp_for_level(level + 1) - base
