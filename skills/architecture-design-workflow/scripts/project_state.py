"""Record approved project stages and append-only revision identifiers in a local JSON file."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import sys
import tempfile

ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def present(value):
    return isinstance(value, str) and bool(value.strip())


def revision_id(stage, version):
    return f"{stage}/V{version}"


def new_project(stages):
    if (
        not stages
        or not all(isinstance(s, str) and ID.fullmatch(s) for s in stages)
        or len(set(stages)) != len(stages)
    ):
        raise ValueError("Supply unique stage ids using letters, digits, underscores, or hyphens")
    return {"schema": 1, "stages": stages, "status": "active", "revisions": [], "status_history": []}


def approval_ok(approval):
    return isinstance(approval, dict) and all(
        present(approval.get(key)) for key in ("by", "basis")
    )


def add_revision(state, stage, note, *, source=None, approval=None, artifacts=()):
    if state["status"] != "active":
        raise ValueError("Project paused; resume with the user's recorded basis first")
    if stage not in state["stages"]:
        raise ValueError(f"Unknown stage: {stage}")
    if not present(note):
        raise ValueError("Record what changed or why this revision was created")
    previous = state["revisions"]
    parent = previous[-1] if previous else None
    known = {r["id"] for r in previous}
    if source is not None and source not in known:
        raise ValueError(f"Unknown historical source: {source}")
    if (parent is None and stage != state["stages"][0]) or (
        parent is not None and parent["stage"] != stage
    ):
        if not approval_ok(approval):
            raise ValueError("Stage change requires a recorded approver and approval basis")
    if source is not None and parent is not None and source != parent["id"] and not approval_ok(approval):
        raise ValueError("Starting from a noncurrent revision requires a recorded decision")
    version = 1 + sum(r["stage"] == stage for r in previous)
    artifacts = list(artifacts)
    if not all(present(path) for path in artifacts):
        raise ValueError("Artifact references must be nonempty")
    paths = {os.path.normcase(os.path.normpath(path)) for path in artifacts}
    archived = {
        os.path.normcase(os.path.normpath(path))
        for revision in previous for path in revision["artifacts"]
    }
    if len(paths) != len(artifacts) or paths & archived:
        raise ValueError("Revision output paths must be unique; keep shared sources in the note")
    entry = {
        "id": revision_id(stage, version),
        "stage": stage,
        "version": version,
        "parent": parent["id"] if parent else None,
        "source": source if source is not None else (parent["id"] if parent else None),
        "note": note,
        "approval": approval,
        "artifacts": list(artifacts),
    }
    previous.append(entry)
    return entry


def set_status(state, status, note, approval=None):
    if status not in {"paused", "active"} or status == state["status"]:
        raise ValueError("Status must change between active and paused")
    if not present(note):
        raise ValueError("Record the reason for changing project status")
    if status == "active" and not approval_ok(approval):
        raise ValueError("Resume requires a recorded approver and approval basis")
    state["status"] = status
    state["status_history"].append(
        {"status": status, "reason": note, "approval": approval,
         "after_revisions": len(state["revisions"])}
    )


def validate_state(state):
    if not isinstance(state, dict) or state.get("schema") != 1:
        raise ValueError("Expected project-state schema 1")
    replay = new_project(state.get("stages"))
    changes = iter(state["status_history"])
    change = next(changes, None)
    for count in range(len(state["revisions"]) + 1):
        while change is not None and change["after_revisions"] == count:
            set_status(replay, change["status"], change["reason"], change["approval"])
            change = next(changes, None)
        if count == len(state["revisions"]):
            break
        entry = state["revisions"][count]
        actual = add_revision(
            replay, entry["stage"], entry["note"], source=entry["source"],
            approval=entry["approval"], artifacts=entry["artifacts"],
        )
        if actual != entry:
            raise ValueError(f"Invalid revision lineage: {entry.get('id')}")
    if change is not None or replay["status_history"] != state["status_history"]:
        raise ValueError("Invalid status history or revision index")
    if replay["status"] != state["status"]:
        raise ValueError("Project status disagrees with recorded status history")


@contextmanager
def single_writer(path):
    lock = path.with_name(path.name + ".lock")
    try:
        handle = lock.open("x", encoding="utf-8")
    except FileExistsError as exc:
        raise ValueError(f"Another writer or stale lock at {lock}; check before retrying") from exc
    try:
        with handle:
            handle.write(str(os.getpid()))
        yield
    finally:
        lock.unlink()


def save(path, state):
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(state, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.close()
            os.replace(temporary, path)
        finally:
            stream.close()
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("stages", nargs="+")
    sub.add_parser("check")
    record = sub.add_parser("record")
    record.add_argument("stage")
    record.add_argument("--source")
    record.add_argument("--artifact", action="append", default=[])
    for command in (record, sub.add_parser("pause"), sub.add_parser("resume")):
        command.add_argument("--note", required=True)
        command.add_argument("--approved-by")
        command.add_argument("--basis")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            state = read(args.file)
            validate_state(state)
            result = {"valid": True, "status": state["status"], "revisions": len(state["revisions"])}
        else:
            with single_writer(args.file):
                if args.command == "init":
                    if args.file.exists():
                        raise ValueError("Project state already exists")
                    state = new_project(args.stages)
                    result = state
                else:
                    state = read(args.file)
                    validate_state(state)
                    approval = None
                    if args.approved_by or args.basis:
                        approval = {"by": args.approved_by, "basis": args.basis}
                        if not approval_ok(approval):
                            raise ValueError("Provide both --approved-by and --basis")
                    if args.command == "record":
                        result = add_revision(
                            state, args.stage, args.note, source=args.source,
                            approval=approval, artifacts=args.artifact,
                        )
                    else:
                        set_status(state, "paused" if args.command == "pause" else "active", args.note, approval)
                        result = state["status_history"][-1]
                save(args.file, state)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"project state: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
