"""TC-18 (AC-11): splitting a body into passages for embedding."""

import random

import pytest
from newsdock_extractor.domain.passages import split_passages


def words(passages: list[str]) -> list[str]:
    return " ".join(passages).split()


def test_random_texts_always_obey_the_size_and_keep_every_word() -> None:
    """Seeded fuzz: odd mixes of paragraphs, sentences, long runs and blank lines."""
    rng = random.Random(7)
    atoms = [
        "word",
        "a",
        "Sentence.",
        "Why?",
        "x" * 40,
        "y" * 1300,
        "é" * 90,
        "\n",
        "  ",
    ]
    for _ in range(300):
        text = " ".join(rng.choice(atoms) for _ in range(rng.randint(0, 400)))
        passages = split_passages(text, target=500, hard_max=700)
        assert all(0 < len(p) <= 700 for p in passages), text[:80]
        assert all(p == p.strip() for p in passages)
        # long unbroken runs are cut, so compare the characters, not the words
        assert "".join(passages).replace("\n", "").replace(" ", "") == "".join(
            text.split()
        )


def test_a_short_text_is_one_passage() -> None:
    assert split_passages("Just one short paragraph.") == ["Just one short paragraph."]


def test_whitespace_and_empty_text_give_no_passages() -> None:
    assert split_passages("") == []
    assert split_passages("   \n \n\t\n") == []


def test_whole_paragraphs_are_packed_up_to_the_target() -> None:
    paragraphs = [f"{n}" + "x" * 299 for n in range(10)]  # 300 characters each
    passages = split_passages("\n".join(paragraphs), target=1000, hard_max=1200)
    # three paragraphs and two separators are 902 characters, a fourth would pass 1,000
    assert [p.count("\n") + 1 for p in passages] == [3, 3, 3, 1]
    assert words(passages) == words(paragraphs)


def test_every_passage_is_within_the_hard_maximum_and_covers_the_text() -> None:
    sentences = [
        f"Sentence number {n} says something quite ordinary." for n in range(400)
    ]
    text = "\n".join(
        " ".join(sentences[i : i + 7]) for i in range(0, len(sentences), 7)
    )
    passages = split_passages(text, target=1000, hard_max=1200)
    assert len(passages) > 5
    assert all(0 < len(p) <= 1200 for p in passages)
    assert words(passages) == text.split()


def test_one_huge_paragraph_is_split_at_sentence_ends() -> None:
    paragraph = " ".join(
        f"This is sentence {n} of a very long paragraph." for n in range(200)
    )
    passages = split_passages(paragraph, target=1000, hard_max=1200)
    assert len(passages) > 5
    assert all(len(p) <= 1200 for p in passages)
    assert all(p.endswith(".") for p in passages)
    assert words(passages) == paragraph.split()


def test_a_run_without_spaces_is_cut_hard_and_terminates() -> None:
    passages = split_passages("x" * 3000, target=1000, hard_max=1200)
    assert all(len(p) <= 1200 for p in passages)
    assert "".join(passages) == "x" * 3000


def test_a_long_paragraph_without_sentence_ends_is_split_at_spaces() -> None:
    paragraph = " ".join(["word"] * 1000)
    passages = split_passages(paragraph, target=1000, hard_max=1200)
    assert all(len(p) <= 1200 for p in passages)
    assert words(passages) == paragraph.split()
    assert all(not p.startswith(" ") and not p.endswith(" ") for p in passages)


def test_a_paragraph_of_exactly_the_hard_maximum_stays_whole() -> None:
    paragraph = "y" * 1200
    assert split_passages(paragraph, target=1000, hard_max=1200) == [paragraph]


def test_length_is_counted_in_characters_not_bytes() -> None:
    paragraph = "é" * 1100  # 2,200 bytes in UTF-8, 1,100 characters
    assert split_passages(paragraph, target=1000, hard_max=1200) == [paragraph]


def test_blank_lines_and_edge_spaces_are_dropped() -> None:
    assert split_passages("  one  \n\n\n  two\n") == ["one\ntwo"]


@pytest.mark.parametrize(("target", "hard_max"), [(0, 10), (100, 50), (-1, 5)])
def test_impossible_sizes_are_refused(target: int, hard_max: int) -> None:
    with pytest.raises(ValueError):
        split_passages("text", target=target, hard_max=hard_max)
