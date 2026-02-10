from textual.app import App
from textual.binding import Binding
from textual.widgets import Static

from api.jellyfin import authenticate_jellyfin
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
        username = config.get("username")
        password = config.get("password")
        if server_url and username and password:
            # Try automatic login
            try:
                token, uid = authenticate_jellyfin(server_url, username, password)
                self.push_screen(LibraryScreen(server_url, token, uid))
            except Exception:
                # If login fails, clear saved credentials and start over
                config.pop("password", None)
                save_config(config)
                self.push_screen(LoginScreen())
        elif server_url:
            self.push_screen(LoginScreen())
        else:
            self.push_screen(ServerScreen())
