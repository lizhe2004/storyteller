from storyteller.cli.interactive import (
    parse_choice,
    parse_yes_no,
    LENGTHS,
    COMPLEXITIES,
)


def test_parse_choice_digit():
    assert parse_choice("1", LENGTHS, 1) == "short"
    assert parse_choice("2", LENGTHS, 0) == "medium"
    assert parse_choice("3", LENGTHS, 0) == "long"


def test_parse_choice_default_on_empty():
    assert parse_choice("", LENGTHS, 1) == "medium"
    assert parse_choice("   ", COMPLEXITIES, 0) == "simple"


def test_parse_choice_out_of_range_returns_default():
    assert parse_choice("99", LENGTHS, 1) == "medium"
    assert parse_choice("0", LENGTHS, 2) == "long"


def test_parse_choice_literal_value():
    assert parse_choice("long", LENGTHS, 0) == "long"
    assert parse_choice("rich", COMPLEXITIES, 0) == "rich"


def test_parse_choice_garbage_returns_default():
    assert parse_choice("nonsense", LENGTHS, 1) == "medium"


def test_parse_yes_no_default():
    assert parse_yes_no("") is True
    assert parse_yes_no("y") is True
    assert parse_yes_no("Y") is True
    assert parse_yes_no("yes") is True
    assert parse_yes_no("n") is False
    assert parse_yes_no("no") is False


def test_parse_yes_no_garbage_returns_default():
    assert parse_yes_no("maybe", default=True) is True
    assert parse_yes_no("maybe", default=False) is False