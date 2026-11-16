"""
Append-only execution log.

logs/agent_logs.json is written in "JSON Lines" style: ONE JSON object per line.
Each new event is appended with open(path, "a"); the file is never rewritten,
so old records can never be overwritten.
"""
import json
from datetime import datetime
from pathlib import Path

import config


def now_iso():
    return datetime.now().isoformat(timespec="milliseconds")


def trace_entry(agent, action, tools_used, input_summary, output_summary, status, started):
    """One row of the 'Agent Execution Trace' shown in the dashboard and the notebook."""
    return {"agent": agent, "action": action, "tools_used": tools_used,
            "input_summary": input_summary, "output_summary": output_summary,
            "status": status, "started": started, "finished": now_iso()}


class ExecutionLog:
    def __init__(self, path=config.LOG_PATH):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)

    def log(self, application_id, agent, action, input_summary, output_summary, status="success"):
        entry = {"timestamp": now_iso(), "application_id": application_id, "agent": agent,
                 "action": action, "input_summary": input_summary,
                 "output_summary": output_summary, "status": status}
        with open(self.path, "a", encoding="utf-8") as file:     # "a" = append only
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_all(self, application_id=None):
        entries = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                entry = json.loads(line)
                if application_id is None or entry["application_id"] == application_id:
                    entries.append(entry)
        return entries
