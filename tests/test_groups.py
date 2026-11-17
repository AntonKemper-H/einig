"""Rule tests for A9 – F16 Fixed groups (specs/a9-groups.md). No Flask, no database."""

from app.services import groups as group_rules

NAME_EMPTY = "Please enter a group name."
NAME_TOO_LONG = "The group name can be at most 60 characters."
NICKNAME_EMPTY = "Please enter a nickname."
NICKNAME_TOO_LONG = "The nickname can be at most 30 characters."
NICKNAME_TAKEN = "This nickname is already taken in this group."


def test_validate_new_group_accepts_and_trims():
    values, errors = group_rules.validate_new_group("  Friday friends ", "  Anna ")
    assert errors == []
    assert values == {"name": "Friday friends", "nickname": "Anna"}


def test_validate_new_group_accepts_the_longest_values():
    values, errors = group_rules.validate_new_group("n" * 60, "a" * 30)
    assert errors == []
    assert values == {"name": "n" * 60, "nickname": "a" * 30}


def test_validate_new_group_rejects_empty_and_whitespace():
    for name, nickname in [("", ""), ("   ", "\t\n"), (None, None)]:
        _, errors = group_rules.validate_new_group(name, nickname)
        assert errors == [NAME_EMPTY, NICKNAME_EMPTY]


def test_validate_new_group_rejects_too_long_values():
    _, errors = group_rules.validate_new_group("n" * 61, "a" * 31)
    assert errors == [NAME_TOO_LONG, NICKNAME_TOO_LONG]


def test_join_group_errors_rejects_a_taken_nickname_in_any_case():
    assert group_rules.join_group_errors("anna", ["Anna", "Ben"]) == [NICKNAME_TAKEN]
    assert group_rules.join_group_errors("ÄRGER", ["ärger"]) == [NICKNAME_TAKEN]
    assert group_rules.join_group_errors("Cara", ["Anna", "Ben"]) == []


def test_join_group_errors_rejects_invalid_nicknames():
    assert group_rules.join_group_errors("", ["Anna"]) == [NICKNAME_EMPTY]
    assert group_rules.join_group_errors("a" * 31, []) == [NICKNAME_TOO_LONG]


def test_remember_group_token_adds_or_replaces_without_changing_the_input():
    tokens = {"g1": "t1"}
    added = group_rules.remember_group_token(tokens, "g2", "t2")
    replaced = group_rules.remember_group_token(added, "g1", "t-new")
    assert added == {"g1": "t1", "g2": "t2"}
    assert replaced == {"g1": "t-new", "g2": "t2"}
    assert tokens == {"g1": "t1"}


def test_groups_to_keep_keeps_the_10_most_recently_joined():
    assert group_rules.MAX_REMEMBERED_GROUPS == 10
    # member_id grows with every join, so a higher id was remembered later (same idea as A8).
    groups = [{"id": f"g{number}", "member_id": 50 + number} for number in range(13)]
    groups.reverse()
    assert group_rules.groups_to_keep(groups) == {f"g{number}" for number in range(3, 13)}
    assert len(groups) == 13


def test_groups_to_keep_with_10_or_fewer_keeps_all():
    groups = [{"id": f"g{number}", "member_id": number} for number in range(10)]
    assert group_rules.groups_to_keep(groups) == {f"g{number}" for number in range(10)}
    assert group_rules.groups_to_keep([]) == set()
