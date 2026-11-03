"""Read-only source-backed supplement for the existing private Review dossier.

Offline read views are observations, not identity merges or archive eligibility.
Working judgments intentionally remain in the existing ego-scoped tag API.
"""
from __future__ import annotations

import json
from pathlib import Path


class JoinedIdentityError(ValueError):
    """A handle or expected ID cannot safely identify a single stored account."""


def _validate(payload):
    if not isinstance(payload, dict) or payload.get("kind") != "map-tpot-custody-pilot" or payload.get("visibility") != "private":
        raise ValueError("invalid private read-view envelope")
    dossiers = payload.get("dossiers")
    if not isinstance(dossiers, list):
        raise ValueError("missing dossier list")
    seen = set()
    for row in dossiers:
        account_id = row.get("accountId") if isinstance(row, dict) else None
        if not isinstance(account_id, str) or not account_id or account_id in seen:
            raise ValueError("invalid or duplicate stored account identity")
        seen.add(account_id)
        for field in ("websiteEvidence", "publicWorkResearch", "contactChecks", "unresolvedHandleMatches", "contactResearch"):
            values = row.get(field, [])
            if not isinstance(values, list) or any(not isinstance(item, dict) for item in values):
                raise ValueError("invalid stored evidence section")
        profiles = row.get("profiles")
        if not isinstance(profiles, list) or not profiles:
            raise ValueError("missing profile observations")
        for profile in profiles:
            if not isinstance(profile, dict) or not isinstance(profile.get("source"), str) or not isinstance(profile.get("record"), dict) or profile["record"].get("account_id") != account_id:
                raise ValueError("profile identity mismatch")
        for item in row.get("contactResearch", []):
            record = item.get("record") if isinstance(item, dict) else None
            if not isinstance(record, dict) or record.get("account_id") != account_id or not isinstance(record.get("routes"), list):
                raise ValueError("contact identity mismatch")
            for route in record["routes"]:
                if not isinstance(route, dict) or any(not isinstance(route.get(key), str) or not route[key] for key in ("type", "address", "source_url")):
                    raise ValueError("invalid source-backed contact")
    return payload


def _handles(row):
    return {str(profile["record"].get("username") or profile["record"].get("handle") or "").casefold()
            for profile in row["profiles"]}


def _view(row, created_at):
    profiles = []
    for item in row["profiles"]:
        source = item["record"]
        profiles.append({"source": item["source"], "username": source.get("username") or source.get("handle"),
                         "displayName": source.get("display_name") or source.get("name"),
                         "bio": source.get("bio") or source.get("description"), "location": source.get("location"),
                         "website": source.get("website"), "capturedAt": source.get("fetched_at") or source.get("captured_at")})
    contacts = [{**route, "sourceFile": Path(item.get("sourcePath", "")).name}
                for item in row.get("contactResearch", []) for route in item["record"]["routes"]]
    public_work = [{**item["artifact"], "sourceFile": Path(item.get("sourcePath", "")).name,
                    "caveats": item.get("caveats", [])}
                   for item in row.get("publicWorkResearch", []) if isinstance(item.get("artifact"), dict)]
    websites = []
    for site in row.get("websiteEvidence", []):
        try:
            links = json.loads(site.get("signal_links_json") or "[]")
            if not isinstance(links, list) or any(not isinstance(link, str) for link in links):
                raise ValueError("invalid website links")
            link_status = "available"
        except (ValueError, TypeError):
            links, link_status = [], "unavailable"
        websites.append({"url": site.get("resolved_url") or site.get("source_url"), "title": site.get("title"),
                         "excerpt": site.get("text_excerpt"), "capturedAt": site.get("fetched_at"),
                         "error": site.get("error"), "links": links, "linkStatus": link_status})
    return {"status": "available", "accountId": row["accountId"], "capturedAt": created_at,
            "profiles": profiles, "websites": websites, "publicWork": public_work, "contacts": contacts,
            "contactChecks": [item["record"] for item in row.get("contactChecks", [])],
            "unresolvedHandleMatches": row.get("unresolvedHandleMatches", []),
            "coverage": row.get("coverage", {}),
            "boundary": "Stored observations and research notes, not calibrated membership or current archive eligibility."}


def joined_preview(path, *, handle, account_id=None):
    """Read a configured local view; never fetch, mutate, log private data or merge."""
    if not path:
        return {"status": "not_configured"}
    try:
        source = Path(path)
        if source.stat().st_size > 8 * 1024 * 1024 or source.stat().st_mode & 0o077:
            raise ValueError("read view must be private and bounded")
        payload = _validate(json.loads(source.read_bytes()))
    except (OSError, ValueError, TypeError):
        return {"status": "unavailable", "message": "Stored joined evidence is unavailable; the archive preview remains independent."}
    handle = str(handle).strip().lstrip("@").casefold()
    matches = [row for row in payload["dossiers"] if handle in _handles(row)]
    if account_id:
        matches = [row for row in matches if row["accountId"] == account_id]
        if not matches and any(row["accountId"] == account_id for row in payload["dossiers"]):
            raise JoinedIdentityError("requested account ID and handle disagree")
    if len(matches) > 1:
        raise JoinedIdentityError("handle resolves to multiple stored account IDs; select an exact ID")
    if not matches:
        return {"status": "not_found"}
    row = matches[0]
    view = _view(row, payload.get("createdAt"))
    profile = next((item for item in view["profiles"] if str(item.get("username") or "").casefold() == handle), view["profiles"][0])
    return {**view, "account": {"accountId": row["accountId"], "username": profile["username"],
                               "displayName": profile["displayName"], "bio": profile["bio"],
                               "location": profile["location"], "website": profile["website"],
                               "fetchedAt": profile["capturedAt"]}}


def supplement_for_account(preview, account_id):
    """Keep cached evidence from ever binding to the wrong archive identity."""
    if preview.get("status") == "available" and preview["accountId"] != account_id:
        raise JoinedIdentityError("stored evidence and archive account ID disagree")
    return {key: value for key, value in preview.items() if key != "account"}
