"""Turn a persona's `bank:` section into Plaid custom-user transactions.

The result is the list PlaidConnector(transactions) plants in the sandbox. Amounts keep
Plaid's sign: positive is money out, negative is a deposit. Deterministic per seed day.
"""

import random
from datetime import date, timedelta

from backend.app.seed.persona import Persona

# Plaid's sandbox accepts a limited custom user; story transactions always fit, and
# everyday spending fills whatever room is left.
DEFAULT_LIMIT = 240

EVERYDAY_NAMES = {
    "groceries": "PEAKSIDE GROCER {city}",
    "coffee": "BLUE KETTLE COFFEE {city}",
    "pharmacy": "CORNERWELL PHARMACY {city}",
    "uniform_shop": "SCRUB AND STITCH UNIFORMS {city}",
    "p2p_transfer_friend": "P2P TRANSFER PRIYA N",
}
PER_YEAR = {"per_week": 52, "per_month": 12, "per_quarter": 4}
TAKE_HOME = 0.785  # share of the taxable wage that reaches the account


def _amount(spec: dict, rng: random.Random) -> float:
    if "amount" in spec:
        return float(spec["amount"])
    low, high = spec["amount_range"]
    return round(rng.uniform(low, high), 2)


def _recurring(persona: Persona) -> list[tuple[date, float, str]]:
    rows = []
    for spec in persona.spec["bank"]["recurring"]:
        rng = random.Random(f"{persona.profile['id']}-bank-{spec['name']}")
        for month in persona.months(spec["months"]):
            day = persona.resolve({"mo": month, "day": spec["day"]})
            rows.append((day, _amount(spec, rng), spec["name"]))
    return rows


def _deposits(persona: Persona) -> list[tuple[date, float, str]]:
    """Weekly stipend and biweekly payroll, each Friday Maya is on assignment."""
    stipend = next(d for d in persona.spec["bank"]["deposits"] if d["cadence"] == "weekly")
    payroll = next(d for d in persona.spec["bank"]["deposits"] if d["cadence"] == "biweekly")
    rows = []
    for week in range(-54, 1):
        friday = persona.resolve({"wk": week, "day": 4})
        assignment = persona.assignment_on(friday)
        if not assignment:
            continue
        pay = assignment["pay"]
        rows.append((friday, -float(sum(pay[field] for field in stipend["amount_from"])), stipend["name"]))
        if week % 2 == 0:
            net = round(2 * pay[payroll["amount_from"]] * TAKE_HOME, 2)
            rows.append((friday, -net, payroll["name"]))
    return rows


def _trips(persona: Persona) -> list[tuple[date, float, str]]:
    """Airline on the way out, then fuel and a ride while home. All inside the trip dates."""
    rows = []
    for depart, back in persona.trips():
        rng = random.Random(f"{persona.profile['id']}-bank-trip-{depart.isoformat()}")
        for offset, spec in enumerate(persona.spec["bank"]["per_trip"]):
            day = min(depart + timedelta(days=offset), back)
            rows.append((day, _amount(spec, rng), spec["name"]))
    return rows


def _city(persona: Persona, day: date) -> str:
    """Where everyday spending happens: home only during a trip home, else the work city."""
    if any(depart <= day <= back for depart, back in persona.trips()):
        return persona.profile["home_metro"]["name"]
    assignment = persona.assignment_on(day)
    if assignment:
        return assignment["metro"]["name"]
    for gap in persona.spec["gaps"]:
        if persona.end(gap["after"]) <= day <= persona.start(gap["before"]):
            # A gap with no trip home must not show spending at home.
            return gap.get("everyday_city") or persona.assignments[gap["before"]]["metro"]["name"]
    return persona.spec["assignments"][0]["metro"]["name"]


def _everyday(persona: Persona, room: int) -> list[tuple[date, float, str]]:
    if room <= 0:
        return []
    rng = random.Random(f"{persona.profile['id']}-bank-everyday")
    first = persona.resolve({"mo": -12, "day": 1})
    span = (persona.today - first).days
    specs = persona.spec["bank"]["everyday"]
    weights = [next(spec[unit] * yearly for unit, yearly in PER_YEAR.items() if unit in spec) for spec in specs]
    rows = []
    for spec in rng.choices(specs, weights=weights, k=room):
        day = first + timedelta(days=rng.randrange(0, span + 1))
        name = EVERYDAY_NAMES[spec["kind"]].format(city=_city(persona, day).upper())
        rows.append((day, _amount(spec, rng), name))
    return rows


def bank_transactions(persona: Persona, limit: int = DEFAULT_LIMIT) -> list[dict]:
    """Plaid custom-user transactions for the persona, oldest first, none after the seed day."""
    story = _recurring(persona) + _deposits(persona) + _trips(persona)
    first = persona.resolve({"mo": -12, "day": 1})
    story = [row for row in story if first <= row[0] <= persona.today]
    rows = sorted(story + _everyday(persona, limit - len(story)), key=lambda row: (row[0], row[2]))
    return [
        {
            "date_transacted": day.isoformat(),
            "date_posted": day.isoformat(),
            "amount": amount,
            "description": name,
            "currency": "USD",
        }
        for day, amount, name in rows
    ]
