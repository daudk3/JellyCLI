import time

from textual.binding import Binding
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Button, Label, ListItem, ListView, Static

from api.jellyfin import get_children
from models.media import format_label, open_in_browser_for_item
from playback.tracker import PlaybackTracker
from ui.screens.modals import ConfirmQuitScreen, MarkWatchStateScreen


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
