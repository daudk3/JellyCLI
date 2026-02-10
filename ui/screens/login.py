import threading
import time
import uuid
import webbrowser

from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Button, Input, Static

from api.jellyfin import (
    begin_oid_authorization,
    authenticate_jellyfin,
    authenticate_oid_state,
    extract_oid_states,
    get_oid_provider_names,
    get_oid_start_url,
    get_oid_states,
)
from config import load_config, save_config
from ui.screens.library import LibraryScreen
from ui.screens.modals import ConfirmQuitScreen


class LoginScreen(Screen):
    BINDINGS = [Binding("escape", "show_quit_menu", "Quit")]

    OIDC_TIMEOUT_SECONDS = 180
    OIDC_POLL_SECONDS = 0.25

    def __init__(self):
        super().__init__()
        self._sso_in_progress = False

    def compose(self):
        yield Vertical(
            Static("[b]Sign in to Jellyfin[/b]", id="title"),
            Input(placeholder="Username", id="username"),
            Input(placeholder="Password", password=True, id="password"),
            Button("Sign In", id="submit"),
            Static("[dim]or[/]", id="sso-divider"),
            Input(placeholder="OIDC provider (default: authelia)", id="oid-provider"),
            Button("Login with SSO", id="submit-oid"),
            Static("", id="message"),
            id="login-container",
        )

    def on_mount(self):
        self.query_one("#username", Input).focus()
        provider = load_config().get("oid_provider")
        if isinstance(provider, str) and provider.strip():
            self.query_one("#oid-provider", Input).value = provider.strip()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "submit":
            self._attempt_login()
        elif event.button.id == "submit-oid":
            self._attempt_oidc_login()

    def on_input_submitted(self, event: Input.Submitted):
        if event.input.id == "username":
            self.query_one("#password", Input).focus()
        elif event.input.id == "password":
            self._attempt_login()
        elif event.input.id == "oid-provider":
            self._attempt_oidc_login()

    def _set_message(self, content: str):
        self.query_one("#message", Static).update(content)

    def _set_controls_disabled(self, disabled: bool):
        self.query_one("#username", Input).disabled = disabled
        self.query_one("#password", Input).disabled = disabled
        self.query_one("#oid-provider", Input).disabled = disabled
        self.query_one("#submit", Button).disabled = disabled
        self.query_one("#submit-oid", Button).disabled = disabled

    def _attempt_login(self):
        if self._sso_in_progress:
            self._set_message("[yellow]SSO is in progress. Please wait or retry when it finishes.[/]")
            return

        user = self.query_one("#username", Input).value.strip()
        pw = self.query_one("#password", Input).value
        config = load_config()
        server_url = config.get("server_url")
        if not server_url:
            self._set_message("[yellow]Server URL missing. Please restart app.[/]")
            return
        if not user or not pw:
            self._set_message("[yellow]Please enter both username and password.[/]")
            return

        try:
            token, uid = authenticate_jellyfin(server_url, user, pw)
            self._set_message("[green]Authenticated![/]")
            config["username"] = user
            config["password"] = pw
            config["access_token"] = token
            config["user_id"] = uid
            save_config(config)
            self.app.config = config
            self.app.push_screen(LibraryScreen(server_url, token, uid))
        except Exception as e:
            self._set_message(f"[red]Login failed: {e}[/]")

    def _attempt_oidc_login(self):
        if self._sso_in_progress:
            self._set_message("[yellow]SSO is already in progress.[/]")
            return

        config = load_config()
        server_url = config.get("server_url")
        if not server_url:
            self._set_message("[yellow]Server URL missing. Please restart app.[/]")
            return

        provider_value = self.query_one("#oid-provider", Input).value.strip() or config.get("oid_provider", "authelia")

        self._sso_in_progress = True
        self._set_controls_disabled(True)
        self._set_message("[yellow]Starting OIDC SSO flow...[/]")

        threading.Thread(
            target=self._oidc_login_worker,
            args=(server_url, provider_value),
            daemon=True,
        ).start()

    def _resolve_oidc_provider(self, server_url: str, provider_value: str) -> str:
        if provider_value:
            return provider_value

        providers = get_oid_provider_names(server_url)
        if not providers:
            raise RuntimeError("No OIDC providers were found on this server.")
        if len(providers) > 1:
            names = ", ".join(providers)
            raise RuntimeError(f"Multiple OIDC providers are configured ({names}). Enter a provider name first.")
        return providers[0]

    def _oidc_login_worker(self, server_url: str, provider_value: str):
        try:
            provider = self._resolve_oidc_provider(server_url, provider_value)

            baseline_states = set()
            try:
                baseline_states = set(extract_oid_states(get_oid_states(server_url)))
            except Exception:
                baseline_states = set()
            state = None
            try:
                auth_url, state = begin_oid_authorization(server_url, provider)
            except Exception:
                # Fallback: still launch browser start URL and use state discovery mode.
                auth_url = get_oid_start_url(server_url, provider)
                state = None
            browser_opened = False
            try:
                browser_opened = bool(webbrowser.open(auth_url))
            except Exception:
                browser_opened = False

            if browser_opened:
                self.app.call_from_thread(
                    self._set_message,
                    f"[yellow]Complete SSO in your browser for provider [b]{provider}[/b]...[/]",
                )
            else:
                self.app.call_from_thread(
                    self._set_message,
                    f"[yellow]Open this URL to continue SSO: {auth_url}[/]",
                )

            device_id = uuid.uuid4().hex
            deadline = time.time() + self.OIDC_TIMEOUT_SECONDS
            last_error = None

            if state:
                # Primary path: poll the exact OIDC state generated for this flow.
                while time.time() < deadline:
                    try:
                        token, uid, username = authenticate_oid_state(
                            server_url=server_url,
                            provider_name=provider,
                            state=state,
                            device_id=device_id,
                        )
                        self.app.call_from_thread(
                            self._oidc_login_success,
                            server_url,
                            token,
                            uid,
                            username,
                            provider,
                        )
                        return
                    except Exception as e:
                        last_error = e
                    time.sleep(self.OIDC_POLL_SECONDS)

            # Fallback path for servers that do not expose state on redirect URL.
            while time.time() < deadline:
                try:
                    states_payload = get_oid_states(server_url)
                    states = extract_oid_states(states_payload)
                except Exception as e:
                    last_error = e
                    time.sleep(self.OIDC_POLL_SECONDS)
                    continue

                candidate_states = [s for s in states if s not in baseline_states]
                if not candidate_states:
                    candidate_states = states

                for candidate_state in candidate_states:
                    try:
                        token, uid, username = authenticate_oid_state(
                            server_url=server_url,
                            provider_name=provider,
                            state=candidate_state,
                            device_id=device_id,
                        )
                        self.app.call_from_thread(
                            self._oidc_login_success,
                            server_url,
                            token,
                            uid,
                            username,
                            provider,
                        )
                        return
                    except Exception as e:
                        last_error = e

                time.sleep(self.OIDC_POLL_SECONDS)

            if last_error:
                self.app.call_from_thread(
                    self._oidc_login_failed,
                    f"OIDC login timed out. Last error: {last_error}",
                )
            else:
                self.app.call_from_thread(
                    self._oidc_login_failed,
                    "OIDC login timed out. Complete authentication in browser and try again.",
                )
        except Exception as e:
            self.app.call_from_thread(self._oidc_login_failed, str(e))

    def _oidc_login_success(self, server_url: str, token: str, uid: str, username: str | None, provider: str):
        config = load_config()
        if isinstance(username, str) and username.strip():
            config["username"] = username.strip()
        config.pop("password", None)
        config["oid_provider"] = provider
        config["access_token"] = token
        config["user_id"] = uid
        save_config(config)
        self.app.config = config

        self._sso_in_progress = False
        self._set_controls_disabled(False)
        self._set_message("[green]Authenticated with SSO![/]")
        self.app.push_screen(LibraryScreen(server_url, token, uid))

    def _oidc_login_failed(self, message: str):
        self._sso_in_progress = False
        self._set_controls_disabled(False)
        self._set_message(f"[red]OIDC login failed: {message}[/]")

    def action_show_quit_menu(self):
        self.app.push_screen(ConfirmQuitScreen())
