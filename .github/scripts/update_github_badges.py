import json
import os
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


def write_badge(path: Path, label: str, value: str, color: str) -> None:
    label_width = len(label) * 7 + 14
    value_width = len(value) * 7 + 14
    width = label_width + value_width
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="22" role="img" aria-labelledby="title">
  <title id="title">{label}: {value}</title>
  <clipPath id="rounded"><rect width="{width}" height="22" rx="4"/></clipPath>
  <g clip-path="url(#rounded)">
    <rect width="{width}" height="22" fill="#333"/>
    <rect x="{label_width}" width="{value_width}" height="22" fill="{color}"/>
  </g>
  <g fill="#fff" font-family="monospace" font-size="11" text-anchor="middle">
    <text x="{label_width / 2}" y="15">{label}</text>
    <text x="{label_width + value_width / 2}" y="15">{value}</text>
  </g>
</svg>
'''
    path.write_text(svg, encoding="utf-8")


def main() -> None:
    token = os.environ.get("CONTRIBUTIONS_TOKEN")
    if not token:
        raise SystemExit("Set the CONTRIBUTIONS_TOKEN repository secret first.")

    now = datetime.now(UTC)
    counts = get_contributions(token, os.environ["GITHUB_REPOSITORY_OWNER"], now)
    streak = current_streak(counts, now.date())
    unit = "day" if streak == 1 else "days"
    assets = Path("asset")
    assets.mkdir(exist_ok=True)
    write_badge(assets / "current-streak.svg", "current streak", f"{streak} {unit}", "#b54708")
    write_badge(assets / "total-contributions.svg", "total contributions", f"{sum(counts.values()):,}", "#0969da")


if __name__ == "__main__":
    main()
