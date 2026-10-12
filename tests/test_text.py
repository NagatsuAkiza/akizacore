from akizacore.utils.text import chunk_text


def test_short_text_is_single_chunk() -> None:
    assert chunk_text("halo") == ["halo"]


def test_empty_text_has_no_chunks() -> None:
    assert chunk_text("   ") == []


def test_long_text_is_split_within_limit_without_losing_words() -> None:
    text = " ".join(f"kata{i}" for i in range(1000))
    chunks = chunk_text(text, limit=200)
    assert all(len(c) <= 200 for c in chunks)
    assert " ".join(chunks).split() == text.split()


def test_text_without_spaces_is_hard_split() -> None:
    chunks = chunk_text("x" * 450, limit=200)
    assert [len(c) for c in chunks] == [200, 200, 50]
