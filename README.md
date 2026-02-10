# JellyCLI

A fast, keyboard‑friendly TUI **Jellyfin** client written with [Textual], with **mpv** playback, and resume/progress sync.

> **Status:** personal project; works great for day‑to‑day use. Feedback and PRs welcome.

---

## Highlights

- **Home view** with **Continue Watching**, **Next Up**, and **Your Libraries**
- **TV flow**: TV Shows ➝ Seasons ➝ Episodes (no episode spam at the library root)
- **Playback in mpv** (detached, quiet). A small in‑app “Now playing” toast shows what started.
- **Resume from server** for partially watched items; **progress sync** while watching and on pause/quit
- **OIDC SSO login** through your browser (via Jellyfin SSO plugin), then back into the TUI session
- **Quick actions**:
  - **Enter**: open/follow/play (single press)
  - **Backspace**: go back
  - **Esc**: quit menu (modal)
  - **m**: mark **watched / unwatched** (works in libraries, Continue Watching, and Next Up)
  - **o**: open the selected item in the **Jellyfin web UI** (folders open to details; episodes/movies begin browser playback)
- **Global search** across Movies **and** TV Shows (results grouped by title type first, then episodes)
- **Greeting** (“Good morning/afternoon/evening, &lt;name&gt;”) with a toggle in the quit menu
- **Logout** and **Reset app** (clears config and returns to the server URL screen)

---

## System Architecture

![System Architecture Diagram](assets/arch-diagram.png)

---

## Requirements

- **Python 3.10+**
- **Jellyfin server (version 10.10.7+)** with the [jellyfin-plugin-sso](https://github.com/9p4/jellyfin-plugin-sso) plugin installed (for OIDC SSO)
- At least one **OIDC provider** configured and enabled in the SSO plugin (if using SSO login)
- **mpv** available on your `PATH`
  - macOS (Homebrew): `brew install mpv`
  - Linux: your distro’s mpv package (use Flatpak if you have issues with your distro's mpv, JellyCLI will automatically detect it)
  - Windows: mpv build + add folder to PATH
- Python deps:
  - `textual` (TUI)
  - `requests` (HTTP)

Install deps:

```bash
pip install textual requests
```

---

## Configuration

JellyCLI loads a simple JSON config at:

```
./config.json
```

Fields:

```json
{
  "server_url": "http://your-jellyfin:8096",
  "username": "alice",
  "password": "••••••••",
  "oid_provider": "authelia",
  "show_greeting": true,
}
```

- **server_url**: your Jellyfin base URL (http/https, with port if needed)
- **username / password**: your Jellyfin credentials (used for password login)
- **oid_provider**: OIDC provider name used for SSO login (default: `authelia`)
- **show_greeting**: toggles the greeting banner in the home view

If your Jellyfin SSO plugin uses a different OIDC provider name, set `oid_provider` in `config.json` to that exact provider name before using **Login with SSO (OIDC)**.

> **First run / missing config**  
> If `config.json` is missing or incomplete, JellyCLI will guide you through:
> 1) **Server URL** ➝ 2) **Sign in with Username/Password or Login with SSO (OIDC)**  
> Your entries are saved back to `config.json`.

> **Security note**  
> Credentials are stored **in plain text** for convenience. If that’s not acceptable for your environment, prefer a machine account or adjust the storage to your needs.

---

## Run

From the project root:

```bash
python main.py
```

- mpv is launched detached and quiet (no terminal spam).
- A toast inside the TUI shows: `Now playing: <Series – Title – SxxExx>` or movie title.

---

## Using the UI

### Login
- **Sign In**: standard Jellyfin username/password auth
- **Login with SSO (OIDC)**:
  - Uses `oid_provider` from `config.json` by default (`authelia`)
  - Opens your browser to complete the OIDC flow
  - Returns to JellyCLI when authentication completes successfully

### Home
- **Greeting** (toggle in quit menu)
- **Search** (full‑width bar above the home content)
- **Continue Watching**: picks up from the saved position
- **Next Up**: the next episode per series
- **Your Libraries**: Movies, TV Shows, etc.

### TV flow
- Select **TV Shows** ➝ **Seasons** ➝ **Episodes**
- Episodes display as: `Series – Episode Title SxxExx`

### Movies
- Movies are listed by title; Enter plays immediately.

### Key bindings

| Key              | Action                                                                          |
| ---------------- | ------------------------------------------------------------------------------- |
| **Enter**        | Open / follow / play selected item                                              |
| **Backspace**    | Go back                                                                         |
| **Esc**          | Open quit menu                                                                  |
| **m**            | Toggle **watched / unwatched** (works in libraries, Continue Watching, Next Up) |
| **o**            | Open in **Jellyfin web** (folders open details, items start playback)           |
| **Ctrl+Shift+Q** | Quit immediately                                                                |

---

## Troubleshooting

- **Playback doesn’t start**: ensure `mpv` is installed and on PATH.
	- If you are using Linux, I highly recommend installing the Flatpak version of `mpv`
- **OIDC SSO login doesn't complete in the TUI**:
	- Confirm the Jellyfin SSO plugin is installed and enabled.
	- Confirm your `oid_provider` value matches the configured provider name exactly.
	- Confirm your reverse proxy/server setup allows the `/sso/OID/*` plugin routes.

---

## Contributing

Issues and PRs are welcome. Please describe your setup (OS, Python, mpv version, Jellyfin version) and steps to reproduce.

---

## License

The source code for JellyCLI is available under the GPLv3 license. See **LICENSE** in this repository.

---

[Textual]: https://textual.textualize.io/
