-- Enterprise Service Desk seed data
-- Canonical seed for the Python + Flask + MySQL build.
-- Run backend/init_db.py first because it creates secure password hashes
-- for the demo accounts and inserts the sample requests.

USE enterprise_service_desk;

INSERT IGNORE INTO departments (id, name) VALUES
  ('D-1', 'IT Support'),
  ('D-2', 'HR'),
  ('D-3', 'Finance'),
  ('D-4', 'Administration'),
  ('D-5', 'Facilities');

INSERT IGNORE INTO categories (id, name, department, default_priority) VALUES
  ('C-1', 'IT Support', 'IT Support', 'High'),
  ('C-2', 'HR', 'HR', 'Medium'),
  ('C-3', 'Finance', 'Finance', 'Medium'),
  ('C-4', 'Administration', 'Administration', 'Low'),
  ('C-5', 'Facilities', 'Facilities', 'Low'),
  ('C-6', 'Security', 'IT Support', 'Critical'),
  ('C-7', 'Payroll', 'Finance', 'High');

-- Demo users and password hashes are intentionally managed by init_db.py.
-- This avoids storing plaintext passwords in SQL.
