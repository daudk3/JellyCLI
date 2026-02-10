import json
import os
import shlex
import shutil
import socket
import subprocess
import time
import uuid
from urllib.parse import parse_qsl, quote_plus, urlencode, urlparse

from textual.widgets import Static

from api.jellyfin import (
    get_item_with_userdata,
    get_playback_info,
    report_playback_progress,
    report_playback_start,
    report_playback_stop,
)
from config import load_config
from utils.time import extract_resume_ticks, ticks_to_seconds


class PlaybackTracker:
    """
    Launch mpv with IPC enabled and periodically sync progress to Jellyfin.
    Timers are attached to the provided screen (LibraryScreen or MediaScreen).
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
        self._start_monotonic = None
        self._stderr_pipe = None
        self._using_flatpak = False
        self._ipc_available = False

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

    def _consume_stderr(self) -> str:
        """Return buffered stderr output (used to surface immediate mpv failures)."""
        pipe = self._stderr_pipe
        self._stderr_pipe = None
        if not pipe:
            return ""
        try:
            data = pipe.read()
        except Exception:
            data = b""
        try:
            pipe.close()
        except Exception:
            pass
        return (data or b"").decode("utf-8", "ignore").strip()

    def _wait_for_mpv_ready(self, timeout: float = 5.0) -> bool:
        """Wait until the mpv IPC socket accepts a connection or the process exits.
        Returns True if IPC is connectable within timeout, False otherwise.
        """
        start = time.monotonic()
        while True:
            # Process died?
            if self.process and self.process.poll() is not None:
                return False
            # IPC socket ready?
            try:
                s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                s.settimeout(0.2)
                s.connect(self.ipc_path)
                s.close()
                return True
            except Exception:
                pass
            if (time.monotonic() - start) >= timeout:
                return False
            time.sleep(0.05)

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
        pb = {}
        ms = {}
        try:
            pb = get_playback_info(self.server_url, self.token, self.user_id, self.item_id)
            self.play_session_id = pb.get("PlaySessionId")
            ms = (pb.get("MediaSources") or [{}])[0]
            self.media_source_id = ms.get("Id")
        except Exception:
            # Fall back if server doesn't require playback info
            self.play_session_id = None
            self.media_source_id = None

        # Build stream URL: prefer server-provided DirectStreamUrl or TranscodingUrl
        media_url = None
        direct = (ms or {}).get("DirectStreamUrl") or (ms or {}).get("DirectStreamUrl")
        trans = (ms or {}).get("TranscodingUrl")
        if isinstance(direct, str) and direct:
            media_url = direct
        elif isinstance(trans, str) and trans:
            media_url = trans
        if media_url:
            if media_url.startswith("/"):
                media_url = f"{self.server_url.rstrip('/')}{media_url}"
            # Ensure required query params are present
            parsed = urlparse(media_url)
            q = dict(parse_qsl(parsed.query))
            modified = False
            if self.resume_ticks and self.resume_ticks > 0 and "StartTimeTicks" not in q:
                q["StartTimeTicks"] = str(self.resume_ticks)
                modified = True
            if self.media_source_id and "MediaSourceId" not in q:
                q["MediaSourceId"] = self.media_source_id
                modified = True
            if self.play_session_id and "PlaySessionId" not in q:
                q["PlaySessionId"] = self.play_session_id
                modified = True
            safe_token = quote_plus(self.token) if self.token else ""
            if safe_token:
                if "api_key" not in q:
                    q["api_key"] = safe_token
                    modified = True
                if "X-Emby-Token" not in q:
                    q["X-Emby-Token"] = safe_token
                    modified = True
            if modified:
                media_url = parsed._replace(query=urlencode(q)).geturl()
        else:
            # Fallback generic stream URL
            base = f"{self.server_url.rstrip('/')}/Videos/{self.item_id}/stream?Static=true"
            if self.media_source_id:
                base += f"&MediaSourceId={self.media_source_id}"
            if self.play_session_id:
                base += f"&PlaySessionId={self.play_session_id}"
            if self.resume_ticks and self.resume_ticks > 0:
                base += f"&StartTimeTicks={self.resume_ticks}"
            safe_token = quote_plus(self.token) if self.token else ""
            if safe_token:
                base += f"&X-Emby-Token={safe_token}&api_key={safe_token}"
            media_url = base

        # Launch mpv quietly with IPC
        # Use Jellyfin's standard header, and include legacy Emby header for compatibility.
        # mpv's string-list options accept multiple instances better than comma-separated values.
        header_args = [
            f"--http-header-fields=X-MediaBrowser-Token: {self.token}",
            f"--http-header-fields=X-Emby-Token: {self.token}",
        ]

        # Basic environment sanity for GUI output on Linux/Unix
        if os.name != "nt" and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
            toast = self._find_toast()
            if toast:
                toast.update("[red]No GUI display found (DISPLAY/WAYLAND_DISPLAY). mpv window may not open.[/]")
            # Continue anyway in case a nonstandard setup handles GUI differently

        # Resolve mpv command: config override -> native -> flatpak
        mpv_cmd: list[str] | None = None
        cfg = {}
        try:
            cfg = load_config() or {}
        except Exception:
            cfg = {}
        cmd_override = cfg.get("mpv_command")
        if isinstance(cmd_override, str) and cmd_override.strip():
            try:
                mpv_cmd = shlex.split(cmd_override)
            except Exception:
                mpv_cmd = [cmd_override]
        if not mpv_cmd:
            mpv_path = shutil.which("mpv")
            if mpv_path:
                mpv_cmd = [mpv_path]
        if not mpv_cmd:
            flatpak = shutil.which("flatpak")
            if flatpak:
                self._using_flatpak = True
                # Prefer to ensure the app exists; fall back to trying to run it
                try:
                    rc = subprocess.run(
                        [flatpak, "info", "io.mpv.Mpv"],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=1,
                    ).returncode
                    if rc == 0:
                        mpv_cmd = [flatpak, "run", "io.mpv.Mpv"]
                except Exception:
                    mpv_cmd = [flatpak, "run", "io.mpv.Mpv"]
        if not mpv_cmd:
            toast = self._find_toast()
            if toast:
                toast.update("[red]mpv not found; install mpv or Flatpak io.mpv.Mpv.[/]")
            return

        argv = [
            *mpv_cmd,
            "--really-quiet",
            "--no-terminal",
            "--player-operation-mode=pseudo-gui",
            "--force-window=yes",
            f"--input-ipc-server={self.ipc_path}",
        ]
        if self.resume_ticks and self.resume_ticks > 0:
            # insert after the ipc arg
            argv[6:6] = ["--hr-seek=yes", f"--start={start_seconds:.3f}"]

        # Avoid forcing VO/GPU context; rely on mpv defaults for maximum compatibility.

        # Add headers and any user-provided extra args
        argv += header_args
        try:
            extra = cfg.get("mpv_extra_args")
            if isinstance(extra, str):
                argv += shlex.split(extra)
            elif isinstance(extra, list):
                argv += [str(x) for x in extra]
        except Exception:
            pass

        # Finally add the media URL as the last argument
        argv.append(media_url)

        try:
            self.process = subprocess.Popen(
                argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            self._start_monotonic = time.monotonic()
            self._stderr_pipe = self.process.stderr
        except Exception as e:
            toast = self._find_toast()
            if toast:
                toast.update(f"[red]Failed to launch mpv: {e}[/]")
            return

        # Wait briefly until mpv has actually started (IPC up). If it fails quickly,
        # surface the error and do not tell the server we're playing.
        if not self._wait_for_mpv_ready(timeout=5.0):
            if self._using_flatpak:
                # Likely cannot access IPC socket across the Flatpak sandbox. Continue without IPC.
                self._ipc_available = False
                toast = self._find_toast()
                if toast:
                    toast.update("[yellow]Playing via Flatpak mpv (limited progress sync).[/]")
            else:
                err = self._consume_stderr()
                msg = "mpv failed to start."
                if err:
                    lines = [l for l in err.splitlines() if l.strip()]
                    if lines:
                        msg += f" Details: {lines[-1]}"
                toast = self._find_toast()
                if toast:
                    toast.update(f"[red]{msg}[/]")
                self.stop(final=False)
                return
        else:
            self._ipc_available = True

        # Notify start (best-effort) only after mpv is ready
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
            # If mpv exited right away, try to expose the error so Linux users can see why playback failed.
            try:
                started_at = getattr(self, "_start_monotonic", None)
                quick_exit = started_at is not None and (time.monotonic() - started_at) < 2.0
                if quick_exit:
                    err = self._consume_stderr()
                    if err:
                        last_line = [ln for ln in err.splitlines() if ln.strip()]
                        if last_line:
                            toast = self._find_toast()
                            if toast:
                                toast.update(f"[red]mpv exited: {last_line[-1]}[/]")
            except Exception:
                pass
            self.stop(final=True)
            return
        elif self._stderr_pipe and self._start_monotonic:
            if (time.monotonic() - self._start_monotonic) > 5:
                try:
                    self._stderr_pipe.close()
                except Exception:
                    pass
                self._stderr_pipe = None
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

        if self._stderr_pipe:
            try:
                self._stderr_pipe.close()
            except Exception:
                pass
            self._stderr_pipe = None
