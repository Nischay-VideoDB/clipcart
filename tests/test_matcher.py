from types import SimpleNamespace

from clipcart import matcher


def test_product_window_is_clamped_to_real_video_duration(monkeypatch):
    video = SimpleNamespace(length=15.25)
    shot = SimpleNamespace(start=13.0, end=14.8)
    monkeypatch.setattr(matcher, "search_spoken", lambda _video, _query: [shot])

    window = matcher.find_product_window(
        video, {"name": "Canvas Tote Bag"}, min_len=12, max_len=40, lead=8,
    )

    assert window == (3.25, 15.25)
