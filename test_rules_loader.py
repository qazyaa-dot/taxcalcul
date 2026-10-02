import copy

import pytest

from engine.rules_loader import RulesError, load_rules, validate_rules


def test_load_2026():
    assert load_rules(2026)["tax_year"] == 2026


def test_missing_year():
    with pytest.raises(RulesError):
        load_rules(1999)


def test_missing_key_detected():
    rules = copy.deepcopy(load_rules(2026))
    del rules["comprehensive_tax"]["credit_cap"]
    with pytest.raises(RulesError, match="credit_cap"):
        validate_rules(rules)


def test_last_bracket_must_be_open():
    rules = copy.deepcopy(load_rules(2026))
    rules["property_tax"]["standard_rates"]["brackets"][-1][0] = 999
    with pytest.raises(RulesError):
        validate_rules(rules)
