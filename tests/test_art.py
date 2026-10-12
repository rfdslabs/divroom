from PIL import Image

from divroom import art
from divroom.control import SIZE


def test_piece_url_encodes_hash_and_view():
    u = art.piece_url("fire-46", "#46_FIRE.ANS")
    assert u == "https://16colo.rs/pack/fire-46/x1/%2346_FIRE.ANS.png"
    assert art.piece_url("p", "A.ANS", view="x2").endswith("/x2/A.ANS.png")


def _tall(w=SIZE, h=256, band_y=200):
    img = Image.new("RGB", (w, h), (0, 0, 0))
    for x in range(w):
        for y in range(band_y, min(h, band_y + 8)):
            img.putpixel((x, y), (255, 255, 255))
    return img


def test_pan_frames_count_and_shape():
    frames = art.pan_frames(_tall(), frames=20)
    assert len(frames) == 20
    for f in frames:
        assert f.size == (SIZE, SIZE) and f.mode == "RGB"


def test_pan_moves_down_the_piece():
    frames = art.pan_frames(_tall(), frames=20)
    # the window travels, so the midpoint frame differs from the top frame
    assert frames[0].tobytes() != frames[len(frames) // 2].tobytes()


def test_pan_is_seamless_loop():
    frames = art.pan_frames(_tall(), frames=21)
    assert frames[0].tobytes() == frames[-1].tobytes()


def test_pan_small_image_is_padded_to_window():
    frames = art.pan_frames(Image.new("RGB", (10, 10), (255, 0, 0)), frames=5)
    assert len(frames) == 5
    for f in frames:
        assert f.size == (SIZE, SIZE)
    # a smaller-than-window image has no travel: every frame is identical
    assert frames[0].tobytes() == frames[-1].tobytes()


PACK_HTML = ('<a href="/pack/advent24/">x</a> <a href="/pack/fire-39/">y</a> '
             '<a href="/pack/advent24/">dup</a> <a href="/other/">no</a>')

PIECE_HTML = """
<a href="/pack/fire-46/%2346_FIRE.ANS">hash</a>
<a href="/pack/fire-46/AK-KING.ANS">ak</a>
<a href="/pack/fire-46/x1/AK-KING.ANS.png">render</a>
<a href="/pack/fire-46/tn/AK-KING.ANS.png">thumb</a>
<a href="/pack/fire-46/FILE_ID.DIZ">diz</a>
<a href="/pack/fire-46/0797SHIT.NFO">nfo</a>
"""


def test_pack_names_parses_and_dedups():
    assert art._pack_names(PACK_HTML) == ["advent24", "fire-39"]


def test_piece_files_keeps_ans_decoded_excludes_renders():
    files = art._piece_files(PIECE_HTML, "fire-46")
    assert "AK-KING.ANS" in files
    assert "#46_FIRE.ANS" in files                       # %23 decoded
    assert all(f.lower().endswith(".ans") for f in files)
    assert not any(".png" in f.lower() or "/" in f for f in files)


def test_random_piece_deterministic_with_seed(monkeypatch):
    import random
    monkeypatch.setattr(art, "list_packs", lambda year, timeout=15: ["p1", "p2", "p3"])
    monkeypatch.setattr(art, "list_pieces", lambda pack, timeout=15: [f"{pack}-a.ANS", f"{pack}-b.ANS"])
    a = art.random_piece(2024, rng=random.Random(42))
    b = art.random_piece(2024, rng=random.Random(42))
    assert a == b and a[0] in {"p1", "p2", "p3"} and a[1].lower().endswith(".ans")


def test_random_piece_skips_empty_packs(monkeypatch):
    import random
    monkeypatch.setattr(art, "list_packs", lambda year, timeout=15: ["empty", "good"])
    monkeypatch.setattr(art, "list_pieces",
                        lambda pack, timeout=15: [] if pack == "empty" else ["good-x.ANS"])
    assert art.random_piece(2024, rng=random.Random(0)) == ("good", "good-x.ANS")


def test_build_fetches_then_pans(monkeypatch):
    monkeypatch.setattr(art, "fetch_piece", lambda pack, file, view="x1", timeout=15: _tall())
    frames = art.build("fire-46", "AK-KING.ANS", frames=8)
    assert len(frames) == 8 and frames[0].size == (SIZE, SIZE)
