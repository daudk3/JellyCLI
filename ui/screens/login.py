from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Static

from api.jellyfin import authenticate_jellyfin
from config import load_config, save_config
from ui.screens.library import LibraryScreen
from ui.screens.modals import ConfirmQuitScreen


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
