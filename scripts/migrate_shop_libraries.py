#!/usr/bin/env python3
"""One-shot migration: expose every library for TG-linked Emby accounts.

The script is intentionally not imported or scheduled by the bot. Run it manually
from the repository root. It only visits ``emby`` / ``emby_server_accounts``
records and never touches the independent ``emby2`` accounts. Failed accounts are
reported and can safely be retried; each update is idempotent.
"""
import asyncio
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_

from bot import LOGGER
from bot.func_helper.emby import get_emby, primary_server_name, server_account_targets
from bot.sql_helper.sql_emby import Emby, get_all_emby


async def open_account(server: str, emby_id: str) -> bool:
    service = get_emby(server)
    current = await service._request("GET", f"/emby/Users/{emby_id}")
    if not current.success or not current.data:
        LOGGER.error("library migration: read failed server=%s embyid=%s error=%s", server, emby_id, current.error)
        return False
    policy = dict(current.data.get("Policy") or {})
    policy["EnableAllFolders"] = True
    policy["EnabledFolders"] = []
    policy["BlockedMediaFolders"] = []
    updated = await service._request("POST", f"/emby/Users/{emby_id}/Policy", json=policy)
    if not updated.success:
        LOGGER.error("library migration: update failed server=%s embyid=%s error=%s", server, emby_id, updated.error)
        return False
    return True


async def migrate() -> int:
    rows = get_all_emby(and_(Emby.tg.is_not(None), Emby.embyid.is_not(None))) or []
    failures = []
    total = 0
    for row in rows:
        targets = server_account_targets(tg=row.tg, embyid=row.embyid)
        for server, emby_id in targets:
            total += 1
            if not await open_account(server, emby_id):
                failures.append((row.tg, server, emby_id))
    print(f"library migration complete: attempted={total} failed={len(failures)}")
    for tg, server, emby_id in failures:
        print(f"FAILED tg={tg} server={server} embyid={emby_id}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(migrate()))
