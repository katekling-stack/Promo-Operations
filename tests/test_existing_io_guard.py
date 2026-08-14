"""'Add to existing IO' must be a numeric FreeWheel IO ID. A name there (e.g. a show title
pasted into the field, or carried across a market duplication) would reach FreeWheel as
insertion_order_id and fail with a cryptic "fail to convert <title> to Int". The builder
rejects it up front with an actionable message; a real numeric id (or blank) is fine."""

from __future__ import annotations

import pytest

from promo_ops.order_builder import OrderBuilder
from promo_ops.plan_loader import support_plan_from_dict


def _build(existing_io_id):
    return OrderBuilder().build(support_plan_from_dict(dict(
        promoted_title="Caught In The Act: Unfaithful", region="UK",
        campaign={"name": "Paramount + - UK"}, durations=[30],
        existing_io_id=existing_io_id)))


def test_title_as_existing_io_id_raises():
    with pytest.raises(ValueError, match="numeric FreeWheel IO ID"):
        _build("Caught In The Act: Unfaithful")


def test_numeric_existing_io_id_ok():
    order = _build("93584432")
    assert order.existing_io_id == "93584432"


def test_blank_existing_io_id_ok():
    order = _build(None)
    assert not order.existing_io_id
