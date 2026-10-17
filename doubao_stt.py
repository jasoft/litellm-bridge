"""Bounded subprocess entry point; heavy ASR imports stay off the recording path."""
from __future__ import annotations

import asyncio
import fcntl
import json
import os
import sys
from pathlib import Path


def main() -> None:
    os.umask(0o077)
    from doubaoime_asr import ASRConfig, transcribe

    credentials = Path(os.environ.get(
        "DOUBAO_CREDENTIAL_PATH",
        str(Path(__file__).resolve().parent / "data" / "doubao-asr-credentials.json"),
    )).expanduser()
    credentials.parent.mkdir(parents=True, exist_ok=True)
    config = ASRConfig(credential_path=credentials, connect_timeout=5, recv_timeout=5)
    # Concurrent uploads must reuse one registration and never read a half-written cache.
    with credentials.with_suffix(".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        config.ensure_credentials()
        credentials.chmod(0o600)
    text = asyncio.run(transcribe(Path(sys.argv[1]), config=config, realtime=False))
    print(json.dumps({"text": text}, ensure_ascii=False))


if __name__ == "__main__":
    main()
