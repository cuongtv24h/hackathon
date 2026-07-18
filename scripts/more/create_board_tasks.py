"""
Task Packet → GitHub Project Board automation.
Reads .packet.md files with YAML frontmatter and creates GitHub issues + project cards.
Supports sync mode: attach existing issues to project if not already there.
---------------------
Task Packets (markdown files)
         │
         ▼
    Parser script
    (đọc .packet.md → extract metadata + body)
         │
         ▼
    GitHub API script
    (tạo issue + gán labels + add to project)
         │
         ▼
    Git Project Board
    (cards tự xuất hiện ở Prompt Backlog)

Usage:
  python scripts/create_board_tasks.py [options]

Options:
  --packets-dir PATH    Thư mục chứa .packet.md files
                        Default: prompts/sprint-1/task-packets/
  --all-sprints         Read all prompts/sprint-*/task-packets/*.packet.md
  --repo STRING         GitHub repo (owner/name)
                        Example: ratrichero/bankcrm
  --project NUMBER      GitHub Project number
                        Example: 1
  --token STRING        GitHub PAT
                        hoặc đọc từ env GITHUB_TOKEN
  --dry-run             Chỉ in ra, không tạo thật
  --skip-existing       Bỏ qua task đã tồn tại (check by title prefix)
  --update-existing     Cập nhật title, body và labels từ packet cho issue đã tồn tại
  --help                Show help

Flow:
  1. Đọc tất cả .packet.md trong packets-dir
  2. Parse frontmatter → metadata
  3. Parse body (phần sau frontmatter) → issue body
  4. Với mỗi packet:
     a. Check xem issue [TASK_ID] đã tồn tại chưa
     b. Nếu chưa → tạo issue
     c. Gán labels
     d. Add issue vào project
     e. (Optional) Set project column = Prompt Backlog
  5. In summary report

Dependencies:
  - pyyaml
  - requests (hoặc PyGithub)

Output:
  - issues created on GitHub
  - cards appear on project board
  - labels auto-created if not exist

Test
python scripts/create_board_tasks.py --repo ratrichero/bankcrm --project 1 --sync --dry-run
python scripts/create_board_tasks.py --repo ratrichero/bankcrm --project 1 --dry-run

Set ENV and Run ( powershell ):
$env:GITHUB_TOKEN=""

## Chế độ 1 — Tạo mới + add vào project (mặc định)

python scripts/create_board_tasks.py --repo ratrichero/bankcrm --project 1

## Chế độ 2 — Sync mode
python scripts/create_board_tasks.py --repo ratrichero/bankcrm --project 1 --sync

Sync mode sẽ:

tạo issue mới nếu chưa có
attach issue cũ vào board nếu đã có nhưng chưa ở project
skip nếu đã có cả issue lẫn project item


"""

import os
import sys
import argparse
import yaml
import requests
from pathlib import Path


GITHUB_API = "https://api.github.com"
GRAPHQL_API = "https://api.github.com/graphql"


def get_headers(token: str) -> dict:
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def get_graphql_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


# ─────────────────────────────────────────────
# Packet parser
# ─────────────────────────────────────────────

def parse_packet(filepath: Path) -> dict:
    content = filepath.read_text(encoding="utf-8")

    if not content.startswith("---"):
        raise ValueError(f"No frontmatter found in {filepath}")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Invalid frontmatter format in {filepath}")

    frontmatter = yaml.safe_load(parts[1])
    body = parts[2].strip()

    return {
        "meta": frontmatter,
        "body": body,
        "file": str(filepath),
    }


# ─────────────────────────────────────────────
# GitHub REST operations
# ─────────────────────────────────────────────

def ensure_label(repo: str, label_name: str, headers: dict) -> None:
    url = f"{GITHUB_API}/repos/{repo}/labels"
    check_url = f"{url}/{requests.utils.quote(label_name)}"
    resp = requests.get(check_url, headers=headers)
    if resp.status_code == 200:
        return

    color_map = {
        "sprint": "0E8A16",
        "wave": "1D76DB",
        "pool": "D93F0B",
        "priority": "B60205",
        "layer": "FBCA04",
    }
    prefix = label_name.split(":")[0] if ":" in label_name else "default"
    color = color_map.get(prefix, "EDEDED")

    requests.post(url, headers=headers, json={
        "name": label_name,
        "color": color,
    })


def find_existing_issue(repo: str, task_id: str, headers: dict) -> dict | None:
    """Find existing issue by [TASK_ID] prefix. Returns {number, node_id} or None."""
    url = f"{GITHUB_API}/repos/{repo}/issues"
    params = {"state": "all", "per_page": 100}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()

    prefix = f"[{task_id}]"
    for issue in resp.json():
        if issue.get("title", "").startswith(prefix):
            return {
                "number": issue["number"],
                "node_id": issue["node_id"],
            }
    return None


def create_issue(repo: str, title: str, body: str, labels: list[str], headers: dict) -> dict:
    """Create GitHub issue. Returns {number, node_id}."""
    url = f"{GITHUB_API}/repos/{repo}/issues"
    payload = {
        "title": title,
        "body": body,
        "labels": labels,
    }
    resp = requests.post(url, headers=headers, json=payload)
    resp.raise_for_status()
    data = resp.json()
    return {
        "number": data["number"],
        "node_id": data["node_id"],
    }


def update_issue(
    repo: str, issue_number: int, title: str, body: str, labels: list[str], headers: dict
) -> None:
    """Synchronize an existing issue with its canonical task packet."""
    url = f"{GITHUB_API}/repos/{repo}/issues/{issue_number}"
    resp = requests.patch(url, headers=headers, json={
        "title": title,
        "body": body,
        "labels": labels,
    })
    resp.raise_for_status()


# ─────────────────────────────────────────────
# GitHub GraphQL operations
# ─────────────────────────────────────────────

def get_project_id(owner: str, project_number: int, token: str) -> str | None:
    """Get Project V2 ID. Tries user first, then org."""
    headers = get_graphql_headers(token)

    # Try as user
    query = """
    query($owner: String!, $number: Int!) {
      user(login: $owner) {
        projectV2(number: $number) {
          id
        }
      }
    }
    """
    resp = requests.post(GRAPHQL_API, headers=headers, json={
        "query": query,
        "variables": {"owner": owner, "number": project_number},
    })
    data = resp.json()

    try:
        return data["data"]["user"]["projectV2"]["id"]
    except (KeyError, TypeError):
        pass

    # Try as org
    query_org = """
    query($owner: String!, $number: Int!) {
      organization(login: $owner) {
        projectV2(number: $number) {
          id
        }
      }
    }
    """
    resp = requests.post(GRAPHQL_API, headers=headers, json={
        "query": query_org,
        "variables": {"owner": owner, "number": project_number},
    })
    data = resp.json()

    try:
        return data["data"]["organization"]["projectV2"]["id"]
    except (KeyError, TypeError):
        return None


def check_item_in_project(project_id: str, issue_node_id: str, token: str) -> bool:
    """Check if issue is already in the project."""
    headers = get_graphql_headers(token)

    query = """
    query($projectId: ID!, $first: Int!) {
      node(id: $projectId) {
        ... on ProjectV2 {
          items(first: $first) {
            nodes {
              content {
                ... on Issue {
                  id
                }
              }
            }
          }
        }
      }
    }
    """

    cursor = None
    checked = 0
    while True:
        variables = {"projectId": project_id, "first": 100}
        if cursor:
            # For pagination, would need after parameter
            # For simplicity, check first 100 items
            pass

        resp = requests.post(GRAPHQL_API, headers=headers, json={
            "query": query,
            "variables": variables,
        })
        data = resp.json()

        try:
            items = data["data"]["node"]["items"]["nodes"]
        except (KeyError, TypeError):
            return False

        for item in items:
            try:
                if item["content"]["id"] == issue_node_id:
                    return True
            except (KeyError, TypeError):
                continue

        # Simple approach: only check first 100
        break

    return False


def add_issue_to_project(project_id: str, issue_node_id: str, token: str) -> str | None:
    """Add issue to project using correct GraphQL mutation."""
    headers = get_graphql_headers(token)

    mutation = """
    mutation($projectId: ID!, $contentId: ID!) {
      addProjectV2ItemById(input: {
        projectId: $projectId
        contentId: $contentId
      }) {
        item {
          id
        }
      }
    }
    """

    resp = requests.post(GRAPHQL_API, headers=headers, json={
        "query": mutation,
        "variables": {
            "projectId": project_id,
            "contentId": issue_node_id,
        },
    })

    data = resp.json()
    try:
        return data["data"]["addProjectV2ItemById"]["item"]["id"]
    except (KeyError, TypeError):
        print(f"  [WARN] GraphQL response: {data}")
        return None


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Sync Task Packets to GitHub Project Board"
    )
    parser.add_argument(
        "--packets-dir",
        default="prompts/sprint-1/task-packets",
        help="Directory containing .packet.md files",
    )
    parser.add_argument(
        "--all-sprints",
        action="store_true",
        help="Read all prompts/sprint-*/task-packets/*.packet.md files",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="GitHub repo (owner/name)",
    )
    parser.add_argument(
        "--project",
        type=int,
        default=None,
        help="GitHub Project V2 number",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="GitHub PAT (or set GITHUB_TOKEN env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without executing",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip tasks that already have issues (legacy mode)",
    )
    parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Update existing issue title, body and labels from its task packet",
    )
    parser.add_argument(
        "--sync",
        action="store_true",
        help="Sync mode: create missing issues AND attach existing issues to project",
    )
    args = parser.parse_args()

    token = args.token or os.environ.get("GITHUB_TOKEN")
    if not token:
        print("[ERROR] GitHub token required. Use --token or set GITHUB_TOKEN env.")
        sys.exit(1)

    headers = get_headers(token)
    packets_dir = Path(args.packets_dir)

    if args.all_sprints:
        packet_files = sorted(Path("prompts").glob("sprint-*/task-packets/*.packet.md"))
    else:
        if not packets_dir.exists():
            print(f"[ERROR] Packets directory not found: {packets_dir}")
            sys.exit(1)
        packet_files = sorted(packets_dir.glob("*.packet.md"))

    if not packet_files:
        source = "prompts/sprint-*/task-packets" if args.all_sprints else str(packets_dir)
        print(f"[WARN] No .packet.md files found in {source}")
        sys.exit(0)

    owner = args.repo.split("/")[0]

    # Get project ID once
    project_id = None
    if args.project:
        if not args.dry_run:
            project_id = get_project_id(owner, args.project, token)
            if not project_id:
                print(f"[WARN] Could not find project #{args.project} for {owner}")
                print(f"[WARN] Issues will be created but not added to project")

    print(f"\n{'='*60}")
    print(f"[BOARD] Syncing {len(packet_files)} packets")
    print(f"[BOARD] Repo: {args.repo}")
    print(f"[BOARD] Project: {args.project or 'none'}")
    print(f"[BOARD] Source: {'all sprints' if args.all_sprints else packets_dir}")
    print(f"[BOARD] Mode: {'sync' if args.sync else 'skip-existing' if args.skip_existing else 'create'}")
    print(f"[BOARD] Dry run: {args.dry_run}")
    print(f"{'='*60}\n")

    created = 0
    attached = 0
    updated = 0
    skipped = 0
    errors = 0

    for pf in packet_files:
        try:
            packet = parse_packet(pf)
        except Exception as e:
            print(f"[ERROR] Failed to parse {pf}: {e}")
            errors += 1
            continue

        meta = packet["meta"]
        task_id = meta["task_id"]
        title = f"[{task_id}] {meta['title']}"
        labels = meta.get("labels", [])
        body = packet["body"]

        print(f"--- {task_id} ---")

        # Check if issue already exists
        existing = find_existing_issue(args.repo, task_id, headers)

        if existing:
            issue_number = existing["number"]
            issue_node_id = existing["node_id"]
            print(f"  [INFO] Issue already exists: #{issue_number}")

            if args.skip_existing and not args.sync:
                print(f"  [SKIP] --skip-existing mode, skipping")
                skipped += 1
                continue

            if args.update_existing:
                if args.dry_run:
                    print(f"  [DRY] Would update #{issue_number}: {title}")
                    updated += 1
                else:
                    try:
                        for label in labels:
                            ensure_label(args.repo, label, headers)
                        update_issue(args.repo, issue_number, title, body, labels, headers)
                        print(f"  [OK] Updated existing #{issue_number}")
                        updated += 1
                    except Exception as e:
                        print(f"  [ERROR] Failed to update #{issue_number}: {e}")
                        errors += 1
                        continue

            if args.sync and project_id:
                # Check if already in project
                if args.dry_run:
                    print(f"  [DRY] Would check/attach #{issue_number} to project")
                    attached += 1
                    continue

                already_in_project = check_item_in_project(
                    project_id, issue_node_id, token
                )

                if already_in_project:
                    print(f"  [SKIP] Already in project")
                    skipped += 1
                else:
                    item_id = add_issue_to_project(
                        project_id, issue_node_id, token
                    )
                    if item_id:
                        print(f"  [OK] Attached existing #{issue_number} to project")
                        attached += 1
                    else:
                        print(f"  [ERROR] Failed to attach to project")
                        errors += 1
                continue
            else:
                if not args.update_existing:
                    print(f"  [SKIP] Issue exists, no --sync or --update-existing flag")
                    skipped += 1
                elif not args.sync:
                    print(f"  [OK] Updated issue; project attachment not requested")
                else:
                    print(f"  [WARN] Updated issue; Project ID is unavailable")
                continue

        # Issue does not exist — create it
        if args.dry_run:
            print(f"  [DRY] Would create: {title}")
            print(f"  [DRY] Labels: {labels}")
            print(f"  [DRY] Body length: {len(body)} chars")
            created += 1
            continue

        # Ensure labels
        for label in labels:
            ensure_label(args.repo, label, headers)

        # Create issue
        try:
            result = create_issue(args.repo, title, body, labels, headers)
            issue_number = result["number"]
            issue_node_id = result["node_id"]
            print(f"  [OK] Created issue #{issue_number}")
        except Exception as e:
            print(f"  [ERROR] Failed to create issue: {e}")
            errors += 1
            continue

        created += 1

        # Add to project
        if project_id:
            item_id = add_issue_to_project(project_id, issue_node_id, token)
            if item_id:
                print(f"  [OK] Added to project")
            else:
                print(f"  [WARN] Could not add to project")

    # Summary
    print(f"\n{'='*60}")
    print(f"[SUMMARY] Created:  {created}")
    print(f"[SUMMARY] Updated:  {updated}")
    print(f"[SUMMARY] Attached: {attached}")
    print(f"[SUMMARY] Skipped:  {skipped}")
    print(f"[SUMMARY] Errors:   {errors}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
