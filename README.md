# GitHub Repo Catalog & Archiver

**Author:** ©Thorsten Bylicki | ©BYLICKILABS  
**Version:** 1.0.0

A cross-platform Python application with GUI for cataloging, searching, and archiving local GitHub repositories – now with multilingual UI (DE/EN) and integrated image preview from `assets/` folders.

---

## 📑 Table of Contents
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Image Preview](#image-preview)
- [Language Support](#language-support)
- [License](#license)

---

## Features
- **Scan & Index** local Git repositories (`.git`) into a local SQLite database.
- **Search** repositories by name or path.
- **Archive** selected repository to ZIP (with/without `.git`).
- **Open** repository in system file explorer.
- **Export** current view to CSV.
- **Multilingual** interface (German/English).
- **GitHub & Info Buttons**.
- **Image Preview** from `assets/`, `media/` folders (prefers 1280×640 images).

---

## Installation

```yarn
Requirements
- Python 3.8+
- `tkinter`
- `Pillow`
```

```bash
pip install pillow
```

---

## Usage
```yarn
python app.py
```

- **Scan Folder** → Recursively finds `.git` repositories and indexes them into `repos.db`.
- **Search** → Filters repositories live.
- **Archive Selected** → Saves repository as ZIP (optional `.git` inclusion).
- **Open Folder** → Opens repository in file explorer.
- **Export CSV** → Exports visible table to CSV.
- **Language Toggle** → Switch between DE/EN instantly.
- **GitHub Button** → Opens BYLICKILABS GitHub profile.

---

## Image Preview
- Searches in `assets/`, `media/`, `Assets/`, `Media/` directories of the repository.
- Prefers **exact 1280×640** images, otherwise best match to 2:1 aspect ratio.
- Displays image filename and original resolution.
- Without Pillow installed, displays an installation prompt.

---

## Language Support
- **English** (default)
- **German**
- Language switch is instant; all UI elements update live.

---

## Lizenz
©Thorsten Bylicki | ©BYLICKILABS
[LICENSE](LICENSE)
