import re

_ADDR_WORDS = {
    "street": "st", "avenue": "ave", "av": "ave", "road": "rd", "drive": "dr", "boulevard": "blvd",
    "lane": "ln", "court": "ct", "place": "pl", "terrace": "ter", "parkway": "pkwy", "highway": "hwy",
    "apartment": "unit", "apt": "unit", "suite": "unit", "ste": "unit",
}  # no N/North folding: "E St" and "East St" can be different streets


def address_key(s: str) -> str:
    """Comparable form: lowercase, no punctuation, St/Street and Apt/#/Unit folded together.

    Shared by the extractor's home match and rule R2; change both or neither.
    """
    s = re.sub(r"(?<=\w)-(?=\w)", "", s.lower())  # "Unit 4-B" == "Apt 4B"
    out: list[str] = []
    for t in re.findall(r"[^\W_]+", s.replace("#", " unit ")):
        t = _ADDR_WORDS.get(t, t)
        if not (t == "unit" and out and out[-1] == "unit"):  # "Apt #4B" -> one unit token
            out.append(t)
    return " ".join(out)
