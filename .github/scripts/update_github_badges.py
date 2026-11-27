import json
import os
from base64 import b64encode
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen


ACCOUNT_QUERY = """
query {
  viewer {
    login
    contributionsCollection { contributionYears }
  }
}
"""

CALENDAR_QUERY = """
query($from: DateTime!, $to: DateTime!) {
  viewer {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""

# https://github.com/simple-icons/simple-icons/blob/develop/icons/github.svg
GITHUB_LOGO = (
    '<svg fill="#fff" role="img" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">'
    '<title>GitHub</title><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 '
    '8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61'
    'C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 '
    '1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466'
    '-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 '
    '3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23'
    '.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92'
    '.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 '
    '24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>'
)


def graphql(token: str, query: str, **variables) -> dict:
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "github-profile-badges",
        },
    )
    with urlopen(request, timeout=20) as response:
        payload = json.load(response)
    if payload.get("errors"):
        messages = [error["message"] for error in payload["errors"]]
        raise RuntimeError("GitHub GraphQL: " + ", ".join(messages))
    return payload["data"]["viewer"]


def get_contributions(token: str, owner: str, now: datetime) -> dict[date, int]:
    account = graphql(token, ACCOUNT_QUERY)
    if account["login"].casefold() != owner.casefold():
        raise SystemExit(f"CONTRIBUTIONS_TOKEN must belong to {owner}.")

    years = set(account["contributionsCollection"]["contributionYears"])
    counts = {}
    for year in sorted(years | {now.year - 1, now.year}):
        start = datetime(year, 1, 1, tzinfo=UTC)
        end = min(now, datetime(year + 1, 1, 1, tzinfo=UTC) - timedelta(seconds=1))
        viewer = graphql(token, CALENDAR_QUERY, **{
            "from": start.isoformat(timespec="seconds"),
            "to": end.isoformat(timespec="seconds"),
        })
        calendar = viewer["contributionsCollection"]["contributionCalendar"]
        for week in calendar["weeks"]:
            for entry in week["contributionDays"]:
                day = date.fromisoformat(entry["date"])
                if start.date() <= day <= end.date():
                    counts[day] = entry["contributionCount"]
    return counts


def current_streak(counts: dict[date, int], today: date) -> int:
    day = today if counts.get(today, 0) else today - timedelta(days=1)
    streak = 0
    while counts.get(day, 0):
        streak += 1
        day -= timedelta(days=1)
    return streak


def badge_text(text: str, center: int, width: int) -> str:
    # The flat style renders text at 10x scale for subpixel placement.
    return (
        '<g transform="scale(.1)"><g aria-hidden="true" fill="#010101">'
        f'<text x="{center}" y="150" fill-opacity=".8" filter="url(#blur)" textLength="{width * 10}">{text}</text>'
        f'<text x="{center}" y="150" fill-opacity=".3" textLength="{width * 10}">{text}</text></g>'
        f'<text x="{center}" y="140" textLength="{width * 10}">{text}</text></g>'
    )


def write_badge(path: Path, label: str, label_width: int, count: int, color: str, *, days: bool = False) -> None:
    digits = str(count)
    value = digits + (" days" if days else "")
    # Shields flat uses 11px Verdana: 6.99px per digit and 29.57px for ' days'.
    # Floor the width in pixels and round it up to the next odd number if even.
    value_width = (699 * len(digits) + (2957 if days else 0)) // 100
    value_width |= 1
    left_width = label_width + 27  # 14px logo, 3px gap, 10px padding
    right_width = value_width + 10
    width = left_width + right_width
    logo = b64encode(GITHUB_LOGO.encode()).decode()
    title = f"{label}: {value}"
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="20" role="img" aria-label="{title}">'
        f'<title>{title}</title><filter id="blur"><feGaussianBlur stdDeviation="16"/></filter>'
        '<linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/>'
        '<stop offset="1" stop-opacity=".1"/></linearGradient>'
        f'<clipPath id="r"><rect width="{width}" height="20" rx="3"/></clipPath><g clip-path="url(#r)">'
        f'<rect width="{left_width}" height="20" fill="#555"/>'
        f'<rect x="{left_width}" width="{right_width}" height="20" fill="{color}"/>'
        f'<rect width="{width}" height="20" fill="url(#s)"/></g>'
        '<g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" '
        'text-rendering="geometricPrecision" font-size="110">'
        f'<image x="5" y="3" width="14" height="14" href="data:image/svg+xml;base64,{logo}"/>'
        + badge_text(label, 230 + label_width * 5, label_width)
        + badge_text(value, (left_width + 4) * 10 + value_width * 5, value_width)
        + '</g></svg>'
    )
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    token = os.environ.get("CONTRIBUTIONS_TOKEN")
    if not token:
        raise SystemExit("Set the CONTRIBUTIONS_TOKEN repository secret first.")

    now = datetime.now(UTC)
    counts = get_contributions(token, os.environ["GITHUB_REPOSITORY_OWNER"], now)
    streak = current_streak(counts, now.date())
    assets = Path("asset")
    assets.mkdir(exist_ok=True)
    write_badge(assets / "current-streak.svg", "current streak", 79, streak, "#ea7233", days=True)
    write_badge(assets / "total-contributions.svg", "total contributions", 101, sum(counts.values()), "#007ec6")


if __name__ == "__main__":
    main()
