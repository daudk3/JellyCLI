import time
from datetime import datetime

from textual.binding import Binding
from textual.screen import Screen
from textual.timer import Timer
from textual.widgets import Input, Label, ListItem, ListView, Static

from api.jellyfin import (
    get_continue_watching,
    get_items_in_library,
    get_libraries,
    get_next_up,
    get_server_name,
    search_library,
)
from config import load_config
from models.media import format_label, open_in_browser_for_item
from playback.tracker import PlaybackTracker
from ui.screens.media import MediaScreen
from ui.screens.modals import ConfirmQuitScreen, MarkWatchStateScreen


class LibraryScreen(Screen):
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

    def _update_title(self):
        server_name = get_server_name(self.server_url, self.token)
        title = f"{server_name} • JellyCLI" if server_name else "JellyCLI Home"
        self.query_one("#title", Static).update(f"[b]{title}[/b]")

    def on_mount(self):
        self.app.home_screen = self
        self._update_title()
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

    def action_show_quit_menu(self):
        self.app.push_screen(ConfirmQuitScreen())

    def on_unmount(self):
        tracker = getattr(self, "_playback_tracker", None)
        if tracker:
            tracker.stop(final=False)
