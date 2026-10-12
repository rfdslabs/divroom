import time

from divroom import slideshow


def _picker():
    seq = iter([(f"p{i}", f"f{i}.ANS") for i in range(1000)])
    return lambda year: next(seq)


def test_buffer_fills_to_target_then_stops():
    b = slideshow.ArtBuffer(1994, target=3, picker=_picker(),
                            builder=lambda p, f, frames=60: [p])
    did = 0
    while b.fill_once():
        did += 1
    assert did == 3 and len(b) == 3
    assert b.fill_once() is False  # full: no more work


def test_buffer_pop_is_fifo_and_refills():
    b = slideshow.ArtBuffer(1994, target=2, picker=_picker(),
                            builder=lambda p, f, frames=60: [p])
    while b.fill_once():
        pass
    first = b.pop()
    assert first["pack"] == "p0" and first["frames"] == ["p0"]
    assert len(b) == 1
    assert b.fill_once() is True   # room again after pop


def test_buffer_pop_empty_returns_none():
    b = slideshow.ArtBuffer(1994, target=2, picker=_picker(), builder=lambda p, f, frames=60: [p])
    assert b.pop() is None


def test_slideshow_plays_from_buffer_and_advances():
    played = []
    s = slideshow.Slideshow(
        ip="x", year=1994, hold=0.05, target=4,
        picker=_picker(), builder=lambda p, f, frames=60: [p],
        player=lambda frames: played.append(frames))
    s.start()
    deadline = time.time() + 5
    while len(played) < 2 and time.time() < deadline:
        time.sleep(0.02)
    st = s.status()
    s.stop()
    assert len(played) >= 2            # switched at least twice, no manual pushing
    assert st["running"] is True
    assert st["current"] is not None
    assert s.status()["running"] is False


def test_slideshow_records_player_error():
    def boom(frames):
        raise RuntimeError("device down")
    s = slideshow.Slideshow(ip="x", year=1994, hold=0.05, target=2,
                            picker=_picker(), builder=lambda p, f, frames=60: [p], player=boom)
    s.start()
    deadline = time.time() + 5
    while s.status()["error"] is None and time.time() < deadline:
        time.sleep(0.02)
    err = s.status()["error"]
    s.stop()
    assert err and "device down" in err
