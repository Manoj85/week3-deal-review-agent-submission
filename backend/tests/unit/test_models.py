"""Missing evidence must never become an assumed numeric value."""

import pytest

from backend.app.models.review import Fact


@pytest.mark.parametrize("fact", [Fact(), Fact(state="CONFLICT"), Fact(state="KNOWN")])
def test_require_value_rejects_missing_conflicting_and_invalid_known_facts(fact):
    with pytest.raises(ValueError, match="non-null"):
        fact.require_value()
