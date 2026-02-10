import requests


def authenticate_jellyfin(server_url: str, username: str, password: str):
    """Authenticate against Jellyfin and return (token, user_id)."""
    headers = {
        "X-Emby-Authorization": 'MediaBrowser Client="JellyCLI", Device="CLI", DeviceId="1234", Version="1.0"',
        "Content-Type": "application/json",
    }
    payload = {"Username": username, "Pw": password}
    url = f"{server_url.rstrip('/')}/Users/AuthenticateByName"
    response = requests.post(url, json=payload, headers=headers, timeout=10)
    response.raise_for_status()
    data = response.json()
    return data["AccessToken"], data["User"]["Id"]


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
