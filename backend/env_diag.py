"""Quick helper to inspect Coze env loading and optionally test a call."""
import argparse
import asyncio
from pathlib import Path
from typing import List, Tuple

from coze_client import COZE_ENDPOINT, COZE_PROJECT_ID, _auth_header, _env_ready, coze_stream


def _mask(text: str) -> str:
    """Mask sensitive strings while showing length and a short prefix."""
    if not text:
        return "<missing>"
    prefix = text[:6]
    return f"{prefix}... (len={len(text)})"


def _print_env_summary() -> None:
    env_path = Path(__file__).with_name(".env")
    print(f".env path: {env_path} (exists={env_path.exists()})")
    print(f"COZE_ENDPOINT: {COZE_ENDPOINT or '<missing>'}")
    auth = _auth_header()
    print(f"COZE_TOKEN: {_mask(auth)} (starts with 'Bearer '? {'yes' if auth.lower().startswith('bearer ') else 'no'})")
    print(f"COZE_PROJECT_ID: {COZE_PROJECT_ID or '<missing>'}")
    print(f"_env_ready(): {_env_ready()}")


async def _test_stream(user_text: str, max_events: int = 5) -> List[Tuple[str, str]]:
    """Consume a few events from coze_stream for debugging."""
    events: List[Tuple[str, str]] = []
    async for event, data in coze_stream(user_text):
        events.append((event, str(data)))
        if len(events) >= max_events or event.lower() == "done":
            break
    return events


def main() -> None:
    parser = argparse.ArgumentParser(description="Diagnose Coze environment and optional stream test.")
    parser.add_argument("--test", action="store_true", help="Perform a short coze_stream test with text 'ping'.")
    args = parser.parse_args()

    _print_env_summary()

    if args.test:
        print("\nRunning stream test (text='ping'):")
        events = asyncio.run(_test_stream("ping"))
        for idx, (event, data) in enumerate(events, start=1):
            print(f"{idx}. event={event!r}, data={data!r}")


if __name__ == "__main__":
    main()
