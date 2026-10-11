"""Load a persona spec and turn its relative dates into real ones."""

import calendar
from datetime import date, timedelta
from pathlib import Path

import yaml

PERSONAS = Path(__file__).resolve().parents[3] / "scripts" / "personas"


class Persona:
    """scripts/personas/<name>.yaml plus the date arithmetic its header describes."""

    def __init__(self, spec: dict, today: date) -> None:
        self.spec = spec
        self.today = today
        self.monday = today - timedelta(days=today.weekday())
        self.profile = spec["profile"]
        self.assignments = {a["id"]: a for a in spec["assignments"]}

    @classmethod
    def load(cls, name: str, today: date | None = None) -> "Persona":
        spec = yaml.safe_load((PERSONAS / f"{name}.yaml").read_text(encoding="utf-8"))
        return cls(spec, today or date.today())

    def month(self, offset: int) -> tuple[int, int]:
        """(year, month) of the calendar month `offset` months from the current one."""
        index = self.today.year * 12 + self.today.month - 1 + offset
        return index // 12, index % 12 + 1

    def resolve(self, when: dict) -> date:
        """{mo, day} or {wk, day} -> date. A day past the month's end clamps to its last day."""
        if "mo" in when:
            year, month = self.month(when["mo"])
            last = calendar.monthrange(year, month)[1]
            return date(year, month, min(when.get("day", 1), last))
        return self.monday + timedelta(weeks=when["wk"], days=when.get("day", 0))

    def months(self, span: dict) -> list[int]:
        """{from, to, skip} -> month offsets, oldest first."""
        skip = set(span.get("skip", []))
        return [m for m in range(span["from"], span["to"] + 1) if m not in skip]

    def start(self, assignment_id: str) -> date:
        return self.resolve(self.assignments[assignment_id]["start"])

    def end(self, assignment_id: str) -> date:
        return self.resolve(self.assignments[assignment_id]["end"])

    def trips(self) -> list[tuple[date, date]]:
        """(depart, return) for every trip home: gap trips first, then extra trips."""
        specs = [gap for gap in self.spec["gaps"] if gap["trip_home"]]
        specs += self.spec.get("extra_trips", [])
        return [(self.resolve(trip["depart"]), self.resolve(trip["return"])) for trip in specs]

    def assignment_on(self, day: date) -> dict | None:
        for assignment in self.spec["assignments"]:
            if self.resolve(assignment["start"]) <= day <= self.resolve(assignment["end"]):
                return assignment
        return None
