# -*- coding: utf-8 -*-
"""Modern Textual-based Jellyfin CLI client with fixed library logic and refined styling."""

from textual.app import App, ComposeResult
from textual.containers import Vertical, Horizontal
from textual.widgets import Button, Input, Static, ListView, ListItem, Label
from textual.screen import Screen, ModalScreen
from textual.binding import Binding
from textual.reactive import reactive
from textual.timer import Timer
import requests
import subprocess
import shlex
import webbrowser
import json
import os
import time
import socket
import uuid
from datetime import datetime
import re
from urllib.parse import urlparse

# ────────────────────────────────────────────────────────────────────────────────
# Configuration and Config Management
# ────────────────────────────────────────────────────────────────────────────────
CONFIG_PATH = os.path.expanduser("~/Projects/JellyCLI/config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}

def save_config(config):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, "w") as f:
        json.dump(config, f, indent=4)


# ────────────────────────────────────────────────────────────────────────────────
# Jellyfin API functions
# ────────────────────────────────────────────────────────────────────────────────

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
        "Fields": "UserData"
    }
    response = requests.get(url, headers=headers, params=params, timeout=10)
    response.raise_for_status()
    return response.json().get("Items", [])

# ────────────────────────────────────────────────────────────────────────────────
# Mark Watched/Unwatched and Descendants Helper
# ────────────────────────────────────────────────────────────────────────────────

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
        "Limit": 500
    }
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("Items", [])

# ────────────────────────────────────────────────────────────────────────────────
# Resume Ticks Extraction Helpers
# ────────────────────────────────────────────────────────────────────────────────

def extract_resume_ticks(item: dict) -> int:
    """Best-effort extraction of resume position in ticks from an item."""
    try:
        ud = item.get("UserData") or {}
        ticks = ud.get("PlaybackPositionTicks") or ud.get("ResumePositionTicks") or 0
        return int(ticks or 0)
    except Exception:
        return 0

def ticks_to_seconds(ticks: int) -> float:
    try:
        return float(ticks) / 10_000_000.0
    except Exception:
        return 0.0

def get_item_with_userdata(server_url: str, token: str, user_id: str, item_id: str) -> dict:
    """Fetch a single item including UserData so we can resume properly."""
    headers = {"X-MediaBrowser-Token": token}
    url = f"{server_url.rstrip('/')}/Users/{user_id}/Items/{item_id}?Fields=UserData"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()

# ────────────────────────────────────────────────────────────────────────────────
# Playback Info/Progress Reporting
# ────────────────────────────────────────────────────────────────────────────────

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

class PlaybackTracker:
    """
    Launch mpv with IPC enabled and periodically sync progress to Jellyfin.
    Timers are attached to the provided 'screen' (LibraryScreen or MediaScreen).
    """
    def __init__(self, screen, server_url, token, user_id, item):
        self.screen = screen
        self.server_url = server_url
        self.token = token
        self.user_id = user_id
        self.item = item

        self.item_id = item["Id"]
        self.process = None
        self.ipc_path = f"/tmp/jellycli-mpv-{uuid.uuid4().hex}.sock"
        self.play_session_id = None
        self.media_source_id = None
        self._progress_timer = None
        self._watch_timer = None
        self._last_ticks = 0
        self.resume_ticks = 0
        self._last_pause_state = None

    def _ticks(self, seconds: float | None) -> int:
        if seconds is None:
            return 0
        return int(seconds * 10_000_000)

    def _mpv_get(self, prop: str):
        try:
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect(self.ipc_path)
            payload = {"command": ["get_property", prop]}
            s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            data = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                data += chunk
                if b"\n" in chunk:
                    break
            s.close()
            # mpv may return multiple lines; take the last JSON object line
            line = data.strip().split(b"\n")[-1]
            if not line:
                return None
            resp = json.loads(line.decode("utf-8"))
            return resp.get("data")
        except Exception:
            return None

    def start(self):
        # Determine resume position (ticks) from item or by fetching details
        resume_ticks = extract_resume_ticks(self.item)
        if not resume_ticks:
            try:
                details = get_item_with_userdata(self.server_url, self.token, self.user_id, self.item_id)
                resume_ticks = extract_resume_ticks(details)
            except Exception:
                resume_ticks = 0
        self.resume_ticks = resume_ticks
        start_seconds = ticks_to_seconds(self.resume_ticks)

        # Get playback info for session & media source
        try:
            pb = get_playback_info(self.server_url, self.token, self.user_id, self.item_id)
            self.play_session_id = pb.get("PlaySessionId")
            ms = (pb.get("MediaSources") or [{}])[0]
            self.media_source_id = ms.get("Id")
        except Exception:
            # Fall back if server doesn't require playback info
            self.play_session_id = None
            self.media_source_id = None

        # Build stream URL
        base = f"{self.server_url.rstrip('/')}/Videos/{self.item_id}/stream?static=true"
        if self.media_source_id:
            base += f"&MediaSourceId={self.media_source_id}"
        if self.play_session_id:
            base += f"&PlaySessionId={self.play_session_id}"
        if self.resume_ticks and self.resume_ticks > 0:
            base += f"&StartTimeTicks={self.resume_ticks}"
        media_url = base

        # Launch mpv quietly with IPC
        headers = f"--http-header-fields='X-Emby-Token: {self.token}'"
        if self.resume_ticks and self.resume_ticks > 0:
            start_arg = f"--start={start_seconds:.3f}"
            cmd = (
                f"mpv --really-quiet --no-terminal "
                f"--hr-seek=yes {start_arg} "
                f"--input-ipc-server={shlex.quote(self.ipc_path)} "
                f"{headers} {shlex.quote(media_url)}"
            )
        else:
            cmd = (
                f"mpv --really-quiet --no-terminal "
                f"--input-ipc-server={shlex.quote(self.ipc_path)} "
                f"{headers} {shlex.quote(media_url)}"
            )

        try:
            self.process = subprocess.Popen(
                cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        except Exception as e:
            toast = self._find_toast()
            if toast:
                toast.update(f"[red]Failed to launch mpv: {e}[/]")
            return

        # Notify start (best-effort)
        start_info = {
            "ItemId": self.item_id,
            "CanSeek": True,
            "IsPaused": False,
            "PlayMethod": "DirectStream",
            "PositionTicks": self.resume_ticks or 0,
        }
        if self.media_source_id:
            start_info["MediaSourceId"] = self.media_source_id
        if self.play_session_id:
            start_info["PlaySessionId"] = self.play_session_id
        try:
            report_playback_start(self.server_url, self.token, start_info)
        except Exception:
            pass

        # Track pause state
        self._last_pause_state = False

        # Start timers
        self._progress_timer = self.screen.set_interval(5, self._progress_tick)
        self._watch_timer = self.screen.set_interval(1, self._watch_process)

        # UI toast: show "Series - Title" when available
        name = self.item.get("Name", "Unknown")
        series = self.item.get("SeriesName")
        display_name = f"{series} - {name}" if series else name
        toast = self._find_toast()
        if toast:
            toast.update(f"[green]Now playing: [b]{display_name}[/b][/green]")

    def _find_toast(self):
        try:
            return self.screen.query_one("#toast", Static)
        except Exception:
            return None

    def _progress_tick(self):
        if not self.process or self.process.poll() is not None:
            return
        # read current playback position and pause state
        pos = self._mpv_get("time-pos")
        pause_state = self._mpv_get("pause")
        ticks = self._ticks(pos)
        if ticks:
            self._last_ticks = ticks
        payload = {
            "ItemId": self.item_id,
            "PositionTicks": self._last_ticks,
            "IsPaused": bool(pause_state) if isinstance(pause_state, bool) else False,
            "CanSeek": True,
            "PlayMethod": "DirectStream",
        }
        if self.media_source_id:
            payload["MediaSourceId"] = self.media_source_id
        if self.play_session_id:
            payload["PlaySessionId"] = self.play_session_id
        try:
            report_playback_progress(self.server_url, self.token, payload)
        except Exception:
            pass

    def _send_progress(self, pause_state: bool | None = None):
        """Send an immediate progress update (used on pause/resume)."""
        if not self.process:
            return
        pos = self._mpv_get("time-pos")
        ticks = self._ticks(pos)
        if ticks:
            self._last_ticks = ticks
        payload = {
            "ItemId": self.item_id,
            "PositionTicks": self._last_ticks,
            "IsPaused": bool(pause_state) if isinstance(pause_state, bool) else False,
            "CanSeek": True,
            "PlayMethod": "DirectStream",
        }
        if self.media_source_id:
            payload["MediaSourceId"] = self.media_source_id
        if self.play_session_id:
            payload["PlaySessionId"] = self.play_session_id
        try:
            report_playback_progress(self.server_url, self.token, payload)
        except Exception:
            pass

    def _watch_process(self):
        if not self.process:
            return
        # If the process has exited, stop and finalize
        if self.process.poll() is not None:
            self.stop(final=True)
            return
        # Poll pause state; if it changed, immediately push a progress update
        pause_state = self._mpv_get("pause")
        if isinstance(pause_state, bool):
            if self._last_pause_state is None:
                self._last_pause_state = pause_state
            elif pause_state != self._last_pause_state:
                # Pause/resume toggled -> save progress right away
                self._send_progress(pause_state)
                self._last_pause_state = pause_state

    def stop(self, final: bool = False):
        # Cancel timers
        if self._progress_timer:
            self._progress_timer.stop()
            self._progress_timer = None
        if self._watch_timer:
            self._watch_timer.stop()
            self._watch_timer = None

        # Final progress / stop
        if final:
            payload = {
                "ItemId": self.item_id,
                "PositionTicks": self._last_ticks,
            }
            if self.play_session_id:
                payload["PlaySessionId"] = self.play_session_id
            try:
                report_playback_stop(self.server_url, self.token, payload)
            except Exception:
                pass

        # Refresh home screen if present
        try:
            home = getattr(self.screen.app, "home_screen", None)
            if home:
                home.reload_home()
        except Exception:
            pass


# ────────────────────────────────────────────────────────────────────────────────
# Utility
# ────────────────────────────────────────────────────────────────────────────────

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
# ────────────────────────────────────────────────────────────────────────────────
# ModalScreen for Marking Watched/Unwatched
# ────────────────────────────────────────────────────────────────────────────────
class MarkWatchStateScreen(ModalScreen):
    """Modal to mark an item (or a folder's descendants) watched/unwatched."""
    def __init__(self, parent_screen, server_url, token, user_id, item):
        super().__init__()
        self.parent_screen = parent_screen
        self.server_url = server_url
        self.token = token
        self.user_id = user_id
        self.item = item

    def compose(self):
        title = self.item.get("Name", "Selected item")
        yield Vertical(
            Static(f"[b]Mark \"{title}\"[/b]", id="mark-title"),
            Horizontal(
                Button("Mark Watched", id="watched"),
                Button("Mark Unwatched", id="unwatched"),
                Button("Cancel", id="cancel"),
                id="mark-buttons",
            ),
            id="mark-dialog",
        )

    def _apply(self, watched: bool):
        item = self.item
        # Decide targets: single item or all playable descendants for folders
        targets = []
        if item.get("IsFolder"):
            try:
                targets = get_descendant_playables(self.server_url, self.token, self.user_id, item["Id"])
            except Exception:
                targets = []
        else:
            targets = [item]

        for it in targets:
            try:
                if watched:
                    mark_item_watched(self.server_url, self.token, self.user_id, it["Id"])
                    # reflect locally
                    ud = it.setdefault("UserData", {})
                    ud["Played"] = True
                    ud["PlayCount"] = max(1, int(ud.get("PlayCount", 0) or 0))
                else:
                    mark_item_unwatched(self.server_url, self.token, self.user_id, it["Id"])
                    ud = it.setdefault("UserData", {})
                    ud["Played"] = False
                    ud["PlayCount"] = 0
                    ud["PlaybackPositionTicks"] = 0
            except Exception:
                # Best-effort; continue with other items
                continue

        # Try to update the parent screen UI and home screen
        try:
            if hasattr(self.parent_screen, "apply_watch_state_local"):
                self.parent_screen.apply_watch_state_local(item, watched)
        except Exception:
            pass
        try:
            home = getattr(self.app, "home_screen", None)
            if home:
                home.reload_home()
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "watched":
            self._apply(True)
            self.app.pop_screen()
        elif event.button.id == "unwatched":
            self._apply(False)
            self.app.pop_screen()
        else:
            self.app.pop_screen()

# ────────────────────────────────────────────────────────────────────────────────
# Browser Helper
# ────────────────────────────────────────────────────────────────────────────────
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


# ────────────────────────────────────────────────────────────────────────────────
# Screens
# ────────────────────────────────────────────────────────────────────────────────

class ConfirmQuitScreen(ModalScreen):
    def compose(self):
        greeting_state = str(getattr(self.app, "show_greeting", True)).lower()
        yield Vertical(
            Static("[b]Are you sure you want to quit JellyCLI?[/b]", id="quit-prompt"),
            Vertical(
                Horizontal(
                    Button("Yes", id="yes"),
                    Button("No", id="no"),
                    id="quit-buttons-top",
                ),
                Horizontal(
                    Button("Logout", id="logout"),
                    Button("Reset App", id="reset"),
                    Button(f"Toggle Greeting ({greeting_state})", id="toggle-greeting"),
                    id="quit-buttons-bottom",
                ),
                id="quit-buttons-container",
            ),
            id="quit-dialog",
        )

    def on_button_pressed(self, event: Button.Pressed):
        button_id = event.button.id
        if button_id == "yes":
            self.app.exit("Goodbye 👋")
        elif button_id == "no":
            self.app.pop_screen()
        elif button_id == "logout":
            config = load_config()
            config.pop("username", None)
            config.pop("password", None)
            save_config(config)
            self.app.pop_screen()
            self.app.push_screen(LoginScreen())
        elif button_id == "reset":
            if os.path.exists(CONFIG_PATH):
                os.remove(CONFIG_PATH)
            self.app.pop_screen()
            self.app.push_screen(ServerScreen())
        elif button_id == "toggle-greeting":
            self.app.show_greeting = not getattr(self.app, "show_greeting", True)
            cfg = load_config()
            cfg["show_greeting"] = self.app.show_greeting
            save_config(cfg)
            # Reload the entire home screen so changes reflect immediately
            try:
                home = getattr(self.app, "home_screen", None)
                if home:
                    home.reload_home()
            except Exception:
                pass
            self.app.pop_screen()


class MediaScreen(Screen):
    """Shows contents within a selected library (Movies, TV Shows, etc.)."""
    BINDINGS = [
        Binding("backspace", "go_back", "Back"),
        Binding("escape", "show_quit_menu", "Quit"),
        Binding("o", "open_in_browser", "Open in browser"),
        Binding("enter", "activate", "Open/Play"),
        Binding("m", "mark_menu", "Mark watched/unwatched"),
    ]
    def apply_watch_state_local(self, item, watched: bool):
        """Update the current list label for the given item id."""
        try:
            target_id = item.get("Id")
            lv = self.query_one("#media-list", ListView)
            for li in lv.children:
                if hasattr(li, "item") and li.item.get("Id") == target_id:
                    ud = li.item.setdefault("UserData", {})
                    ud["Played"] = bool(watched)
                    ud["PlayCount"] = 1 if watched else 0
                    # refresh label text
                    label = li.query_one(Label)
                    label.update(format_label(li.item))
                    break
        except Exception:
            pass

    def action_mark_menu(self):
        item = getattr(self, "_selected_item", None)
        if not item:
            return
        self.app.push_screen(MarkWatchStateScreen(self, self.server_url, self.token, self.user_id, item))
    def action_activate(self):
        """Activate the current selection with the Enter key (open folder or play)."""
        item = getattr(self, "_selected_item", None)
        if not item:
            return
        self._activate_selection(item)

    def __init__(self, server_url, token, user_id, title, items):
        super().__init__()
        self.server_url, self.token, self.user_id, self.title, self.items = server_url, token, user_id, title, items
        self.toast_timer: Timer | None = None
        self._last_select_time = 0.0
        self._last_select_id = None
        self._selected_item = None

    def compose(self):
        yield Static(f"[b]{self.title}[/b]", id="title")
        yield Static("", id="toast")
        yield ListView(id="media-list")

    def on_mount(self):
        lv = self.query_one("#media-list", ListView)
        if not self.items:
            lv.append(ListItem(Label("[dim]No items found.[/]")))
            return
        for item in self.items:
            li = ListItem(Label(format_label(item)))
            li.item = item
            lv.append(li)

    def on_list_view_selected(self, event: ListView.Selected):
        item = getattr(event.item, "item", None)
        self._selected_item = item
        if not item:
            return

        now = time.monotonic()
        current_id = item.get("Id")
        if self._last_select_id == current_id and (now - self._last_select_time) <= 0.4:
            # Treat as double-click / activate
            self._activate_selection(item)
        else:
            # Single select: record selection but show no toast
            self._last_select_id = current_id
            self._last_select_time = now


    def on_list_view_highlighted(self, event: ListView.Highlighted):
        """Keep selection in sync when navigating with keyboard."""
        item = getattr(event.item, "item", None)
        self._selected_item = item

    def action_open_in_browser(self):
        """Open selected item in the Jellyfin web UI (episodes auto-play)."""
        item = getattr(self, "_selected_item", None)
        if not item:
            return
        open_in_browser_for_item(self.server_url, item)

    def _activate_selection(self, item):
        if item.get("IsFolder"):
            children = get_children(self.server_url, self.token, self.user_id, item["Id"])
            self.app.push_screen(MediaScreen(self.server_url, self.token, self.user_id, item["Name"], children))
        else:
            self._play_item(item)

    def _play_item(self, item):
        tracker = PlaybackTracker(self, self.server_url, self.token, self.user_id, item)
        setattr(self, "_playback_tracker", tracker)
        tracker.start()

    def _show_toast(self, msg: str, duration: float = 3):
        toast = self.query_one("#toast", Static)
        toast.update(f"[green]{msg}[/]")
        if self.toast_timer:
            self.toast_timer.stop()
        self.toast_timer = self.set_timer(duration, lambda: toast.update(""))

    def action_go_back(self):
        self.app.pop_screen()

    def action_show_quit_menu(self):
        self.app.push_screen(ConfirmQuitScreen())

    def on_unmount(self):
        tracker = getattr(self, "_playback_tracker", None)
        if tracker:
            tracker.stop(final=False)


class LibraryScreen(Screen):
    def update_greeting(self):
        """Update greeting banner visibility and text based on config and time of day."""
        config = load_config()
        username = config.get("username", "User")
        first_name = username.split()[0] if " " in username else username
        hour = datetime.now().hour
        if hour < 12:
            greeting = "Good morning"
        elif hour < 18:
            greeting = "Good afternoon"
        else:
            greeting = "Good evening"
        try:
            greeting_widget = self.query_one("#greeting", Static)
            show = getattr(self.app, "show_greeting", True)
            greeting_widget.display = show
            if show:
                greeting_widget.update(f"[b]{greeting}, {first_name}![/b]")
            else:
                greeting_widget.update("")
        except Exception:
            # If the widget isn't on this screen yet, ignore.
            pass
    """Home screen showing Continue Watching, Next Up, and Libraries."""
    BINDINGS = [
        Binding("escape", "show_quit_menu", "Quit"),
        Binding("o", "open_in_browser", "Open in browser"),
        Binding("enter", "activate", "Open/Play"),
        Binding("m", "mark_menu", "Mark watched/unwatched"),
    ]

    def action_activate(self):
        """Activate the currently highlighted/selected item or library with Enter."""
        item = getattr(self, "_selected_item", None)
        library = getattr(self, "_selected_library", None)
        self._activate_selection(item=item, library=library)

    def __init__(self, server_url, token, user_id):
        super().__init__()
        self.server_url, self.token, self.user_id = server_url, token, user_id
        self.toast_timer: Timer | None = None
        self._last_select_time = 0.0
        self._last_select_id = None
        self._selected_item = None
        self._selected_library = None

    def compose(self):
        yield Static("[b]JellyCLI Home[/b]", id="title")
        yield Static("", id="toast")
        yield Static("", id="greeting")
        yield Input(placeholder="Search all media...", id="search-input")
        yield ListView(id="home-list")

    def on_mount(self):
        self.app.home_screen = self
        lv = self.query_one("#home-list", ListView)
        # Greeting
        self.update_greeting()

        def add_section(title):
            lv.append(ListItem(Label(f"[b]{title}[/b]"), classes="section-header"))

        # Continue Watching
        add_section("Continue Watching")
        for item in get_continue_watching(self.server_url, self.token, self.user_id):
            li = ListItem(Label(format_label(item)))
            li.item = item
            lv.append(li)

        lv.append(ListItem(Label(""), classes="spacer"))  # Add space between sections

        # Next Up
        add_section("Next Up")
        for item in get_next_up(self.server_url, self.token, self.user_id):
            li = ListItem(Label(format_label(item)))
            li.item = item
            lv.append(li)

        lv.append(ListItem(Label(""), classes="spacer"))

        # Libraries
        add_section("Your Libraries")
        for lib in get_libraries(self.server_url, self.token, self.user_id):
            li = ListItem(Label(lib["Name"]))
            li.library = lib
            lv.append(li)

    def reload_home(self):
        lv = self.query_one("#home-list", ListView)
        lv.clear()
        # Refresh greeting as well
        self.update_greeting()

        def add_section(title):
            lv.append(ListItem(Label(f"[b]{title}[/b]"), classes="section-header"))

        # Continue Watching
        add_section("Continue Watching")
        for item in get_continue_watching(self.server_url, self.token, self.user_id):
            li = ListItem(Label(format_label(item)))
            li.item = item
            lv.append(li)

        lv.append(ListItem(Label(""), classes="spacer"))

        # Next Up
        add_section("Next Up")
        for item in get_next_up(self.server_url, self.token, self.user_id):
            li = ListItem(Label(format_label(item)))
            li.item = item
            lv.append(li)

        lv.append(ListItem(Label(""), classes="spacer"))

        # Libraries
        add_section("Your Libraries")
        for lib in get_libraries(self.server_url, self.token, self.user_id):
            li = ListItem(Label(lib["Name"]))
            li.library = lib
            lv.append(li)

    def on_list_view_selected(self, event: ListView.Selected):
        item = getattr(event.item, "item", None)
        library = getattr(event.item, "library", None)
        self._selected_item = item
        self._selected_library = library

        # Determine an ID for double-click comparison
        current_id = None
        if item:
            current_id = item.get("Id")
        elif library:
            current_id = library.get("Id")

        if current_id is None:
            return

        now = time.monotonic()
        if self._last_select_id == current_id and (now - self._last_select_time) <= 0.4:
            # Double click -> activate
            self._activate_selection(item=item, library=library)
        else:
            # Single select (mouse): record selection, no toast
            self._last_select_id = current_id
            self._last_select_time = now


    def on_list_view_highlighted(self, event: ListView.Highlighted):
        """Keep selection in sync for keyboard navigation."""
        self._selected_item = getattr(event.item, "item", None)
        self._selected_library = getattr(event.item, "library", None)

    def action_open_in_browser(self):
        """Open selected item in the Jellyfin web UI (episodes auto-play)."""
        item = getattr(self, "_selected_item", None)
        if item:
            open_in_browser_for_item(self.server_url, item)

    def _activate_selection(self, item=None, library=None):
        if item:
            self._play_item(item)
        elif library:
            items = get_items_in_library(self.server_url, self.token, self.user_id, library["Id"])
            self.app.push_screen(MediaScreen(self.server_url, self.token, self.user_id, library["Name"], items))

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "search-input":
            query = event.value.strip()
            if query:
                try:
                    results = search_library(self.server_url, self.token, self.user_id, query)
                    self.app.push_screen(MediaScreen(self.server_url, self.token, self.user_id, "Search Results", results))
                except Exception as e:
                    toast = self.query_one("#toast", Static)
                    toast.update(f"[red]Search failed: {e}[/]")
                    if self.toast_timer:
                        self.toast_timer.stop()
                    self.toast_timer = self.set_timer(3, lambda: toast.update(""))

    def _play_item(self, item):
        # Start playback with progress tracking
        tracker = PlaybackTracker(self, self.server_url, self.token, self.user_id, item)
        setattr(self, "_playback_tracker", tracker)
        tracker.start()

    def _show_toast(self, msg: str, duration: float = 3):
        toast = self.query_one("#toast", Static)
        toast.update(msg)
        if self.toast_timer:
            self.toast_timer.stop()
        self.toast_timer = self.set_timer(duration, lambda: toast.update(""))

    def action_show_quit_menu(self):
        self.app.push_screen(ConfirmQuitScreen())

    def on_unmount(self):
        tracker = getattr(self, "_playback_tracker", None)
        if tracker:
            tracker.stop(final=False)


# ────────────────────────────────────────────────────────────────────────────────
# ServerScreen: For entering server URL and saving to config
# ────────────────────────────────────────────────────────────────────────────────
class ServerScreen(Screen):
    BINDINGS = [Binding("escape", "show_quit_menu", "Quit")]
    def compose(self):
        yield Vertical(
            Static("[b]Enter Jellyfin Server URL[/b]", id="title"),
            Input(placeholder="e.g. http://localhost:8096", id="server-url"),
            Button("Next", id="server-next"),
            Static("", id="server-message"),
            id="login-container",
        )

    def on_mount(self):
        self.query_one("#server-url", Input).focus()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "server-next":
            self._save_server_url()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "server-url":
            self._save_server_url()

    def _save_server_url(self):
        url = self.query_one("#server-url", Input).value.strip()
        msg = self.query_one("#server-message", Static)

        if not url:
            msg.update("[yellow]Please enter the server URL.[/]")
            return

        # Prepend scheme if missing
        if not re.match(r'^https?://', url):
            url = "http://" + url

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            msg.update("[red]Invalid URL format. Please enter a valid server address (e.g. http://localhost:8096).[/]")
            return

        config = load_config()
        config["server_url"] = url.rstrip('/')
        save_config(config)
        self.app.config = config
        self.app.pop_screen()
        self.app.push_screen(LoginScreen())

    def action_show_quit_menu(self):
        self.app.push_screen(ConfirmQuitScreen())


# ────────────────────────────────────────────────────────────────────────────────
# LoginScreen: For entering username/password and saving to config
# ────────────────────────────────────────────────────────────────────────────────
class LoginScreen(Screen):
    BINDINGS = [Binding("escape", "show_quit_menu", "Quit")]
    def compose(self):
        yield Vertical(
            Static("[b]Sign in to Jellyfin[/b]", id="title"),
            Input(placeholder="Username", id="username"),
            Input(placeholder="Password", password=True, id="password"),
            Button("Sign In", id="submit"),
            Static("", id="message"),
            id="login-container",
        )

    def on_mount(self):
        self.query_one("#username", Input).focus()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "submit":
            self._attempt_login()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "username":
            self.query_one("#password", Input).focus()
        elif event.input.id == "password":
            self._attempt_login()

    def _attempt_login(self):
        user = self.query_one("#username", Input).value.strip()
        pw = self.query_one("#password", Input).value
        msg = self.query_one("#message", Static)
        config = load_config()
        server_url = config.get("server_url")
        if not server_url:
            msg.update("[yellow]Server URL missing. Please restart app.[/]")
            return
        if not user or not pw:
            msg.update("[yellow]Please enter both username and password.[/]")
            return
        try:
            token, uid = authenticate_jellyfin(server_url, user, pw)
            msg.update("[green]Authenticated![/]")
            config["username"] = user
            config["password"] = pw
            save_config(config)
            self.app.config = config
            self.app.push_screen(LibraryScreen(server_url, token, uid))
        except Exception as e:
            msg.update(f"[red]Login failed: {e}[/]")

    def action_show_quit_menu(self):
        self.app.push_screen(ConfirmQuitScreen())


# ────────────────────────────────────────────────────────────────────────────────
# Main Application
# ────────────────────────────────────────────────────────────────────────────────

class JellyCLIApp(App):
    """Modern Jellyfin CLI App with refined look."""

    CSS = """
    Screen {
        background: #0d1117;
        color: #e6edf3;
    }
    #title {
        text-align: center;
        padding: 0 1 0 1;
        margin-bottom: 0;
        border-bottom: solid #30363d;
        color: #58a6ff;
    }
    #toast {
        height: 1;
        text-align: center;
        color: #3fb950;
        margin: 1;
    }
    ListView {
        border: round #30363d;
        margin: 1 4;
        padding: 0 2;
    }
    ListItem {
        padding: 0 1;
    }
    .section-header {
        color: #79c0ff;
        background: #161b22;
        margin-top: 0;
        margin-bottom: 0;
    }
    .spacer {
        height: 1;
    }
    #greeting {
        margin: 0 4 1 4;
        text-align: left;
        color: #c9d1d9;
        background: transparent;
    }
    Input {
        background: #161b22;
        border: solid #30363d;
        color: #e6edf3;
        max-width: 40;
    }
    Button {
        background: #238636;
        color: white;
        border: none;
        padding: 1 2;
    }
    Button:hover {
        background: #2ea043;
    }
    #login-container, #server-url-container {
        layout: vertical;
        width: 100%;
        height: 100%;
        align: center middle;
        content-align: center middle;
        background: #0d1117;
    }

    #login-container > *, #server-url-container > * {
        width: 60%;
        max-width: 60;
        text-align: center;
        margin: 1;
    }

    #quit-dialog {
        layout: vertical;
        border: round #58a6ff;
        background: #161b22;
        width: 100%;
        height: 100%;
        padding: 1 4;
        align: center middle;
        content-align: center middle;
        text-align: center;
    }
    #quit-prompt {
        margin: 0 0 1 0;
    }
    #quit-buttons-container {
        layout: vertical;
        align: center middle;
        content-align: center middle;
        margin: 0;
        padding: 0;
    }
    #quit-buttons-top Button, #quit-buttons-bottom Button {
        width: 14;
        height: 3;
        margin: 0 1;
    }
    #quit-buttons-top {
        layout: horizontal;
        align: center middle;
        content-align: center middle;
        padding: 0;
        margin: 0 0 1 0;
    }
    #quit-buttons-bottom {
        layout: horizontal;
        align: center middle;
        content-align: center middle;
        padding: 0;
        margin: 1 0 0 0;
    }
    #quit-buttons-bottom #toggle-greeting {
        width: 32;
    }
    #mark-dialog {
        layout: vertical;
        border: round #58a6ff;
        background: #161b22;
        width: 90%;
        max-width: 120;
        min-height: 10;
        padding: 1 2;
        align: center middle;
        content-align: center middle;
        text-align: center;
    }
    #mark-title {
        margin: 0 0 1 0;
        text-align: center;
    }
    #mark-buttons {
        layout: horizontal;
        align: center middle;
        content-align: center middle;
    }
    #mark-buttons Button {
        width: 20;
        height: 3;
        margin: 0 1;
    }
    #search-label {
        margin: 0 4 0 4;
        color: #79c0ff;
        text-align: center;
    }
    #search-input {
        margin: 0 4 1 4;
        max-width: 40;
        width: 60%;
        align: center middle;
    }
    ModalScreen {
        align: center middle;
        content-align: center middle;
    }
    """

    BINDINGS = [Binding("ctrl+shift+q", "quit", "Quit"), Binding("escape", "show_quit_menu", "Quit")]

    def __init__(self):
        super().__init__()
        self.config = {}
        self.show_greeting = load_config().get("show_greeting", True)

    def compose(self):
        # No main screen UI; will push screens as needed
        yield Static("", id="placeholder")

    def on_mount(self):
        self.config = load_config()
        config = self.config
        server_url = config.get("server_url")
        username = config.get("username")
        password = config.get("password")
        if server_url and username and password:
            # Try automatic login
            try:
                token, uid = authenticate_jellyfin(server_url, username, password)
                self.push_screen(LibraryScreen(server_url, token, uid))
            except Exception as e:
                # If login fails, clear saved credentials and start over
                config.pop("password", None)
                save_config(config)
                self.push_screen(LoginScreen())
        elif server_url:
            self.push_screen(LoginScreen())
        else:
            self.push_screen(ServerScreen())


# ────────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    JellyCLIApp().run()
    def apply_watch_state_local(self, item, watched: bool):
        """Update the display label for the affected item in the home list."""
        try:
            target_id = item.get("Id")
            lv = self.query_one("#home-list", ListView)
            for li in lv.children:
                if hasattr(li, "item") and li.item.get("Id") == target_id:
                    ud = li.item.setdefault("UserData", {})
                    ud["Played"] = bool(watched)
                    ud["PlayCount"] = 1 if watched else 0
                    label = li.query_one(Label)
                    label.update(format_label(li.item))
                    break
        except Exception:
            pass

    def action_mark_menu(self):
        item = getattr(self, "_selected_item", None)
        if not item:
            return
        self.app.push_screen(MarkWatchStateScreen(self, self.server_url, self.token, self.user_id, item))