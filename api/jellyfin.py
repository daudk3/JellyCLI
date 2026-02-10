import re
from urllib.parse import parse_qs, quote, urljoin, urlparse

import requests


CLIENT_AUTH_HEADER = 'MediaBrowser Client="JellyCLI", Device="CLI", DeviceId="1234", Version="1.0"'
DEFAULT_DEVICE_NAME = "JellyCLI"
DEFAULT_APP_NAME = "JellyCLI"
DEFAULT_APP_VERSION = "1.0"


def authenticate_jellyfin(server_url: str, username: str, password: str):
    """Authenticate against Jellyfin and return (token, user_id)."""
    headers = {
        "X-Emby-Authorization": CLIENT_AUTH_HEADER,
        "Content-Type": "application/json",
    }
    payload = {"Username": username, "Pw": password}
    url = f"{server_url.rstrip('/')}/Users/AuthenticateByName"
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    return data["AccessToken"], data["User"]["Id"]


def authenticate_with_token(server_url: str, token: str):
    """
    Validate an existing Jellyfin access token and return (token, user_id, username_or_none).
    Raises on invalid token.
    """
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/Me"
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    user_id = data.get("Id")
    username = data.get("Name") or data.get("Username")
    if not user_id:
        raise ValueError("Token validation response missing user id")
    return token, user_id, username


def get_server_name(server_url: str, token: str | None = None) -> str | None:
    """Fetch server display name from Jellyfin."""
    auth_headers = {"X-MediaBrowser-Token": token} if token else {}
    endpoints = [
        ("/System/Info", auth_headers),
        ("/System/Info/Public", {}),
    ]
    for path, headers in endpoints:
        try:
            response = requests.get(f"{server_url.rstrip('/')}{path}", headers=headers, timeout=10)
            response.raise_for_status()
            data = _safe_json(response) or {}
            if isinstance(data, dict):
                name = data.get("ServerName") or data.get("Name")
                if isinstance(name, str) and name.strip():
                    return name.strip()
        except Exception:
            continue
    return None


def _safe_json(response):
    try:
        return response.json()
    except Exception:
        return None


def get_oid_configs(server_url: str):
    """Fetch OpenID provider configuration entries from the SSO plugin."""
    url = f"{server_url.rstrip('/')}/sso/OID/Get"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = _safe_json(response)
    return data if data is not None else {}


def _extract_provider_names(payload) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()

    def add(name):
        if not isinstance(name, str):
            return
        cleaned = name.strip()
        if not cleaned or cleaned in seen:
            return
        seen.add(cleaned)
        names.append(cleaned)

    def walk(node):
        if isinstance(node, str):
            add(node)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return

        lowered = {str(k).lower(): v for k, v in node.items()}
        maybe_name = lowered.get("providername") or lowered.get("provider") or lowered.get("name")
        enabled = lowered.get("enabled")
        if isinstance(maybe_name, str) and (enabled is None or bool(enabled)):
            add(maybe_name)

        for key, value in node.items():
            if isinstance(value, dict):
                value_keys = {str(k).lower() for k in value.keys()}
                if "oidendpoint" in value_keys or "oidclientid" in value_keys:
                    is_enabled = value.get("enabled", value.get("Enabled", True))
                    if bool(is_enabled):
                        add(str(key))
                walk(value)
            elif isinstance(value, list):
                walk(value)

    walk(payload)
    return names


def get_oid_provider_names(server_url: str) -> list[str]:
    """Return configured OpenID provider names from the SSO plugin."""
    return _extract_provider_names(get_oid_configs(server_url))


def get_oid_states(server_url: str):
    """Fetch active OpenID states from the SSO plugin."""
    url = f"{server_url.rstrip('/')}/sso/OID/States"
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    data = _safe_json(response)
    return data if data is not None else []


def extract_oid_states(payload) -> list[str]:
    """Best-effort extraction of state values from OID/States response payload."""
    states: list[str] = []
    seen: set[str] = set()

    def add(value):
        if not isinstance(value, str):
            return
        cleaned = value.strip()
        if len(cleaned) < 8 or cleaned in seen:
            return
        seen.add(cleaned)
        states.append(cleaned)

    def walk(node):
        if isinstance(node, str):
            add(node)
            return
        if isinstance(node, list):
            for item in node:
                walk(item)
            return
        if not isinstance(node, dict):
            return

        state_value = node.get("state", node.get("State"))
        add(state_value)

        for key, value in node.items():
            key_l = str(key).lower()
            if key_l not in {"state", "provider", "providername", "name", "enabled", "id", "key", "items", "data"}:
                add(str(key))
            if isinstance(value, (dict, list, str)):
                walk(value)

    walk(payload)
    return states


def get_oid_start_url(server_url: str, provider_name: str) -> str:
    provider = quote(provider_name.strip(), safe="")
    return f"{server_url.rstrip('/')}/sso/OID/start/{provider}"


def begin_oid_authorization(server_url: str, provider_name: str):
    """
    Initiate OIDC login and return (authorization_url, state_or_none).
    This lets non-browser clients track a concrete state value.
    """
    start_url = get_oid_start_url(server_url, provider_name)
    response = requests.get(start_url, allow_redirects=False, timeout=10)

    auth_url = None
    if response.status_code in (301, 302, 303, 307, 308):
        location = response.headers.get("Location")
        if location:
            auth_url = urljoin(f"{server_url.rstrip('/')}/", location)
    elif response.status_code == 200:
        # Best-effort parse in case a reverse proxy/plugin serves an HTML redirect page.
        body = response.text or ""
        match = re.search(r"""window\.location(?:\.href)?\s*=\s*["']([^"']+)["']""", body)
        if not match:
            match = re.search(
                r"""<meta[^>]+http-equiv=["']refresh["'][^>]+url=([^"'>\s]+)""",
                body,
                flags=re.IGNORECASE,
            )
        if match:
            auth_url = urljoin(f"{server_url.rstrip('/')}/", match.group(1))

    if not auth_url:
        # Fallback for unknown server behavior; browser can still start with the public endpoint.
        auth_url = start_url

    state = parse_qs(urlparse(auth_url).query).get("state", [None])[0]
    if isinstance(state, str):
        state = state.strip() or None
    else:
        state = None

    return auth_url, state


def authenticate_oid_state(
    server_url: str,
    provider_name: str,
    state: str,
    device_id: str,
    device_name: str = DEFAULT_DEVICE_NAME,
    app_name: str = DEFAULT_APP_NAME,
    app_version: str = DEFAULT_APP_VERSION,
):
    """
    Exchange an OIDC flow state for Jellyfin credentials via the SSO plugin.
    Returns (token, user_id, username_or_none).
    """
    provider = quote(provider_name.strip(), safe="")
    url = f"{server_url.rstrip('/')}/sso/OID/Auth/{provider}"
    headers = {
        "X-Emby-Authorization": CLIENT_AUTH_HEADER,
        "Content-Type": "application/json",
    }
    payload = {
        "deviceId": device_id,
        "deviceName": device_name,
        "appName": app_name,
        "appVersion": app_version,
        "data": state,
    }
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()

    token = data.get("AccessToken")
    user = data.get("User") or {}
    user_id = user.get("Id") or data.get("UserId")
    username = user.get("Name") or user.get("Username") or data.get("Username")

    if not token or not user_id:
        raise ValueError("SSO authentication response missing token or user id")
    return token, user_id, username


def get_libraries(server_url: str, token: str, user_id: str):
    """Return main user libraries (Movies, TV Shows, etc.)."""
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/{user_id}/Views"
    response = requests.get(url, headers=headers, timeout=10)
    response.raise_for_status()
    return response.json().get("Items", [])


def get_continue_watching(server_url: str, token: str, user_id: str):
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/{user_id}/Items/Resume"
    params = {"UserId": user_id, "Limit": 30, "Fields": "UserData"}
    return requests.get(url, headers=headers, params=params, timeout=10).json().get("Items", [])


def get_next_up(server_url: str, token: str, user_id: str):
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Shows/NextUp"
    params = {"UserId": user_id, "Limit": 30, "Fields": "UserData"}
    return requests.get(url, headers=headers, params=params, timeout=10).json().get("Items", [])


def get_items_in_library(server_url: str, token: str, user_id: str, library_id: str):
    """Get all items in a given library."""
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/{user_id}/Items"
    # Set Recursive to False to return only top-level items (shows, not episodes) for TV Shows library
    params = {"ParentId": library_id, "Recursive": False, "Limit": 300, "UserId": user_id, "Fields": "UserData"}
    response = requests.get(url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("Items", [])


def get_children(server_url: str, token: str, user_id: str, parent_id: str):
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/{user_id}/Items"
    params = {"ParentId": parent_id, "UserId": user_id, "Recursive": False, "Limit": 100, "Fields": "UserData"}
    response = requests.get(url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("Items", [])


def search_library(server_url: str, token: str, user_id: str, query: str):
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/{user_id}/Items"
    params = {
        "UserId": user_id,
        "SearchTerm": query,
        "IncludeItemTypes": "Movie,Series,Episode",
        "Recursive": True,
        "Limit": 100,
        "Fields": "UserData",
    }
    response = requests.get(url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("Items", [])


def mark_item_watched(server_url: str, token: str, user_id: str, item_id: str):
    """Mark a single item as watched."""
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/{user_id}/PlayedItems/{item_id}"
    resp = requests.post(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return True


def mark_item_unwatched(server_url: str, token: str, user_id: str, item_id: str):
    """Mark a single item as unwatched."""
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/{user_id}/PlayedItems/{item_id}"
    resp = requests.delete(url, headers=headers, timeout=10)
    if resp.status_code not in (200, 204):
        resp.raise_for_status()
    return True


def get_descendant_playables(server_url: str, token: str, user_id: str, parent_id: str):
    """Fetch all playable descendants (Movies, Episodes) under a folder (Series/Season)."""
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/{user_id}/Items"
    params = {
        "ParentId": parent_id,
        "UserId": user_id,
        "Recursive": True,
        "IncludeItemTypes": "Movie,Episode",
        "Fields": "UserData",
        "Limit": 500,
    }
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("Items", [])


def get_item_with_userdata(server_url: str, token: str, user_id: str, item_id: str) -> dict:
    """Fetch a single item including UserData so we can resume properly."""
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/{user_id}/Items/{item_id}?Fields=UserData"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()


def get_playback_info(server_url: str, token: str, user_id: str, item_id: str):
    """Request playback info to obtain PlaySessionId and MediaSourceId."""
    headers = {"X-MediaBrowser-Token": token, "Content-Type": "application/json"}
    url = f"{server_url.rstrip('/')}/Items/{item_id}/PlaybackInfo"
    payload = {"UserId": user_id, "AutoOpenLiveStream": False}
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    return resp.json()


def report_playback_start(server_url: str, token: str, info: dict):
    headers = {"X-MediaBrowser-Token": token, "Content-Type": "application/json"}
    url = f"{server_url.rstrip('/')}/Sessions/Playing"
    requests.post(url, headers=headers, json=info, timeout=10)


def report_playback_progress(server_url: str, token: str, info: dict):
    headers = {"X-MediaBrowser-Token": token, "Content-Type": "application/json"}
    url = f"{server_url.rstrip('/')}/Sessions/Playing/Progress"
    requests.post(url, headers=headers, json=info, timeout=10)


def report_playback_stop(server_url: str, token: str, info: dict):
    headers = {"X-MediaBrowser-Token": token, "Content-Type": "application/json"}
    url = f"{server_url.rstrip('/')}/Sessions/Playing/Stopped"
    requests.post(url, headers=headers, json=info, timeout=10)
