from textual.app import App
from textual.binding import Binding
from textual.widgets import Static

from api.jellyfin import authenticate_jellyfin, authenticate_with_token
from config import load_config, save_config
from ui.css import APP_CSS
from ui.screens.library import LibraryScreen
from ui.screens.login import LoginScreen
from ui.screens.server import ServerScreen


class JellyCLIApp(App):
    """Modern Jellyfin CLI App with refined look."""

    CSS = APP_CSS

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
        access_token = config.get("access_token")
        username = config.get("username")
        password = config.get("password")
        if not server_url:
            self.push_screen(ServerScreen())
            return

        if isinstance(access_token, str) and access_token.strip():
            try:
                token, uid, resolved_username = authenticate_with_token(server_url, access_token.strip())
                config["access_token"] = token
                config["user_id"] = uid
                if isinstance(resolved_username, str) and resolved_username.strip():
                    config["username"] = resolved_username.strip()
                save_config(config)
                self.config = config
                self.push_screen(LibraryScreen(server_url, token, uid))
                return
            except Exception:
                # Token is no longer valid. Force reauthentication.
                config.pop("access_token", None)
                config.pop("user_id", None)
                config.pop("password", None)
                save_config(config)
                self.config = config
                self.push_screen(LoginScreen())
                return

        if server_url and username and password:
            # Try automatic login from saved credentials.
            try:
                token, uid = authenticate_jellyfin(server_url, username, password)
                config["access_token"] = token
                config["user_id"] = uid
                save_config(config)
                self.config = config
                self.push_screen(LibraryScreen(server_url, token, uid))
            except Exception:
                # If login fails, clear saved credentials and start over
                config.pop("password", None)
                config.pop("access_token", None)
                config.pop("user_id", None)
                save_config(config)
                self.config = config
                self.push_screen(LoginScreen())
        elif server_url:
            self.push_screen(LoginScreen())
