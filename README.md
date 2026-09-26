# Enterprise Employee Service Desk & Workflow Management Portal

## Technology stack
- Frontend: HTML, CSS, JavaScript
- Backend: **Python + Flask**
- Database: **MySQL**
- Development tool: **Visual Studio Code**

The previous Node.js/Express + JSON-file backend has been replaced with a Flask REST API and a real MySQL database. The frontend API wrapper now points to Flask on port 5000.

## Project structure
```
enterprise-service-desk/
├── frontend/                  # HTML/CSS/JS UI
├── backend/
│   ├── app.py                 # Flask backend + REST API
│   ├── init_db.py             # Creates tables and sample data
│   ├── requirements.txt       # Python dependencies
│   └── .env.example           # MySQL/Flask settings
├── database/
│   ├── schema.sql             # MySQL schema
│   └── seed.sql               # Compatible reference seed
├── postman/
└── tests/
```

## Run in VS Code
1. Open the `enterprise-service-desk` folder in VS Code.
2. Make sure MySQL Server is running.
3. Open a terminal in `backend`.
4. Create/activate a virtual environment (recommended):
   - Windows: `py -m venv venv`
   - PowerShell activation is optional; if blocked by policy, use `venv\Scripts\python.exe` directly.
5. Install packages:
   `venv\Scripts\python.exe -m pip install -r requirements.txt`
6. Copy `backend/.env.example` to `backend/.env` and put your MySQL root password in `DB_PASSWORD`.
7. Initialize MySQL:
   `venv\Scripts\python.exe init_db.py`
8. Start Flask:
   `venv\Scripts\python.exe app.py`
9. Open: **http://127.0.0.1:5000**

Flask serves the frontend itself, so you do not need `npm`, Node.js, or a separate frontend server.

## Demo accounts
| Role | Email | Password |
|---|---|---|
| Employee | employee@company.com | Employee@123 |
| Executive | executive@company.com | Executive@123 |
| HR Executive | hr.exec@company.com | Executive@123 |
| Manager | manager@company.com | Manager@123 |
| Admin | admin@company.com | Admin@123 |

## API
Flask API base URL: `http://127.0.0.1:5000/api`

Health check: `http://127.0.0.1:5000/api/health`

The existing frontend pages and API method names are preserved, so the UI continues to use login, requests, dashboards, notifications, admin, comments, assignment and status workflows.

## Documentation deliverables
- ER diagram: `docs/ER_Diagram.png`
- Application architecture diagram: `docs/Application_Architecture_Diagram.png`
- Final project report: `docs/Final_Project_Report_Tanvi_Bogam.docx`
- GitHub repository: upload this project folder to GitHub before final submission if the mentor requires a repository URL.


## Week 3 implementation checklist
- Role-based authentication and protected pages for Employee, Executive, Manager and Admin.
- Employee dashboard, request creation, request list, request details and notifications.
- Workflow: Open → Assigned → In Progress → Pending Information → Resolved → Closed, with controlled transitions and formal reopen.
- Manager assignment with assignment history.
- SLA targets: Critical 4h, High 8h, Medium 24h, Low 72h.
- SLA state and SLA records are maintained for each request.
- Comments and staff-only internal notes with authorization checks.
- Search, filters, date range and pagination on request lists.
- Manager/admin dashboard KPIs and workload charts.
- Admin users, departments, categories and audit trail.
- MySQL schema includes assignment, attachment and SLA support tables.
- Request attachments are validated and persisted under `backend/uploads` (maximum 5 MB; allowed document/image/text types).
- Audit logging and notifications are generated for important workflow actions.

## Submission notes
1. Do not commit `backend/.env` or real database passwords.
2. Copy `.env.example` to `.env` and set `DB_PASSWORD` on the machine where the demo is run.
3. Run `init_db.py` before the first launch; it creates secure password hashes and demo data.
4. Start Flask with `venv\Scripts\python.exe app.py` and open `http://127.0.0.1:5000`.
