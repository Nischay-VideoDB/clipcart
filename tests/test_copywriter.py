from clipcart.copywriter import write_copy


def test_copywriter_uses_product_fallback_without_a_model_client():
    result = write_copy(None, {"name": "Canvas Tote", "price": "SGD 18.90"}, "")

    assert result["hook"] == "Canvas Tote"
    assert result["caption"] == "Check out Canvas Tote for SGD 18.90."
