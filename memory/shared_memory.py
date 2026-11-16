"""
Shared memory: ONE JSON file that holds every application record.

All agents read the record, and each agent writes only its own result back
(intake_result, eligibility_result, merit_result, need_result, final_decision).
Re-submitting the same application id keeps the old evaluation in
`previous_evaluations`, so history is never lost.
"""
import json
import os
from datetime import datetime
from pathlib import Path

import config


class SharedMemory:
    def __init__(self, path=config.MEMORY_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._save({"applications": {}})

    def _load(self):
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError(f"{self.path} is not valid JSON ({error}). "
                             'Fix it or replace its content with {"applications": {}}.') from error

    def _save(self, data):
        temp = self.path.with_suffix(".tmp")                 # write a temp file, then swap it in
        temp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp, self.path)

    def create_application(self, application_id):
        """Start a fresh record. If the id already exists, keep the old one as history."""
        data = self._load()
        record = {
            "application_id": application_id,
            "student_name": None, "cgpa": None, "family_income": None, "course": None,
            "achievements": [], "statement": None, "statement_summary": None,
            "intake_result": {}, "eligibility_result": {}, "merit_result": {},
            "need_result": {}, "final_decision": {}, "execution_trace": [],
            "submitted_at": datetime.now().isoformat(timespec="seconds"),
            "previous_evaluations": [],
        }
        old = data["applications"].get(application_id)
        if old:
            snapshot = {k: v for k, v in old.items() if k != "previous_evaluations"}
            record["previous_evaluations"] = old.get("previous_evaluations", []) + [snapshot]
        data["applications"][application_id] = record
        self._save(data)
        return record

    def get(self, application_id):
        record = self._load()["applications"].get(application_id)
        if record is None:
            raise KeyError(f"No application with id '{application_id}' in shared memory.")
        return record

    def update(self, application_id, key, value):
        self.update_many(application_id, {key: value})

    def update_many(self, application_id, fields):
        data = self._load()
        if application_id not in data["applications"]:
            raise KeyError(f"No application with id '{application_id}' in shared memory.")
        data["applications"][application_id].update(fields)
        self._save(data)

    def all_applications(self):
        """Every record, newest first."""
        records = list(self._load()["applications"].values())
        return sorted(records, key=lambda r: r.get("submitted_at", ""), reverse=True)
