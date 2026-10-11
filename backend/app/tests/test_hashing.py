from backend.app.common.hashing import content_hash

# Pinned: P1 (cache) and P2 (SourceRef) must agree. If this changes, tell the other side.
EXPECTED = "b98781fdc9f83451a2fc937819581a4dcb105522785a9ca1f9e3c675e992d8d2"


def test_content_hash_pinned_and_whitespace_normalized():
    assert content_hash("Rent paid $1,450 to Westport") == EXPECTED
    assert content_hash("  Rent\tpaid\n\n$1,450   to Westport \r\n") == EXPECTED
    assert content_hash("Rent paid $1,451 to Westport") != EXPECTED
