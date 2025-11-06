# JellyCLI

A minimalistic CLI tool for browsing and playing Jellyfin media.

## Highlights

- Minimalistic CLI interface for Jellyfin.
- Keyboard navigation for media browsing.
- Playback synchronization with Jellyfin server.
- Configurable key bindings.
- Supports multiple media types.

## Setup

1. Clone the repository.
2. Install dependencies.
3. Configure your Jellyfin server credentials.
4. Run the tool.

## Configuration

```json
{
  "server": {
    "url": "http://your-jellyfin-server",
    "api_key": "your_api_key"
  },
  "playback": {
    "sync_playback": true
  },
  "key_bindings": {
    "play_pause": "space",
    "next": "n",
    "previous": "p",
    "quit": "q"
  }
}
```

## Key Bindings

- `space`: Play/Pause
- `n`: Next media
- `p`: Previous media
- `q`: Quit the application

## Playback Sync

JellyCLI synchronizes playback position with the Jellyfin server to allow seamless continuation across devices.

## License

MIT License.

# JellyCLI

A fast, keyboard‑friendly **Jellyfin** TUI written with [Textual], with **mpv** playback, resume/progress sync, and smart skipping of server‑defined segments (Intro/Outro/Recap/Preview).

> **Status:** personal project; works great for day‑to‑day use. Feedback and PRs welcome.

---

## Highlights

- **Home view** with **Continue Watching**, **Next Up**, and **Your Libraries**
- **TV flow**: TV Shows ➝ Seasons ➝ Episodes (no episode spam at the library root)
- **Playback in mpv** (detached, quiet). A small in‑app “Now playing” toast shows what started.
- **Resume from server** for partially watched items; **progress sync** while watching and on pause/quit
- **Auto‑skip segments** using Jellyfin’s segment data  
  (Intro Skipper / server segments: *Intro, Outro, Recap, Preview*)
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
  - Linux: your distro’s mpv package
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
~/Projects/JellyCLI/config.json
```

Fields:

```json
{
  "server_url": "http://your-jellyfin:8096",
  "username": "alice",
  "password": "••••••••",
  "show_greeting": true,
  "skip-segments": ["Intro", "Outro", "Recap", "Preview"]
}
```

- **server_url**: your Jellyfin base URL (http/https, with port if needed)
- **username / password**: your Jellyfin credentials
- **show_greeting**: toggles the greeting banner in the home view
- **skip-segments**: which server‑defined segments to skip globally  
  Leave **empty** (`[]`) to **disable** auto‑skip.

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

| Key                 | Action                                                                    |
|---------------------|---------------------------------------------------------------------------|
| **Enter**           | Open / follow / play selected item                                        |
| **Backspace**       | Go back                                                                   |
| **Esc**             | Open quit menu                                                            |
| **m**               | Toggle **watched / unwatched** (works in libraries, Continue Watching, Next Up) |
| **o**               | Open in **Jellyfin web** (folders open details, items start playback)    |
| **Ctrl+Shift+Q**    | Quit immediately                                                         |

---

## Resume & Progress Sync

- Starting from **Continue Watching** resumes from the server’s saved time.
- While playing in mpv, JellyCLI **periodically updates progress** and also on **pause/quit** events.
- When playback ends, the **home view refreshes**, so **Next Up** and **Continue Watching** reflect your latest state.

---

## Segment Skipping (server‑defined)

JellyCLI uses Jellyfin’s data to skip segments:

1. **Segments API** (`/Items/{id}/Segments`) — preferred
2. If unavailable, it falls back to **Chapters** (`GET /Users/{userId}/Items/{itemId}?Fields=Chapters`)
3. Segment names are normalized to the supported set: **Intro, Outro, Recap, Preview**

Control this with `skip-segments` in `config.json`:

- Example: `["Intro", "Outro"]` → skips only intros and outros
- Empty list `[]` → **disables** auto‑skip entirely

> For best results, install and enable the **Intro Skipper** plugin on your Jellyfin server and let it analyze your library.

---

## Watch State

- Press **m** on any show/season/episode/movie to mark **watched/unwatched**.
- **Unwatched items** are shown with a subtle dot indicator.
- Changing watch state immediately refreshes **Continue Watching** / **Next Up**.

---

## Open in Browser

Press **o**:

- **Folders** (show, season): opens that page in Jellyfin web
- **Items** (episode, movie): starts playback in the browser

---

## Packaging (optional)

If you want a single binary:

```bash
pip install pyinstaller
pyinstaller --onefile --name jellycli main.py
```

- Users will still need **mpv** available on their systems.
- On macOS gatekeeper, you may need to allow the binary to run.

---

## Troubleshooting

- **Playback doesn’t start**: ensure `mpv` is installed and on PATH.
- **Resume/skip doesn’t work**:
  - Confirm the item shows segments/markers in Jellyfin web.
  - Verify your `skip-segments` includes the parts you want to skip.
- **Auth fails**: try your credentials in Jellyfin web; check `server_url` (scheme/port).
- **Networking**: if Jellyfin runs on a different host/port, confirm local firewall rules.

---

## Contributing

Issues and PRs are welcome. Please describe your setup (OS, Python, mpv version, Jellyfin version) and steps to reproduce.

---

## License

See **LICENSE** in this repository.

---

[Textual]: https://textual.textualize.io/