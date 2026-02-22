"""Verify frontend membership wiring for ClusterView account details."""
from __future__ import annotations

import json
from pathlib import Path


def status(ok: bool, label: str) -> str:
    return f"{'✓' if ok else '✗'} {label}"


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    web_root = project_root / "graph-explorer" / "src"

    cluster_view_path = web_root / "ClusterView.jsx"
    data_path = web_root / "data.js"
    sidebar_path = web_root / "ClusterDetailsSidebar.jsx"
    panel_path = web_root / "AccountMembershipPanel.jsx"
    panel_test_path = web_root / "AccountMembershipPanel.test.jsx"
    integration_test_path = web_root / "ClusterView.integration.test.jsx"
    settings_path = project_root / "config" / "graph_settings.json"

    checks: list[str] = []

    checks.append(status(cluster_view_path.exists(), f"ClusterView present: {cluster_view_path}"))
    checks.append(status(data_path.exists(), f"data.js present: {data_path}"))
    checks.append(status(sidebar_path.exists(), f"ClusterDetailsSidebar present: {sidebar_path}"))
    checks.append(status(panel_path.exists(), f"AccountMembershipPanel present: {panel_path}"))
    checks.append(status(panel_test_path.exists(), f"Panel test present: {panel_test_path}"))
    checks.append(status(integration_test_path.exists(), f"Integration test present: {integration_test_path}"))

    cluster_view_text = cluster_view_path.read_text() if cluster_view_path.exists() else ""
    data_text = data_path.read_text() if data_path.exists() else ""
    sidebar_text = sidebar_path.read_text() if sidebar_path.exists() else ""

    checks.append(status("fetchAccountMembership" in data_text, "fetchAccountMembership API helper defined"))
    checks.append(status("/api/clusters/accounts/" in data_text, "Membership endpoint path wired in data helper"))
    checks.append(status("loadMembership" in cluster_view_text, "ClusterView includes membership loading flow"))
    checks.append(status("membershipLoading" in cluster_view_text and "membershipError" in cluster_view_text, "ClusterView tracks membership loading/error state"))
    checks.append(status("AccountMembershipPanel" in sidebar_text, "Sidebar renders AccountMembershipPanel"))

    settings_payload = {}
    if settings_path.exists():
        try:
            settings_payload = json.loads(settings_path.read_text())
        except Exception:
            settings_payload = {}
    settings = settings_payload.get("settings") if isinstance(settings_payload, dict) else {}
    if not isinstance(settings, dict):
        settings = {}
    checks.append(status("membership_engine" in settings, "Graph settings include membership_engine"))

    failures = [line for line in checks if line.startswith("✗")]

    print("Membership UI Verification")
    print("=" * 24)
    for line in checks:
        print(line)

    print("\nMetrics")
    print(f"- checks_total: {len(checks)}")
    print(f"- checks_passed: {len(checks) - len(failures)}")
    print(f"- checks_failed: {len(failures)}")
    print(f"- membership_engine_setting: {settings.get('membership_engine', 'missing')}")
    print(f"- cluster_view_loc: {sum(1 for _ in cluster_view_text.splitlines()) if cluster_view_text else 0}")

    print("\nNext steps")
    if failures:
        print("- Resolve failed checks before shipping membership panel.")
        print("- Re-run: python -m scripts.verify_membership_ui")
        raise SystemExit(1)

    print("- Wiring checks passed.")
    print("- Run frontend tests: cd graph-explorer && npx vitest run src/AccountMembershipPanel.test.jsx src/ClusterView.integration.test.jsx")
    print("- For live validation, enable `settings.membership_engine = \"grf\"` and select a member in ClusterView.")


if __name__ == "__main__":
    main()
