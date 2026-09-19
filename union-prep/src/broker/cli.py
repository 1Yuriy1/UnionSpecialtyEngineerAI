"""Run one submission end to end.

    python -m broker.cli data/samples/app_001_contractor.txt
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .llm import Client
from .models import Submission
from .pipeline import Broker, load_carriers


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("application", type=Path)
    ap.add_argument("--carriers", type=Path, default=Path("data/carriers.yaml"))
    ap.add_argument("--reply", type=Path, help="a carrier reply to ingest")
    ap.add_argument("--reply-from", default="HALLMARK_E&S")
    ap.add_argument("--force", action="store_true", help="skip the human review gate")
    args = ap.parse_args()

    broker = Broker(Client(), load_carriers(args.carriers))
    sub = Submission(
        submission_id=args.application.stem,
        received_at=date.today(),
        source_text=args.application.read_text(),
    )

    sub = broker.intake(sub)
    print(f"\n--- extraction [{sub.state.value}] ---")
    assert sub.risk
    for name, field in sub.risk.__dict__.items():
        if hasattr(field, "value"):
            flag = "  <-- review" if field.needs_review else ""
            print(f"  {name:28} {field.value!r:40} {field.confidence:.2f}{flag}")

    print("\n--- appetite ---")
    drafts = broker.market(sub, override_review=args.force)
    for m in sub.matches:
        print(f"  {m.carrier_name:28} {m.decision:7} {m.score:.2f}  "
              f"{'; '.join(m.hard_blocks or m.reasons)}")

    print("\n--- drafts ---")
    for d in drafts:
        print(f"\nSubject: {d.subject}\n{d.body}\n{'-' * 60}")

    if args.reply:
        broker.ingest_reply(sub, args.reply_from, args.reply.read_text())
        print("\n--- quotes ---")
        print(broker.summarise(sub))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
