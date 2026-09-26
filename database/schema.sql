CREATE DATABASE IF NOT EXISTS enterprise_service_desk CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE enterprise_service_desk;

CREATE TABLE IF NOT EXISTS departments (
  id VARCHAR(20) PRIMARY KEY,
  name VARCHAR(100) NOT NULL UNIQUE,
  manager_id VARCHAR(20) NULL
);

CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(20) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  email VARCHAR(160) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('employee','executive','manager','admin') NOT NULL,
  department VARCHAR(100) NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
  id VARCHAR(20) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  department VARCHAR(100) NOT NULL,
  default_priority ENUM('Low','Medium','High','Critical') NOT NULL DEFAULT 'Medium'
);

CREATE TABLE IF NOT EXISTS service_requests (
  id VARCHAR(20) PRIMARY KEY,
  title VARCHAR(200) NOT NULL,
  category VARCHAR(100) NOT NULL,
  department VARCHAR(100) NOT NULL,
  description TEXT NOT NULL,
  priority ENUM('Low','Medium','High','Critical') NOT NULL,
  required_date DATETIME NULL,
  attachment VARCHAR(255) NULL,
  contact VARCHAR(60) NULL,
  employee_id VARCHAR(20) NOT NULL,
  assigned_to VARCHAR(20) NULL,
  status VARCHAR(30) NOT NULL DEFAULT 'Open',
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  sla_deadline DATETIME NOT NULL,
  resolved_at DATETIME NULL,
  INDEX idx_req_status(status), INDEX idx_req_priority(priority),
  INDEX idx_req_department(department), INDEX idx_req_employee(employee_id),
  INDEX idx_req_assigned(assigned_to),
  FOREIGN KEY (employee_id) REFERENCES users(id),
  FOREIGN KEY (assigned_to) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS request_comments (
  id VARCHAR(40) PRIMARY KEY,
  request_id VARCHAR(20) NOT NULL,
  user_id VARCHAR(20) NOT NULL,
  user_name VARCHAR(120) NOT NULL,
  role VARCHAR(20) NOT NULL,
  text TEXT NOT NULL,
  internal BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL,
  INDEX idx_comment_request(request_id),
  FOREIGN KEY (request_id) REFERENCES service_requests(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS request_history (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  request_id VARCHAR(20) NOT NULL,
  status VARCHAR(100) NOT NULL,
  user_id VARCHAR(20) NOT NULL,
  note TEXT NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_history_request(request_id),
  FOREIGN KEY (request_id) REFERENCES service_requests(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS notifications (
  id VARCHAR(50) PRIMARY KEY,
  user_id VARCHAR(20) NOT NULL,
  message VARCHAR(255) NOT NULL,
  request_id VARCHAR(20) NULL,
  is_read BOOLEAN NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL,
  INDEX idx_notification_user(user_id,is_read),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (request_id) REFERENCES service_requests(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id VARCHAR(50) PRIMARY KEY,
  user_id VARCHAR(20) NOT NULL,
  action VARCHAR(100) NOT NULL,
  request_id VARCHAR(20) NULL,
  details VARCHAR(255) NULL,
  created_at DATETIME NOT NULL,
  INDEX idx_audit_created(created_at),
  FOREIGN KEY (user_id) REFERENCES users(id),
  FOREIGN KEY (request_id) REFERENCES service_requests(id) ON DELETE SET NULL
);


-- Assignment history required by the workflow specification.
CREATE TABLE IF NOT EXISTS request_assignments (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  request_id VARCHAR(20) NOT NULL,
  assigned_to VARCHAR(20) NOT NULL,
  assigned_by VARCHAR(20) NOT NULL,
  assigned_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  note VARCHAR(255) NULL,
  INDEX idx_assignment_request(request_id),
  INDEX idx_assignment_employee(assigned_to),
  FOREIGN KEY (request_id) REFERENCES service_requests(id) ON DELETE CASCADE,
  FOREIGN KEY (assigned_to) REFERENCES users(id),
  FOREIGN KEY (assigned_by) REFERENCES users(id)
);

-- Attachment metadata. The current UI stores a safe display name; this table
-- keeps the schema ready for persisted uploads.
CREATE TABLE IF NOT EXISTS request_attachments (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  request_id VARCHAR(20) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  file_path VARCHAR(500) NOT NULL,
  uploaded_by VARCHAR(20) NOT NULL,
  uploaded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX idx_attachment_request(request_id),
  FOREIGN KEY (request_id) REFERENCES service_requests(id) ON DELETE CASCADE,
  FOREIGN KEY (uploaded_by) REFERENCES users(id)
);

-- One SLA record per request, including target, deadline and completion state.
CREATE TABLE IF NOT EXISTS sla_records (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  request_id VARCHAR(20) NOT NULL,
  priority ENUM('Low','Medium','High','Critical') NOT NULL,
  target_hours INT NOT NULL,
  started_at DATETIME NOT NULL,
  deadline DATETIME NOT NULL,
  completed_at DATETIME NULL,
  status ENUM('Active','Completed','Breached') NOT NULL DEFAULT 'Active',
  INDEX idx_sla_request(request_id),
  INDEX idx_sla_status(status),
  FOREIGN KEY (request_id) REFERENCES service_requests(id) ON DELETE CASCADE
);
