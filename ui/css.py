APP_CSS = """
Screen {
    background: #0d1117;
    color: #e6edf3;
}
#title {
    text-align: center;
    padding: 0 1 0 1;
    margin-bottom: 0;
    border-bottom: solid #30363d;
    color: #58a6ff;
}
#toast {
    height: 1;
    text-align: center;
    color: #3fb950;
    margin: 1;
}
ListView {
    border: round #30363d;
    margin: 1 4;
    padding: 0 2;
}
ListItem {
    padding: 0 1;
}
.section-header {
    color: #79c0ff;
    background: #161b22;
    margin-top: 0;
    margin-bottom: 0;
}
.spacer {
    height: 1;
}
#greeting {
    margin: 0 4 1 4;
    text-align: left;
    color: #c9d1d9;
    background: transparent;
}
Input {
    background: #161b22;
    border: solid #30363d;
    color: #e6edf3;
    max-width: 40;
}
Button {
    background: #238636;
    color: white;
    border: none;
    padding: 1 2;
}
Button:hover {
    background: #2ea043;
}
#login-container, #server-url-container {
    layout: vertical;
    width: 100%;
    height: 100%;
    align: center middle;
    content-align: center middle;
    background: #0d1117;
}

#login-container > *, #server-url-container > * {
    width: 60%;
    max-width: 60;
    text-align: center;
    margin: 1;
}

#quit-dialog {
    layout: vertical;
    border: round #58a6ff;
    background: #161b22;
    width: 100%;
    height: 100%;
    padding: 1 4;
    align: center middle;
    content-align: center middle;
    text-align: center;
}
#quit-prompt {
    margin: 0 0 1 0;
}
#quit-buttons-container {
    layout: vertical;
    align: center middle;
    content-align: center middle;
    margin: 0;
    padding: 0;
}
#quit-buttons-top Button, #quit-buttons-bottom Button {
    width: 14;
    height: 3;
    margin: 0 1;
}
#quit-buttons-top {
    layout: horizontal;
    align: center middle;
    content-align: center middle;
    padding: 0;
    margin: 0 0 1 0;
}
#quit-buttons-bottom {
    layout: horizontal;
    align: center middle;
    content-align: center middle;
    padding: 0;
    margin: 1 0 0 0;
}
#quit-buttons-bottom #toggle-greeting {
    width: 32;
}
#mark-dialog {
    layout: vertical;
    border: round #58a6ff;
    background: #161b22;
    width: 90%;
    max-width: 120;
    min-height: 10;
    padding: 1 2;
    align: center middle;
    content-align: center middle;
    text-align: center;
}
#mark-title {
    margin: 0 0 1 0;
    text-align: center;
}
#mark-buttons {
    layout: horizontal;
    align: center middle;
    content-align: center middle;
}
#mark-buttons Button {
    width: 20;
    height: 3;
    margin: 0 1;
}
#search-label {
    margin: 0 4 0 4;
    color: #79c0ff;
    text-align: center;
}
#search-input {
    margin: 0 4 1 4;
    max-width: 40;
    width: 60%;
    align: center middle;
}
ModalScreen {
    align: center middle;
    content-align: center middle;
}
"""
