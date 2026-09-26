import os
import re
from pathlib import Path
from datetime import datetime, timedelta

import mysql.connector
from werkzeug.security import generate_password_hash
from dotenv import load_dotenv


# --------------------------------------------------
# LOAD ENVIRONMENT VARIABLES
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "")
DB_NAME = os.getenv("DB_NAME", "enterprise_service_desk")


# --------------------------------------------------
# CONNECT TO MYSQL SERVER
# --------------------------------------------------

print("Connecting to MySQL...")

root = mysql.connector.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD
)

cur = root.cursor()

cur.execute(
    f"""
    CREATE DATABASE IF NOT EXISTS `{DB_NAME}`
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci
    """
)

cur.close()
root.close()

print(f"Database '{DB_NAME}' is ready.")


# --------------------------------------------------
# CONNECT TO DATABASE
# --------------------------------------------------

conn = mysql.connector.connect(
    host=DB_HOST,
    port=DB_PORT,
    user=DB_USER,
    password=DB_PASSWORD,
    database=DB_NAME
)

c = conn.cursor()


# --------------------------------------------------
# READ SCHEMA.SQL
# --------------------------------------------------

schema_path = BASE_DIR.parent / "database" / "schema.sql"

print("Reading database schema...")

sql = schema_path.read_text(encoding="utf-8")


# Remove SQL single-line comments before splitting.
# This prevents comments from being attached to CREATE TABLE statements.
sql = re.sub(r"--[^\r\n]*", "", sql)


# Remove CREATE DATABASE and USE statements because
# the database has already been selected above.
statements = []

for statement in sql.split(";"):
    statement = statement.strip()

    if not statement:
        continue

    upper_statement = statement.upper()

    if upper_statement.startswith("CREATE DATABASE"):
        continue

    if upper_statement.startswith("USE "):
        continue

    statements.append(statement)


# --------------------------------------------------
# CREATE TABLES
# --------------------------------------------------

print(f"Creating {len(statements)} database objects...")

for statement in statements:
    c.execute(statement)

conn.commit()

print("Database tables created successfully.")


# --------------------------------------------------
# DEMO USERS
# --------------------------------------------------

users = [
    (
        "U-1001",
        "Tanvi Bogam",
        "employee@company.com",
        "Employee@123",
        "employee",
        "IT Support",
    ),
    (
        "U-1002",
        "Rahul Sharma",
        "executive@company.com",
        "Executive@123",
        "executive",
        "IT Support",
    ),
    (
        "U-1003",
        "Priya Nair",
        "manager@company.com",
        "Manager@123",
        "manager",
        "IT Support",
    ),
    (
        "U-1004",
        "System Admin",
        "admin@company.com",
        "Admin@123",
        "admin",
        "Administration",
    ),
    (
        "U-1005",
        "Sneha Kulkarni",
        "hr.exec@company.com",
        "Executive@123",
        "executive",
        "HR",
    ),
]


print("Creating demo users...")


for uid, name, email, password, role, department in users:

    c.execute(
        "SELECT id FROM users WHERE id=%s",
        (uid,)
    )

    existing_user = c.fetchone()

    password_hash = generate_password_hash(password)

    if not existing_user:

        c.execute(
            """
            INSERT INTO users
            (
                id,
                name,
                email,
                password_hash,
                role,
                department,
                active
            )
            VALUES
            (%s,%s,%s,%s,%s,%s,1)
            """,
            (
                uid,
                name,
                email,
                password_hash,
                role,
                department,
            ),
        )

    else:

        c.execute(
            """
            UPDATE users
            SET
                name=%s,
                email=%s,
                password_hash=%s,
                role=%s,
                department=%s,
                active=1
            WHERE id=%s
            """,
            (
                name,
                email,
                password_hash,
                role,
                department,
                uid,
            ),
        )


# --------------------------------------------------
# DEPARTMENTS
# --------------------------------------------------

deps = [
    ("D-1", "IT Support"),
    ("D-2", "HR"),
    ("D-3", "Finance"),
    ("D-4", "Administration"),
    ("D-5", "Facilities"),
]


for department in deps:

    c.execute(
        """
        INSERT IGNORE INTO departments(id,name)
        VALUES(%s,%s)
        """,
        department,
    )


# Assign manager
c.execute(
    """
    UPDATE departments
    SET manager_id=%s
    WHERE id IN (%s,%s,%s,%s,%s)
    """,
    (
        "U-1003",
        "D-1",
        "D-2",
        "D-3",
        "D-4",
        "D-5",
    ),
)


# --------------------------------------------------
# CATEGORIES
# --------------------------------------------------

cats = [
    ("C-1", "IT Support", "IT Support", "High"),
    ("C-2", "HR", "HR", "Medium"),
    ("C-3", "Finance", "Finance", "Medium"),
    ("C-4", "Administration", "Administration", "Low"),
    ("C-5", "Facilities", "Facilities", "Low"),
    ("C-6", "Security", "IT Support", "Critical"),
    ("C-7", "Payroll", "Finance", "High"),
]


for category in cats:

    c.execute(
        """
        INSERT IGNORE INTO categories
        (
            id,
            name,
            department,
            default_priority
        )
        VALUES(%s,%s,%s,%s)
        """,
        category,
    )


# --------------------------------------------------
# SAMPLE SERVICE REQUESTS
# --------------------------------------------------

c.execute(
    "SELECT COUNT(*) FROM service_requests"
)

request_count = c.fetchone()[0]


if request_count == 0:

    now = datetime.utcnow()

    sample_requests = [

        (
            "REQ-1024",
            "Laptop Access Request",
            "IT Support",
            "IT Support",
            "Laptop access request - please assist at the earliest.",
            "High",
            "U-1001",
            "U-1002",
            "In Progress",
            now - timedelta(days=2),
            now - timedelta(hours=1),
            now + timedelta(hours=7),
        ),

        (
            "REQ-1025",
            "Salary Query",
            "Payroll",
            "Finance",
            "Salary query - please assist at the earliest.",
            "Medium",
            "U-1001",
            None,
            "Open",
            now - timedelta(days=1),
            now - timedelta(days=1),
            now + timedelta(hours=23),
        ),

        (
            "REQ-1026",
            "ID Card Request",
            "Administration",
            "Administration",
            "ID card request - please assist at the earliest.",
            "Low",
            "U-1001",
            None,
            "Resolved",
            now - timedelta(days=8),
            now - timedelta(days=7),
            now + timedelta(hours=60),
        ),

        (
            "REQ-1027",
            "VPN Access Issue",
            "Security",
            "IT Support",
            "VPN access issue - please assist at the earliest.",
            "Critical",
            "U-1001",
            "U-1002",
            "Assigned",
            now - timedelta(hours=3),
            now - timedelta(hours=3),
            now + timedelta(hours=1),
        ),
    ]


    for (
        request_id,
        title,
        category,
        department,
        description,
        priority,
        employee_id,
        assigned_to,
        status,
        created_at,
        updated_at,
        sla_deadline,
    ) in sample_requests:

        resolved_at = (
            updated_at
            if status == "Resolved"
            else None
        )

        c.execute(
            """
            INSERT INTO service_requests
            (
                id,
                title,
                category,
                department,
                description,
                priority,
                employee_id,
                assigned_to,
                status,
                created_at,
                updated_at,
                sla_deadline,
                resolved_at
            )
            VALUES
            (
                %s,%s,%s,%s,%s,%s,%s,%s,
                %s,%s,%s,%s,%s
            )
            """,
            (
                request_id,
                title,
                category,
                department,
                description,
                priority,
                employee_id,
                assigned_to,
                status,
                created_at,
                updated_at,
                sla_deadline,
                resolved_at,
            ),
        )


        # Request history

        c.execute(
            """
            INSERT INTO request_history
            (
                request_id,
                status,
                user_id,
                note,
                created_at
            )
            VALUES(%s,%s,%s,%s,%s)
            """,
            (
                request_id,
                "Created",
                employee_id,
                "Request created",
                created_at,
            ),
        )


    # --------------------------------------------------
    # ASSIGNMENT + SLA RECORDS
    # --------------------------------------------------

    for (
        request_id,
        title,
        category,
        department,
        description,
        priority,
        employee_id,
        assigned_to,
        status,
        created_at,
        updated_at,
        sla_deadline,
    ) in sample_requests:

        if assigned_to:

            c.execute(
                """
                SELECT id
                FROM request_assignments
                WHERE request_id=%s
                AND assigned_to=%s
                """,
                (
                    request_id,
                    assigned_to,
                ),
            )

            existing_assignment = c.fetchone()

            if not existing_assignment:

                c.execute(
                    """
                    INSERT INTO request_assignments
                    (
                        request_id,
                        assigned_to,
                        assigned_by,
                        assigned_at,
                        note
                    )
                    VALUES(%s,%s,%s,%s,%s)
                    """,
                    (
                        request_id,
                        assigned_to,
                        "U-1003",
                        created_at,
                        "Initial seeded assignment",
                    ),
                )


        # SLA

        c.execute(
            """
            SELECT id
            FROM sla_records
            WHERE request_id=%s
            """,
            (request_id,),
        )

        existing_sla = c.fetchone()


        if not existing_sla:

            if status == "Resolved" and updated_at <= sla_deadline:

                sla_status = "Completed"

            elif (
                datetime.utcnow() > sla_deadline
                and status not in ("Resolved", "Closed")
            ):

                sla_status = "Breached"

            else:

                sla_status = "Active"


            target_hours = {
                "Critical": 4,
                "High": 8,
                "Medium": 24,
                "Low": 72,
            }[priority]


            c.execute(
                """
                INSERT INTO sla_records
                (
                    request_id,
                    priority,
                    target_hours,
                    started_at,
                    deadline,
                    completed_at,
                    status
                )
                VALUES(%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    request_id,
                    priority,
                    target_hours,
                    created_at,
                    sla_deadline,
                    updated_at if status == "Resolved" else None,
                    sla_status,
                ),
            )


    # --------------------------------------------------
    # DEMO NOTIFICATIONS
    # --------------------------------------------------

    c.execute(
        """
        INSERT INTO notifications
        (
            id,
            user_id,
            message,
            request_id,
            is_read,
            created_at
        )
        VALUES(%s,%s,%s,%s,0,%s)
        """,
        (
            "N-1",
            "U-1001",
            "REQ-1024 has been assigned to the IT Support Department.",
            "REQ-1024",
            now,
        ),
    )


    c.execute(
        """
        INSERT INTO notifications
        (
            id,
            user_id,
            message,
            request_id,
            is_read,
            created_at
        )
        VALUES(%s,%s,%s,%s,0,%s)
        """,
        (
            "N-2",
            "U-1002",
            "New request REQ-1027 assigned to you.",
            "REQ-1027",
            now,
        ),
    )


# --------------------------------------------------
# COMMIT & CLOSE
# --------------------------------------------------

conn.commit()

c.close()
conn.close()

print("")
print("==============================================")
print(" Database initialized successfully!")
print("==============================================")
print("")
print("Demo Login Accounts:")
print("Employee : employee@company.com / Employee@123")
print("Executive: executive@company.com / Executive@123")
print("Manager  : manager@company.com / Manager@123")
print("Admin    : admin@company.com / Admin@123")
print("")