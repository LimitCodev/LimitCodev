#!/usr/bin/env python3
"""fetch.py — refresh data/raw/ from the GitHub API.

    GITHUB_TOKEN=... python scripts/fetch.py

Writes the same four files the generators already read (user, repos,
languages, contributions) plus `snapshot.json`, the date the data was taken,
which the banner prints. Run daily by `.github/workflows/refresh.yml`; the
Actions token is enough, since everything read here is public.

Contributions come from GraphQL and cover the default window (the last year).
Private contributions are only counted when the token belongs to the user.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
LOGIN = json.loads((ROOT / "data/profile.json").read_text(encoding="utf-8"))["identity"]["handle"]
API = "https://api.github.com"
LIMA = dt.timezone(dt.timedelta(hours=-5))   # Peru has no DST; the date the owner sees

CONTRIBUTIONS_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      totalCommitContributions
      totalIssueContributions
      totalPullRequestContributions
      totalRepositoryContributions
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date } }
      }
    }
  }
}
"""


def _request(url: str, body: dict | None = None) -> object:
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise SystemExit("GITHUB_TOKEN is required (GraphQL refuses anonymous calls)")
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {token}",
                 "Accept": "application/vnd.github+json",
                 "User-Agent": "limitcodev-profile-refresh"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def _write(name: str, data: object) -> None:
    (RAW / name).write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")),
                            encoding="utf-8")


def main() -> None:
    user = _request(f"{API}/users/{LOGIN}")
    repos = _request(f"{API}/users/{LOGIN}/repos?type=owner&sort=pushed&per_page=100")
    repos = [r for r in repos if not r["fork"]]

    per_repo: dict[str, dict[str, int]] = {}
    for r in repos:
        langs = _request(f"{API}/repos/{r['full_name']}/languages")
        if langs:
            per_repo[r["name"]] = langs
    totals: dict[str, int] = {}
    for langs in per_repo.values():
        for name, size in langs.items():
            totals[name] = totals.get(name, 0) + size
    totals = dict(sorted(totals.items(), key=lambda kv: -kv[1]))

    contrib = _request(f"{API}/graphql",
                       {"query": CONTRIBUTIONS_QUERY, "variables": {"login": LOGIN}})
    if contrib.get("errors"):
        raise SystemExit(f"GraphQL error: {contrib['errors']}")

    _write("user.json", user)
    _write("repos.json", repos)
    (RAW / "languages.json").write_text(
        json.dumps({"per_repo": per_repo, "totals": totals}, indent=2) + "\n", encoding="utf-8")
    _write("contributions.json", contrib)
    _write("snapshot.json", {"date": dt.datetime.now(LIMA).date().isoformat()})
    print(f"{LOGIN}: {user['public_repos']} public repos, {len(totals)} languages, "
          f"{contrib['data']['user']['contributionsCollection']['contributionCalendar']['totalContributions']}"
          f" contributions")


if __name__ == "__main__":
    main()
