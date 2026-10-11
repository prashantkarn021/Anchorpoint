import hashlib


def content_hash(text: str) -> str:
    """sha256 hex of UTF-8 text after collapsing whitespace runs and stripping.

    Shared by the agent extraction cache and the ledger's SourceRef.content_hash; change both or neither.
    """
    return hashlib.sha256(" ".join(text.split()).encode("utf-8")).hexdigest()
