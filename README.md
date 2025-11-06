# JellyCLI

A fast, cross-platform, keyboard‑friendly **Jellyfin** TUI written with [Textual], with **mpv** playback, and resume/progress sync.

> **Status:** personal project; works great for day‑to‑day use. Feedback and PRs welcome.

---

## Highlights

- **Home view** with **Continue Watching**, **Next Up**, and **Your Libraries**
- **TV flow**: TV Shows ➝ Seasons ➝ Episodes (no episode spam at the library root)
- **Playback in mpv** (detached, quiet). A small in‑app “Now playing” toast shows what started.
- **Resume from server** for partially watched items; **progress sync** while watching and on pause/quit
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

## Requirements

- **Python 3.10+**
- **mpv** available on your `PATH`
  - macOS (Homebrew): `brew install mpv`
  - Linux: your distro’s mpv package (use Flatpak if you have issues with your distro's mpv, JellyCLI will automatically detect it)
  - Windows: mpv build + add folder to PATH
- Python deps:
  - `textual` (TUI)
  - `requests` (HTTP)

Install deps:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
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
  "show_greeting": true,
}
```

- **server_url**: your Jellyfin base URL (http/https, with port if needed)
- **username / password**: your Jellyfin credentials
- **show_greeting**: toggles the greeting banner in the home view

> **First run / missing config**  
> If `config.json` is missing or incomplete, JellyCLI will guide you through:
> 1) **Server URL** ➝ 2) **Username & Password**  
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

---

## Contributing

Issues and PRs are welcome. Please describe your setup (OS, Python, mpv version, Jellyfin version) and steps to reproduce.

---

## License

See **LICENSE** in this repository.

---

[Textual]: https://textual.textualize.io/