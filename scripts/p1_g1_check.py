"""Gate G1: Strands agent gets a completion (plain + structured) from Akamai inference.

Run from repo root: .venv\\Scripts\\python scripts\\p1_g1_check.py
"""

import sys
from datetime import date
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # repo root, team convention
from strands import Agent

from backend.app.agents.llm import make_model


class Payment(BaseModel):
    payee: str
    amount: float
    date: date


def check(name: str, fn) -> bool:
    try:
        ok, detail = fn()
    except Exception as e:  # noqa: BLE001 - report, don't crash: this is a gate check
        ok, detail = False, f"{type(e).__name__}: {e}"
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")
    return ok


def plain():
    reply = str(Agent(model=make_model(), callback_handler=None)("Reply with exactly: pong")).strip()
    return "pong" in reply.lower(), repr(reply[:80])


def structured():
    agent = Agent(model=make_model(), callback_handler=None)
    result = agent(
        "Extract the payment: Rent of $1,450 paid to Westport Property Mgmt on 2026-09-01.",
        structured_output_model=Payment,
    )
    p = result.structured_output
    ok = "westport" in p.payee.lower() and p.amount == 1450 and p.date == date(2026, 9, 1)
    return ok, repr(p)


if __name__ == "__main__":
    results = [check("plain reply", plain), check("structured output", structured)]
    sys.exit(0 if all(results) else 1)
