import re
import subprocess
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT_PY = ROOT / "src" / "waterlagen" / "__init__.py"

VERSION_RE = re.compile(r'__version__\s*=\s*"(\d{4})\.(\d{1,2})\.(\d+)"')
TAG_RE = re.compile(r"^v?(\d{4})\.(\d{1,2})\.(\d+)$")


def parse_version(s: str) -> tuple[int, int, int] | None:
    m = TAG_RE.match(s.strip())
    if not m:
        return None
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def get_latest_tag_version() -> tuple[int, int, int] | None:
    try:
        out = subprocess.check_output(["git", "tag"], cwd=ROOT, text=True)
    except Exception:
        return None
    versions = []
    for line in out.splitlines():
        v = parse_version(line)
        if v:
            versions.append(v)
    return max(versions) if versions else None


def get_current_version(text: str) -> tuple[int, int, int]:
    m = VERSION_RE.search(text)
    if not m:
        raise SystemExit("Could not find __version__ in __init__.py")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def main() -> int:
    text = INIT_PY.read_text(encoding="utf-8")
    current = get_current_version(text)
    latest_tag = get_latest_tag_version()

    # Pick the highest known version between tag and current
    base = max([v for v in [latest_tag, current] if v is not None])

    today = date.today()
    if (base[0], base[1]) == (today.year, today.month):
        next_version = (today.year, today.month, base[2] + 1)
    else:
        next_version = (today.year, today.month, 0)

    new_version = f'{next_version[0]}.{next_version[1]}.{next_version[2]}'
    if f'__version__ = "{new_version}"' in text:
        return 0

    new_text = VERSION_RE.sub(f'__version__ = "{new_version}"', text, count=1)
    INIT_PY.write_text(new_text, encoding="utf-8")
    print(f"Updated __version__ to {new_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
