import re
from urllib.parse import urlparse

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Static

from config import load_config, save_config
from ui.screens.modals import ConfirmQuitScreen


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
        if not re.match(r"^https?://", url):
            url = "http://" + url

        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            msg.update("[red]Invalid URL format. Please enter a valid server address (e.g. http://localhost:8096).[/]")
            return

        config = load_config()
        config["server_url"] = url.rstrip("/")
        save_config(config)
        self.app.config = config
        self.app.pop_screen()
        from ui.screens.login import LoginScreen

        self.app.push_screen(LoginScreen())

    def action_show_quit_menu(self):
        self.app.push_screen(ConfirmQuitScreen())
