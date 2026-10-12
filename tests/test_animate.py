from PIL import Image

from divroom import animate
from divroom.control import SIZE


def _ok_frames(frames, n):
    assert isinstance(frames, list) and len(frames) == n
    for f in frames:
        assert isinstance(f, Image.Image)
        assert f.size == (SIZE, SIZE)
        assert f.mode == "RGB"


def test_rainbow_frame_count_and_shape():
    _ok_frames(animate.rainbow(frames=12), 12)


def test_rainbow_animates_between_frames():
    frames = animate.rainbow(frames=8)
    # a moving hue sweep: a given pixel is a different color one frame later
    assert frames[0].getpixel((0, 0)) != frames[1].getpixel((0, 0))


def test_plasma_frame_count_and_motion():
    frames = animate.plasma(frames=10)
    _ok_frames(frames, 10)
    assert frames[0].tobytes() != frames[5].tobytes()


def test_sweep_endpoints_present():
    frames = animate.sweep("#ff0000", "#0000ff", frames=6)
    _ok_frames(frames, 6)
    # the band moves, so the composite changes across frames
    assert frames[0].tobytes() != frames[3].tobytes()


def test_pulse_peaks_brighter_than_start():
    frames = animate.pulse("#ffffff", frames=10)
    _ok_frames(frames, 10)
    brightness = [sum(f.getpixel((32, 32))) for f in frames]
    assert max(brightness) > brightness[0]


def test_gradient_is_single_frame_with_endpoints():
    img = animate.gradient("#ff0000", "#0000ff", angle=0)
    assert isinstance(img, Image.Image) and img.size == (SIZE, SIZE)
    left = img.getpixel((0, 32))
    right = img.getpixel((SIZE - 1, 32))
    assert left[0] > left[2]      # near pure red on the left
    assert right[2] > right[0]    # near pure blue on the right


def test_build_dispatches_and_wraps_gradient_as_list():
    assert len(animate.build("rainbow", frames=5)) == 5
    g = animate.build("gradient", a="#ff0000", b="#0000ff")
    assert isinstance(g, list) and len(g) == 1


def test_build_rejects_unknown():
    import pytest
    with pytest.raises(KeyError):
        animate.build("nope")
