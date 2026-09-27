# SmartCampus — AI-Assisted College Lost & Found

A Flask + SQLite college Lost & Found platform with TF-IDF/cosine-similarity matching, moderation, private verification, claims, notifications and a responsive subtle-colour UI.

## Run on Windows
```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python app.py
```
Open http://127.0.0.1:5000

Development admin: `admin@college.edu` / `Admin@123` (change before real deployment).

The ML output is a **Match Similarity Score**, not ownership probability. An administrator makes the final ownership decision.
