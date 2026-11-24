# Student HQ - Setup, Troubleshooting & Learning Guide

This document explains why the project failed to run initially, the technical principles behind each issue, how they were resolved, and best practices for developing and deploying Django applications.

---

## Table of Contents
1. [Executive Summary](#executive-summary)
2. [Root Causes and Technical Analysis](#root-causes-and-technical-analysis)
   - [1. Non-Portable Virtual Environment (`venv`)](#1-non-portable-virtual-environment-venv)
   - [2. Database Service Inactive](#2-database-service-inactive)
   - [3. Missing Target Database](#3-missing-target-database)
   - [4. Authentication Mismatch in Environment Variables](#4-authentication-mismatch-in-environment-variables)
   - [5. Unapplied Migrations and Missing Seed Data](#5-unapplied-migrations-and-missing-seed-data)
3. [Step-by-Step Solutions Applied](#step-by-step-solutions-applied)
4. [Software Engineering Best Practices Learned](#software-engineering-best-practices-learned)
5. [Day-to-Day Operations & Cheatsheet](#day-to-day-operations--cheatsheet)
6. [Demo Accounts Reference](#demo-accounts-reference)

---

## Executive Summary

When attempting to launch Student HQ initially, the application could not start due to environment-level configuration mismatches rather than bugs in the Python code:

1. A pre-packaged virtual environment copied from another computer failed to execute.
2. The MySQL database server was not running.
3. The configured database (`studenthq_db`) did not exist.
4. Database credentials in `.env` did not match the local MySQL server.
5. Database schema migrations and seed data had not been initialized.

---

## Root Causes and Technical Analysis

### 1. Non-Portable Virtual Environment (`venv`)

#### What Happened
Running `python manage.py check` via the existing `venv` produced:
```text
No Python at '"C:\Users\user\AppData\Local\Programs\Python\Python310\python.exe'
```

#### The Technical Reason
Python virtual environments (`venv`) are **not portable**. They contain:
- Hardcoded absolute paths in configuration files (e.g., `venv/pyvenv.cfg` pointed to `C:\Users\user\...` on a machine with Python 3.10).
- Windows launcher scripts with embedded absolute interpreter paths.
- Compiled binary extensions (`.pyd` files, such as `_mysql.cp310-win_amd64.pyd` and `_bcrypt.pyd`) compiled specifically for Python 3.10 (CPython 3.10 ABI). Your computer has Python 3.12 installed under `C:\Users\hp\...`.

#### Takeaway
Never commit `venv/` to Git or transfer it between machines. Recreate it on each host machine using `requirements.txt`.

---

### 2. Database Service Inactive

#### What Happened
Attempting to connect to the MySQL database returned:
```text
ERROR 2002 (HY000): Can't connect to MySQL server on 'localhost' (10061)
```

#### The Technical Reason
Windows socket error `10061` (`WSAECONNREFUSED`) means the target host actively rejected the connection because no process was listening on the requested port (`3306`). The MySQL / MariaDB daemon from XAMPP was stopped.

---

### 3. Missing Target Database

#### What Happened
The Django configuration in `studenthq/settings.py` specifies:
```python
'NAME': os.getenv('DATABASE_NAME', 'studenthq_db'),
```
Even with MariaDB running, the database `studenthq_db` did not exist on the local MySQL server.

---

### 4. Authentication Mismatch in Environment Variables

#### What Happened
The initial `.env` file contained:
```dotenv
DATABASE_USER=root
DATABASE_PASSWORD=admin123
```
When connecting with this password, MySQL returned:
```text
ERROR 1045 (28000): Access denied for user 'root'@'localhost' (using password: YES)
```

#### The Technical Reason
Standard XAMPP installations configure the MySQL `root` superuser with **no password** (an empty string `""`) by default. Because `.env` had `admin123`, authentication failed.

---

### 5. Unapplied Migrations and Missing Seed Data

#### What Happened
Django requires database tables to match its ORM models (`Student`, `Course`, `Enrollment`, `Fee`, etc.), as well as system tables for sessions and authentication. Without running migrations, opening the site resulted in database table errors, and without seed data, there were no users to log in with.

---

## Step-by-Step Solutions Applied

### Step 1: Rebuilt the Virtual Environment
Recreated the virtual environment using the local Python 3.12 installation:
```powershell
C:\Users\hp\AppData\Local\Programs\Python\Python312\python.exe -m venv venv --system-site-packages --clear
```
Created a clean [requirements.txt](file:///c:/Users/hp/Downloads/studenthq/studenthq/requirements.txt) to document dependencies:
```text
Django>=4.2,<5.0
mysqlclient>=2.2.4
python-dotenv>=1.0.0
python-dateutil>=2.8.2
bcrypt>=4.0.0
```

### Step 2: Started the MariaDB/MySQL Service
Launched the MariaDB daemon from the XAMPP directory:
```powershell
C:\xampp\mysql\bin\mysqld.exe --defaults-file="C:\xampp\mysql\bin\my.ini" --standalone
```

### Step 3: Created the Database
Created `studenthq_db` with `utf8mb4` encoding:
```sql
CREATE DATABASE IF NOT EXISTS studenthq_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### Step 4: Corrected [.env](file:///c:/Users/hp/Downloads/studenthq/studenthq/.env) Credentials
Updated the password variable in [.env](file:///c:/Users/hp/Downloads/studenthq/studenthq/.env) to match XAMPP's blank root password:
```dotenv
DATABASE_NAME=studenthq_db
DATABASE_USER=root
DATABASE_PASSWORD=
DATABASE_HOST=localhost
DATABASE_PORT=3306
```

### Step 5: Ran Migrations and Seed Data
1. Applied schema migrations:
   ```powershell
   .\venv\Scripts\python.exe manage.py migrate
   ```
2. Populated demo courses, fee structures, and test user accounts:
   ```powershell
   .\venv\Scripts\python.exe manage.py seed_data
   ```
3. Verified the setup with automated tests:
   ```powershell
   .\venv\Scripts\python.exe manage.py test
   ```
   *(All 41 tests passed successfully.)*

---

## Software Engineering Best Practices Learned

| Practice | Recommendation |
| :--- | :--- |
| **`.gitignore` for Virtual Environments** | Always add `venv/`, `.env`, and `*.pyd` to `.gitignore`. Never share environments across machines. |
| **Dependency Manifests** | Maintain a [requirements.txt](file:///c:/Users/hp/Downloads/studenthq/studenthq/requirements.txt) file so any developer can recreate the environment using `pip install -r requirements.txt`. |
| **Environment Separation** | Provide an `.env.example` template with dummy values so collaborators know which environment variables are expected. |
| **Idempotent Data Seeding** | Use Django management commands (like `python manage.py seed_data`) with `get_or_create()` to populate sample data safely. |

---

## Day-to-Day Operations & Cheatsheet

### 1. Starting the Application

#### A. Ensure MySQL is running
Start MySQL using either:
- **XAMPP Control Panel**: Click **Start** next to MySQL.
- **Terminal**:
  ```powershell
  Start-Process -FilePath "C:\xampp\mysql\bin\mysqld.exe" -ArgumentList "--defaults-file=C:\xampp\mysql\bin\my.ini", "--standalone" -WindowStyle Hidden
  ```

#### B. Start Django
```powershell
cd c:\Users\hp\Downloads\studenthq\studenthq
.\venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```
Visit: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

### 2. Running Automated Tests
```powershell
.\venv\Scripts\python.exe manage.py test
```

### 3. Re-seeding Test Data (If Needed)
```powershell
.\venv\Scripts\python.exe manage.py seed_data
```

---

## Demo Accounts Reference

| Role | Email | Password | Purpose |
| :--- | :--- | :--- | :--- |
| **Administrator** | `admin@aun.edu.ng` | `admin1234` | Fee structure, course management, audit logs, financial reports |
| **Academic Advisor** | `advisor@aun.edu.ng` | `advisor1234` | Student advising, course approval, academic tracking |
| **Student (CS)** | `student@aun.edu.ng` | `student1234` | Computer Science student dashboard, course registration, fee payment |
| **Student (Business)** | `ba@aun.edu.ng` | `student1234` | Business Administration student portal |
| **Student (Economics)**| `econ@aun.edu.ng` | `student1234` | Economics student portal |
| **Student (Engineering)**| `eng@aun.edu.ng` | `student1234` | Software/Systems Engineering student portal |
