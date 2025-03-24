# 📝 Overleaf Downloader

A fully automated tool to **download all historical versions** of Overleaf projects using **Docker** and **Selenium**.  
Supports multiple projects, handles Overleaf request limits, and can resume after interruption.

## 📦 Features

- Downloads **all history versions** of one or more Overleaf projects
- Automatically **resumes** from the last downloaded version
- Waits and retries if Overleaf rate-limits
- Persistent logging and progress tracking
- Works on **Linux**, **Windows**, **WSL**, **macOS**
- Supports `.env` or per-project cookies

## 🚀 Quick Start

### 1. Install Docker

- Linux: https://docs.docker.com/engine/install/
- Windows: https://docs.docker.com/desktop/install/windows-install/

### 2. Clone the Repository

```bash
git clone https://github.com/IllIgt/overleaf-downloader.git
cd overleaf-downloader
```

### 3. Create `.env` File (optional global cookie)

```env
COOKIE=eyJhbGciOi...
```

### 4. Configure `config.json`

```json
{
  "projects": [
    {
      "name": "project1",
      "url": "https://www.overleaf.com/project/..."
    },
    {
      "name": "project2",
      "url": "https://www.overleaf.com/project/..."
    }
  ],
  "cookie": "optional"
}
```

You can also add a `"cookie"` field to override the global one.

### 5. Run with Docker

```bash
docker compose up --build
```

ZIP files will be saved to `downloads/`, logs in `shared/logs/`, progress in `shared/progress.json`.

## 📂 Folder Structure

```
.
├── config.json             # Overleaf project list
├── .env                    # Optional global cookie
├── downloads/              # All downloaded versions (.zip)
├── shared/progress.json    # Stores current progress
├── shared/logs/output.log         # Runtime logs
├── main.py
├── Dockerfile
└── docker-compose.yml
```

## 🍪 How to Get Overleaf Cookie

1. Log in to https://overleaf.com
2. Open browser DevTools → Application → Cookies
3. Copy the value of the cookie named `overleaf_session2`
4. Use it in `.env` or in `config.json` under `"cookie"`

## 🛠 Recovery

If the script stops or crashes, you can restart it and it will continue from where it left off.  
If Overleaf starts blocking downloads, the script will pause and retry later with exponential backoff (up to 24 hours).

## 💻 Windows Notes

- Works best with Docker Desktop and WSL2
- Volumes will be auto-created at first run
- You can view logs inside `logs/output.log`

