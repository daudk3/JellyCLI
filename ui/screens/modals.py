import os

from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from api.jellyfin import (
    get_descendant_playables,
    mark_item_unwatched,
    mark_item_watched,
)
from config import CONFIG_PATH, load_config, save_config


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
            from ui.screens.login import LoginScreen

            config = load_config()
            config.pop("username", None)
            config.pop("password", None)
            config.pop("access_token", None)
            config.pop("user_id", None)
            save_config(config)
            self.app.pop_screen()
            self.app.push_screen(LoginScreen())
        elif button_id == "reset":
            from ui.screens.server import ServerScreen

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
