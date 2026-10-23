#!/usr/bin/env python3
"""stack-watch seen-items ledger.

The ledger (stack-watch/ledger.json in the target repo) records every vendor
item ever seen, with a content hash, dates, severity, and the user's decision,
plus a history of runs. It prevents repeat reporting across runs and is the
only record of when the last probe ran.

Decision values: ticketed, watch, dismissed, auto-dismissed, pending.
"pending" marks an item presented in a proposal table that the user has not
decided on yet; it is re-shown on the next run with a "previously proposed,
awaiting decision" note.

CLI usage (all subcommands take the ledger path first; the file is created
empty if missing):

    ledger.py <ledger.json> hash <vendor> <url> <title>
    ledger.py <ledger.json> seen <hash>            -> prints the decision or "no"
    ledger.py <ledger.json> add                    -> reads one item JSON object,
                                                      or an array of them, on stdin
    ledger.py <ledger.json> set-decision <hash> <decision> [ticket_url]
    ledger.py <ledger.json> last-probed            -> prints ISO date or "null"
    ledger.py <ledger.json> record-run <mode> <lookback_from> <items_seen> <items_proposed>
    ledger.py <ledger.json> list [decision]        -> prints matching items JSON
    ledger.py <ledger.json> filter                 -> reads an item array (or
                                                      {"items": [...]}) on stdin,
                                                      prints {"new", "reshow", "dropped"}

Also importable: seen(), add(), add_many(), set_decision(), last_probed(),
filter_items(), item_hash().
Standard library only.
"""

import datetime
import hashlib
import json
import os
import sys

SCHEMA_VERSION = 1
BODY_KEEP = 200  # characters of an item's body kept in the ledger
# Noise entries keep only what dedupe and audit need; the report has the rest.
NOISE_FIELDS = {"hash", "vendor", "title", "url", "date", "severity", "decision",
                "first_seen", "source_type"}
DECISIONS = {"ticketed", "watch", "dismissed", "auto-dismissed", "pending"}


def item_hash(vendor, url, title):
    raw = f"{vendor}|{url}|{title}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load(path):
    if not os.path.isfile(path):
        return {"schema_version": SCHEMA_VERSION, "runs": [], "items": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def find(data, h):
    index = data.get("_index")
    if index is None:
        index = data["_index"] = {i.get("hash"): i for i in data["items"]}
    return index.get(h)


def save(path, data):
    data = {k: v for k, v in data.items() if k != "_index"}
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


def seen(path, h):
    """Return the item dict if the hash is in the ledger, else None."""
    return find(load(path), h)


def _add_to(data, item):
    if not item.get("hash"):
        item["hash"] = item_hash(item.get("vendor", ""), item.get("url", ""),
                                 item.get("title", ""))
    existing = find(data, item["hash"])
    if existing:
        return existing
    item.setdefault("first_seen", datetime.date.today().isoformat())
    item.setdefault("decision", "pending")
    if item["decision"] not in DECISIONS:
        raise ValueError(f"unknown decision: {item['decision']}")
    if item["decision"] == "auto-dismissed":
        item = {k: v for k, v in item.items() if k in NOISE_FIELDS}
    elif isinstance(item.get("body"), str) and len(item["body"]) > BODY_KEEP:
        item["body"] = item["body"][:BODY_KEEP].rstrip() + "..."  # the report holds the full text
    data["items"].append(item)
    find(data, None)  # make sure the index exists before updating it
    data["_index"][item["hash"]] = item
    return item


def add(path, item):
    """Add one item. Fills hash, first_seen, and default decision if absent.
    Refuses a duplicate hash (returns the existing item unchanged)."""
    data = load(path)
    result = _add_to(data, item)
    save(path, data)
    return result


def add_many(path, items):
    """Add a list of items in one load/save. Returns the stored items."""
    data = load(path)
    results = [_add_to(data, item) for item in items]
    save(path, data)
    return results


def set_decision(path, h, decision, ticket_url=None):
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision}")
    data = load(path)
    item = find(data, h)
    if item is None:
        raise KeyError(f"hash not in ledger: {h}")
    item["decision"] = decision
    item["decided_on"] = datetime.date.today().isoformat()
    if ticket_url:
        item["ticket_url"] = ticket_url
    save(path, data)
    return item


RESHOW_NOTES = {"watch": "previously watched",
                "pending": "previously proposed, awaiting decision"}


def filter_items(path, items):
    """Split freshly collected items against the ledger.

    new:     never seen
    reshow:  seen with decision watch or pending; each carries a "note"
    dropped: count of items already ticketed, dismissed, or auto-dismissed
    """
    data = load(path)
    by_hash = {i.get("hash"): i for i in data["items"]}
    out = {"new": [], "reshow": [], "dropped": 0}
    for item in items:
        if not item.get("hash"):
            item["hash"] = item_hash(item.get("vendor", ""), item.get("url", ""),
                                     item.get("title", ""))
        prior = by_hash.get(item["hash"])
        if prior is None:
            out["new"].append(item)
        elif prior.get("decision") in RESHOW_NOTES:
            item = dict(item, note=RESHOW_NOTES[prior["decision"]],
                        first_seen=prior.get("first_seen"))
            out["reshow"].append(item)
        else:
            out["dropped"] += 1
    return out


def last_probed(path):
    """ISO date of the most recent probe run recorded, else None."""
    data = load(path)
    dates = [r["date"] for r in data["runs"] if r.get("mode") == "probe"]
    return max(dates) if dates else None


def record_run(path, mode, lookback_from, items_seen, items_proposed):
    data = load(path)
    if lookback_from in ("", "null", "none"):
        lookback_from = None
    run = {"date": datetime.date.today().isoformat(), "mode": mode,
           "lookback_from": lookback_from, "items_seen": int(items_seen),
           "items_proposed": int(items_proposed)}
    data["runs"].append(run)
    save(path, data)
    return run


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(2)
    try:
        run_cli(sys.argv[1], sys.argv[2], sys.argv[3:])
    except (KeyError, ValueError, IndexError) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"error: invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)


def run_cli(path, cmd, rest):
    if cmd == "hash":
        print(item_hash(*rest))
    elif cmd == "seen":
        item = seen(path, rest[0])
        print(item["decision"] if item else "no")
    elif cmd == "add":
        payload = json.load(sys.stdin)
        if isinstance(payload, list):
            print(json.dumps(add_many(path, payload)))
        else:
            print(json.dumps(add(path, payload)))
    elif cmd == "set-decision":
        h, decision = rest[0], rest[1]
        url = rest[2] if len(rest) > 2 else None
        print(json.dumps(set_decision(path, h, decision, url)))
    elif cmd == "last-probed":
        print(last_probed(path) or "null")
    elif cmd == "record-run":
        print(json.dumps(record_run(path, *rest)))
    elif cmd == "filter":
        payload = json.load(sys.stdin)
        items = payload.get("items", []) if isinstance(payload, dict) else payload
        print(json.dumps(filter_items(path, items)))
    elif cmd == "list":
        data = load(path)
        items = data["items"]
        if rest:
            items = [i for i in items if i.get("decision") == rest[0]]
        print(json.dumps(items, indent=2))
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
