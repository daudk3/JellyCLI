import webbrowser


def format_label(item):
    """Build display label and append a dot if the item is fully watched."""

    def is_finished(it: dict) -> bool:
        # Only mark playable items (Movie/Episode) as finished.
        item_type = (it or {}).get("Type")
        if item_type not in ("Movie", "Episode"):
            return False
        ud = (it or {}).get("UserData") or {}
        # Jellyfin sets Played=True when fully watched; rely on that first.
        if ud.get("Played") is True:
            return True
        # Otherwise infer from progress >=95% of runtime.
        runtime = (it or {}).get("RunTimeTicks") or 0
        pos = ud.get("PlaybackPositionTicks") or ud.get("ResumePositionTicks") or 0
        try:
            runtime = int(runtime or 0)
            pos = int(pos or 0)
        except Exception:
            return False
        return runtime > 0 and pos >= int(runtime * 0.95)

    series = item.get("SeriesName")
    name = item.get("Name", "Unknown")
    s = item.get("ParentIndexNumber")
    e = item.get("IndexNumber")

    if series:
        base = f"{series} - {name} S{s:02d}E{e:02d}" if (s is not None and e is not None) else f"{series} - {name}"
    else:
        base = name

    if is_finished(item):
        return f"{base} [dim]•[/]"
    return base


def open_in_browser_for_item(server_url: str, item: dict):
    """
    Open the item's page in the Jellyfin web UI.
    - For folders (Series / Season / collections), opens the details page.
    - For episodes, attempts to auto-start playback by appending a play flag.
    """
    item_id = item.get("Id")
    if not item_id:
        return
    server_id = item.get("ServerId")
    # Base details route used by Jellyfin Web
    url = f"{server_url.rstrip('/')}/web/index.html#!/details?id={item_id}"
    params = []
    if server_id:
        params.append(f"serverId={server_id}")
    # Auto-play only for episodes (movies will open details page)
    if item.get("Type") == "Episode" and not item.get("IsFolder", False):
        params.append("play=true")
    if params:
        url = url + "&" + "&".join(params)
    try:
        webbrowser.open(url)
    except Exception:
        pass
