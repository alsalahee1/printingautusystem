# Deploying PrintSys

PrintSys is a single FastAPI app. It runs anywhere Python 3.10+ runs — a shop
PC, an office server, or a small cloud VM. SQLite needs no setup; PostgreSQL or
SQL Server is a drop-in for multi-user use.

## 1. Quick run (single PC)

```bash
pip install -r requirements.txt
python -m app.seed          # optional sample data
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://<pc-ip>:8000` from any device on the same network and log in as
**admin / admin**. Change the password immediately under *Users*.

## 2. Environment variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `PRINTSYS_DB_URL` | Database connection string | `sqlite:///./printsys.db` |
| `PRINTSYS_SECRET` | Signs session cookies — **set a long random value** | `dev-secret-change-me` |
| `PRINTSYS_ADMIN_PASS` | Password for the auto-created `admin` on first run | `admin` |

```bash
export PRINTSYS_SECRET="$(python -c 'import secrets; print(secrets.token_hex(32))')"
export PRINTSYS_ADMIN_PASS="a-strong-password"
```

## 3. Production server (multi-user)

Use a process manager and a real database.

```bash
pip install gunicorn psycopg[binary]
export PRINTSYS_DB_URL="postgresql+psycopg://printsys:secret@localhost/printsys"
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 127.0.0.1:8000
```

Tables are created automatically on startup. Put Nginx (or Caddy) in front for
HTTPS and proxy to `127.0.0.1:8000`.

### systemd unit (`/etc/systemd/system/printsys.service`)

```ini
[Unit]
Description=PrintSys
After=network.target

[Service]
WorkingDirectory=/opt/printsys
Environment=PRINTSYS_DB_URL=postgresql+psycopg://printsys:secret@localhost/printsys
Environment=PRINTSYS_SECRET=change-me-to-a-long-random-string
ExecStart=/opt/printsys/.venv/bin/gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 4 -b 127.0.0.1:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now printsys
```

## 4. Email & e-Invoice

- **Email**: enter SMTP host/port/from/credentials under *Settings → Email* to
  send PDF quotes and invoices. Leave blank to keep email disabled.
- **e-Invoice**: fill in your company TIN/BRN/MSIC under *Settings → e-Invoice*.
  Each invoice exposes a MyInvois-aligned JSON at `/invoices/<id>/einvoice`.
  Submitting to the IRBM MyInvois API (sign + submit) requires IRBM credentials
  and is a separate integration step.

## 5. Importing your AutoCount data

Export Customers and Stock items from AutoCount to CSV, then upload them under
*Import Data*. Columns are matched by name and records upserted by code, so you
can re-export and re-import safely.

## 6. Backups

- **SQLite**: back up the `printsys.db` file (stop the app or copy while idle).
- **PostgreSQL**: `pg_dump printsys > backup.sql` on a schedule.

## 7. Tests

```bash
pip install pytest
pytest
```

The suite uses an isolated temporary database and does not touch your data.
