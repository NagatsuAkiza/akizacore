import asyncio

import pytest
from pydantic import BaseModel, Field

from akizacore.ai.router import match_rule
from akizacore.ai.tools import Tool, ToolContext, ToolExecutor, ToolRegistry
from akizacore.schemas.discord import UserInfo

USER = UserInfo(id=1, username="u")


class NoArgs(BaseModel):
    pass


class NumArgs(BaseModel):
    n: int = Field(1, ge=1, le=5, description="angka")


def ctx(*, is_admin: bool = False, economy: bool = True) -> ToolContext:
    return ToolContext(server_id=1, user=USER, is_admin=is_admin, features={"economy": economy})


def make_registry(calls: list[str]) -> ToolRegistry:
    async def read(c: ToolContext, a: NumArgs) -> str:
        calls.append("read")
        return f"n={a.n}"

    async def admin(c: ToolContext, a: NoArgs) -> str:
        calls.append("admin")
        return "rahasia"

    async def danger(c: ToolContext, a: NoArgs) -> str:
        calls.append("danger")
        return "boom"

    async def slow(c: ToolContext, a: NoArgs) -> str:
        await asyncio.sleep(1)
        return "terlambat"

    async def failing(c: ToolContext, a: NoArgs) -> str:
        raise RuntimeError("rusak")

    async def verbose(c: ToolContext, a: NoArgs) -> str:
        return "x" * 5000

    return ToolRegistry(
        [
            Tool("read_n", "baca angka", NumArgs, read, feature="economy"),
            Tool("admin_only", "khusus admin", NoArgs, admin, permission="admin"),
            Tool("danger", "aksi berbahaya", NoArgs, danger, side_effect="destructive"),
            Tool("slow", "lambat", NoArgs, slow, timeout_s=0.05),
            Tool("failing", "selalu gagal", NoArgs, failing),
            Tool("verbose", "keluaran panjang", NoArgs, verbose),
        ]
    )


def offered(registry: ToolRegistry, c: ToolContext) -> set[str]:
    return {spec.name for spec in registry.specs_for(c)}


def test_specs_only_offer_allowed_read_tools() -> None:
    registry = make_registry([])
    assert offered(registry, ctx()) == {"read_n", "slow", "failing", "verbose"}
    assert "admin_only" in offered(registry, ctx(is_admin=True))
    assert "read_n" not in offered(registry, ctx(economy=False))
    assert "danger" not in offered(
        registry, ctx(is_admin=True)
    )  # destruktif tidak pernah ditawarkan


def test_schema_is_clean_and_argless_tools_have_no_parameters() -> None:
    registry = make_registry([])
    specs = {s.name: s for s in registry.specs_for(ctx())}
    params = specs["read_n"].parameters
    assert params is not None
    assert params["properties"]["n"]["maximum"] == 5  # type: ignore[index]
    assert "title" not in str(params)
    assert "default" not in str(params)
    assert specs["slow"].parameters is None


def test_duplicate_tool_name_is_rejected() -> None:
    registry = make_registry([])
    with pytest.raises(ValueError):
        registry.register(Tool("slow", "dup", NoArgs, lambda c, a: asyncio.sleep(0, "x")))


async def test_executor_happy_path_and_validation() -> None:
    executor = ToolExecutor(make_registry([]))
    assert await executor.run_named("read_n", '{"n": 3}', ctx()) == "n=3"
    assert await executor.run_named("read_n", "", ctx()) == "n=1"  # default dipakai
    assert (await executor.run_named("read_n", '{"n": 99}', ctx())).startswith(
        "Error: argumen tidak valid"
    )
    assert (await executor.run_named("read_n", "{bukan json", ctx())).startswith(
        "Error: argumen tidak valid"
    )


async def test_executor_blocks_unknown_denied_and_destructive_tools() -> None:
    calls: list[str] = []
    executor = ToolExecutor(make_registry(calls))

    assert "tidak dikenal" in await executor.run_named("hack", "{}", ctx())
    assert (await executor.run_named("admin_only", "{}", ctx())).startswith("Ditolak")
    assert (await executor.run_named("read_n", "{}", ctx(economy=False))).startswith("Ditolak")
    assert (await executor.run_named("danger", "{}", ctx(is_admin=True))).startswith("Ditahan")
    assert calls == []  # tidak ada handler yang sempat jalan

    assert await executor.run_named("admin_only", "{}", ctx(is_admin=True)) == "rahasia"


async def test_executor_handles_timeout_failure_and_long_output() -> None:
    executor = ToolExecutor(make_registry([]))
    assert "timeout" in await executor.run_named("slow", "{}", ctx())
    assert "gagal" in await executor.run_named("failing", "{}", ctx())
    assert len(await executor.run_named("verbose", "{}", ctx())) <= 1500


@pytest.mark.parametrize(
    "text",
    [
        "saldo",
        "Saldo saya?",
        "berapa koin aku",
        "berapa saldoku?",
        "cek saldo",
        "saldo saya berapa",
        "my balance",
        "how much coins do I have",
    ],
)
def test_router_matches_balance(text: str) -> None:
    match = match_rule(text)
    assert match is not None and match.tool == "get_balance"


@pytest.mark.parametrize(
    ("text", "by"),
    [
        ("leaderboard", "balance"),
        ("Peringkat koin", "balance"),
        ("siapa paling kaya?", "balance"),
        ("ranking xp", "xp"),
        ("top level", "xp"),
    ],
)
def test_router_matches_leaderboard(text: str, by: str) -> None:
    match = match_rule(text)
    assert match is not None
    assert (match.tool, match.args) == ("get_leaderboard", {"by": by})


@pytest.mark.parametrize(
    "text",
    [
        "jelaskan konsep koin kripto",
        "bagaimana cara menghitung saldo akhir tahun",
        "halo",
        "tolong ceritakan tentang peringkat FIFA",
        "",
        "   ",
    ],
)
def test_router_does_not_hijack_normal_questions(text: str) -> None:
    assert match_rule(text) is None
