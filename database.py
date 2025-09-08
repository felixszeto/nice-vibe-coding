import sqlite3
import datetime
import bcrypt
import re
import logging
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# =================================================================
# Password Handling - using bcrypt directly
# =================================================================

def get_password_hash(password: str) -> str:
    """Hashes a plaintext password."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_bytes = bcrypt.hashpw(password_bytes, salt)
    return hashed_bytes.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies if a plaintext password matches a hashed password."""
    try:
        plain_password_bytes = plain_password.encode('utf-8')
        hashed_password_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(plain_password_bytes, hashed_password_bytes)
    except (ValueError, TypeError):
        return False

# =================================================================

DB_FILE = "app_data.db"
DEFAULT_PROMPT_NAME = "default_system_prompt"
APP_TEMPLATE_PROMPT_NAME = "app_template_prompt"
RISK_ANALYSIS_PROMPT_NAME = "risk_analysis_prompt"

def get_db_connection():
    """Creates and returns a database connection."""
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database: creates tables and seeds initial prompts and settings."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # CREATE TABLE statements extracted from db_design.sql
    create_table_sqls = [
        """
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS prompts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            content TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS organizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            tax_id VARCHAR(20),
            address VARCHAR(200),
            contact_phone VARCHAR(20),
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS departments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL,
            organization_id BIGINT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (organization_id) REFERENCES organizations(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username VARCHAR(50) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            first_name VARCHAR(50),
            last_name VARCHAR(50),
            email VARCHAR(100) NOT NULL UNIQUE,
            phone VARCHAR(20),
            avatar_url VARCHAR(255),
            status TINYINT NOT NULL DEFAULT 1, -- 1: active, 0: inactive
            lang VARCHAR(10) DEFAULT 'en',
            organization_id BIGINT,
            department_id INTEGER,
            balance DECIMAL(18,2) DEFAULT 0.00,
            login_attempts INTEGER DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login_at DATETIME,
            FOREIGN KEY (organization_id) REFERENCES organizations(id),
            FOREIGN KEY (department_id) REFERENCES departments(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL UNIQUE, -- Group name should be unique
            description TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS user_groups (
            user_id INTEGER NOT NULL,
            group_id INTEGER NOT NULL,
            PRIMARY KEY (user_id, group_id),
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS authorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL UNIQUE, -- Authority name should be unique
            description TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS group_authorities (
            group_id INTEGER NOT NULL,
            authority_id INTEGER NOT NULL,
            PRIMARY KEY (group_id, authority_id),
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE,
            FOREIGN KEY (authority_id) REFERENCES authorities(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS versions (
            uuid TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            user_request TEXT,
            base_version_uuid TEXT,
            raw_ai_response TEXT,
            html_content TEXT NOT NULL,
            app_template_html TEXT, -- AI-generated template for app store preview
            functional_description TEXT,
            operating_instructions TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,      -- Maintain association with your design
            app_name TEXT NOT NULL,
            description TEXT,                     -- New: Application description
            owner_user_id INTEGER NOT NULL,       -- New: Application owner
            
            -- Approval and publishing status management
            latest_submitted_version_uuid TEXT, -- Latest version submitted for review
            live_version_uuid TEXT,             -- Current live version
            status TINYINT NOT NULL DEFAULT 0,  -- 0: DRAFT, 1: PENDING_APPROVAL, 2: APPROVED, 3: REJECTED, 4: PUBLISHED, 5: ARCHIVED, 6: DELETED
            
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            submitted_at TIMESTAMP,             -- Submission time for review
            last_reviewed_at TIMESTAMP,         -- Last review time
            published_at TIMESTAMP,             -- First publication time
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            preview_generation_status TINYINT DEFAULT 0, -- 0: None, 1: Pending, 2: In Progress, 3: Completed, 4: Failed
            preview_generation_retries INTEGER DEFAULT 0,

            FOREIGN KEY (owner_user_id) REFERENCES users(id),
            FOREIGN KEY (latest_submitted_version_uuid) REFERENCES versions(uuid),
            FOREIGN KEY (live_version_uuid) REFERENCES versions(uuid)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER NOT NULL,
            version_uuid TEXT NOT NULL,         -- Which version to review
            reviewer_user_id INTEGER NOT NULL,  -- Reviewer
            decision TINYINT NOT NULL,          -- 1: approved, 2: rejected
            comments TEXT,                      -- Review comments
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY (application_id) REFERENCES applications(id),
            FOREIGN KEY (version_uuid) REFERENCES versions(uuid),
            FOREIGN KEY (reviewer_user_id) REFERENCES users(id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS app_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL, -- e.g., 'risk', 'category'
            name TEXT NOT NULL,
            lang TEXT NOT NULL DEFAULT 'en', -- Add language field
            UNIQUE(type, name, lang)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS application_version_features (
            version_uuid TEXT NOT NULL,
            feature_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (version_uuid, feature_id),
            FOREIGN KEY (version_uuid) REFERENCES versions(uuid) ON DELETE CASCADE,
            FOREIGN KEY (feature_id) REFERENCES app_features(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS app_shares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            share_uuid TEXT UNIQUE NOT NULL,
            version_uuid TEXT NOT NULL,
            user_id INTEGER NOT NULL,
            expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (version_uuid) REFERENCES versions(uuid) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    ]

    # INSERT statements extracted from db_design.sql (mock data)
    insert_data_sqls = [
        """
        INSERT OR IGNORE INTO prompts (name, content) VALUES
        ('default_system_prompt', 'You are a professional front-end development assistant. Your task is to generate or modify HTML based on user requirements and existing HTML code.
Your output must strictly adhere to the following rules:
1. Before you start generating the final HTML code, you can write down your thought process, analysis, and plan within <think></think> tags. This part will be displayed to the user. Due to token limitations, the thought process must be as brief as possible to save output. If necessary, you can skip this step. Your ultimate goal is to quickly provide stable and runnable code without overthinking logical issues, as the user will test it themselves.
2. The complete, runnable HTML code you provide to the user must be, and can only be, wrapped in a pair of `<output-html>` and `</output-html>` tags. Do not add any explanatory text or comments outside the `<output-html>` tag. The HTML content should be self-contained. If CSS or JS is needed, please use inline styles or `<style>`, `<script>` tags as much as possible.
3. Remember that the generated code is for creating a page. Strictly avoid omitting any parts that overlap with previous code.
4. Since the user''s computer cannot access the internet, importing non-native HTML packages, CDNs, and online media resources is prohibited.

---
[PREVIOUS HTML CODE]
{previous_html_code}

---
[CONVERSATION HISTORY]
{conversation_history}

---
[USER''S NEW REQUEST]
{user_request}

---
**[RESPONSE MUST USE LANGUAGE]**
{app_lang_code}')
        """,
        """
        INSERT OR IGNORE INTO prompts (name, content) VALUES
        ('app_template_prompt', 'You are a creative front-end designer. Your task is to create an "extremely simplified and miniaturized small application template" based on the user''s existing HTML code.
This template will be used for display in an application store, aiming for maximum visualization to showcase the core functionality of the application with minimal elements to attract user clicks.

Your output must strictly adhere to the following rules:
1.  **Do not use the `<think>` tag**. Directly output the final HTML.
2.  The final HTML code must be, and can only be, wrapped in a pair of `<output-html>` and `</output-html>` tags.
3.  The HTML must be **a complete, self-contained HTML5 file**, including `<!DOCTYPE html>`, `<html style="width: 100%; height: 100%">`, `<head>`, and `<body>` tags. All CSS and JS must be inline.
4.  The design must adapt to a **square** container (e.g., 400px*400px), be responsive, and must fill the entire screen.
5.  Abstract and visualize the core functionality instead of a full implementation. For example, for a calculator, you might only show an animation of numbers and symbols. Ensure core visual elements are centered or well-laid out within the container to avoid being hidden by scrolling.
6.  Prohibit the use of any external links, CDNs, or online media resources.

---
[USER''S FULL APPLICATION HTML]
{app_html_code}

---
**[RESPONSE MUST USE LANGUAGE]**
{app_lang_code}')
        """,
        """
        INSERT OR IGNORE INTO prompts (name, content) VALUES
        ('risk_analysis_prompt', '''You are a professional application security analyst and product classification expert.
Your task is to analyze the provided HTML code and output your analysis report in a multilingual JSON format.

**Analysis and Output Requirements:**

1.  **Multilingual Support:**
    *   You must generate a complete analysis report for both **English (`en`)** and the user-specified language **`{app_lang_code}`**.
    *   The root JSON object of the output must contain two keys: `en` and `{app_lang_code}`.
    *   If `{app_lang_code}` is the same as `en`, only output the `en` report.

2.  **Report Content (for each language):**
    *   **Risk Assessment:**
        *   Categorize potential security risks into three levels: `critical_risks`, `medium_risks`, `low_risks`.
        *   **Prioritize existing tags:** Please prioritize selecting from the "Existing Risk Tag List" for the corresponding level below. If no match is found, you can create a new, concise description.
        *   **Existing Critical Risk Tag List:** {existing_critical_risks}
        *   **Existing Medium Risk Tag List:** {existing_medium_risks}
        *   **Existing Low Risk Tag List:** {existing_low_risks}
    *   **Application Categories (categories):**
        *   Suggest 2-3 most relevant categories based on the application''s functionality and content.
        *   **Prioritize existing categories:** Please prioritize selecting from the "Existing Category List" below. If a suitable category is not found, you can create a new category name.
        *   **Existing Category List:** "Games","Productivity","Lifestyle","Tools","Education","Health & Fitness","Social","News","Finance","Shopping","Travel","Photo & Video","Music","Books","Efficiency & Finance","Family", {existing_categories}
    *   **Functional Description (functional_description):** Generate a concise and accurate functional description.
    *   **Operating Instructions (operating_instructions):** Generate a clear and easy-to-understand operating guide.

**Output Format Requirements:**
*   Your output **must** be a single, well-formatted JSON object.
*   Do not add any extra text, comments, or tags before or after the JSON object.
*   The JSON structure is as follows:
    ```json
    {
      "en": {
        "critical_risks": ["Risk A", "Risk B"],
        "medium_risks": ["Risk C"],
        "low_risks": [],
        "categories": ["Tools", "Productivity"],
        "functional_description": "An English description of the app.",
        "operating_instructions": "English operating instructions."
      },
      "{app_lang_code}": {
        "critical_risks": ["Risk A translated", "Risk B translated"],
        "medium_risks": ["Risk C translated"],
        "low_risks": [],
        "categories": ["Tools translated", "Productivity translated"],
        "functional_description": "A translated description of the app.",
        "operating_instructions": "Translated operating instructions."
      }
    }
    ```

---
**[HTML CODE TO BE ANALYZED]**
{app_html_code}

---
**[RESPONSE MUST USE LANGUAGE]**
{app_lang_code}''')
        """,
    """
    INSERT OR IGNORE INTO authorities (id, name, description) VALUES
        (1, 'system_admin', 'Access to the backend management page'),
        (2, 'publish_app', 'Publish applications'),
        (3, 'review_app', 'Review applications'),
        (4, 'develop_app', 'Develop applications'),
        (5, 'share_app', 'Share applications')
        """,
        """
        INSERT OR IGNORE INTO groups (id, name, description) VALUES
        (1, 'Administrators', 'System administrator group'),
        (2, 'Developers', 'Application developer group'),
        (3, 'Reviewers', 'Application reviewer group')
        """,
        """
        INSERT OR IGNORE INTO group_authorities (group_id, authority_id) VALUES
        (1, 1), -- Admin has management access
        (2, 2), -- Developers can publish
        (2, 4), -- Developers can develop
        (2, 5), -- Developers can share
        (3, 3) -- Reviewers can review
        """,
        """
        INSERT OR IGNORE INTO users (id, username, password_hash, email, status) VALUES
        (1, 'admin', '$2b$12$/UBEgHhmx6LY04S83rqsJOPn75dLGg1qbNdfWSpZOL7tO2NindU/e', 'admin@example.com', 1)
        """,
        """
        INSERT OR IGNORE INTO user_groups (user_id, group_id) VALUES
        (1, 1) -- admin is in Administrators
        """
    ]

    for sql in create_table_sqls:
        cursor.execute(sql)
        logger.info(f"Executed CREATE TABLE: {sql.strip().splitlines()[0]}...")

    # Check and add 'app_template_html' column (if it doesn't exist)
    try:
        cursor.execute("PRAGMA table_info(versions)")
        columns = [row['name'] for row in cursor.fetchall()]
        if 'app_template_html' not in columns:
            cursor.execute("ALTER TABLE versions ADD COLUMN app_template_html TEXT")
            logger.info("Column 'app_template_html' has been successfully added to the 'versions' table.")
        if 'functional_description' not in columns:
            cursor.execute("ALTER TABLE versions ADD COLUMN functional_description TEXT")
            logger.info("Column 'functional_description' has been successfully added to the 'versions' table.")
        if 'operating_instructions' not in columns:
            cursor.execute("ALTER TABLE versions ADD COLUMN operating_instructions TEXT")
            logger.info("Column 'operating_instructions' has been successfully added to the 'versions' table.")
    except sqlite3.OperationalError as e:
        logger.error(f"Error checking 'versions' table: {e}")

    # Add AI Models Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS ai_models (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        api_key TEXT NOT NULL,
        model_name TEXT NOT NULL,
        endpoint_url TEXT,
        is_code_generation_model BOOLEAN NOT NULL DEFAULT 0,
        is_preview_generation_model BOOLEAN NOT NULL DEFAULT 0,
        is_report_generation_model BOOLEAN NOT NULL DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(name)
    )
    """)
    logger.info("Executed CREATE TABLE for ai_models...")

    # Data migration: from settings table to ai_models table
    cursor.execute("SELECT key, value FROM settings WHERE key LIKE '%AI_%'")
    old_ai_settings = {row['key']: row['value'] for row in cursor.fetchall()}
    
    migrated = False
    if 'PRODUCTION_AI_API_KEY' in old_ai_settings:
        logger.info("Migrating PRODUCTION AI settings to ai_models table...")
        cursor.execute("""
            INSERT INTO ai_models (name, api_key, model_name, endpoint_url, is_code_generation_model)
            SELECT 'Default Production Model', ?, ?, ?, 1
            WHERE NOT EXISTS (SELECT 1 FROM ai_models WHERE name = 'Default Production Model')
        """, (
            old_ai_settings.get('PRODUCTION_AI_API_KEY', ''),
            old_ai_settings.get('PRODUCTION_AI_MODEL', ''),
            old_ai_settings.get('PRODUCTION_AI_ENDPOINT', '')
        ))
        migrated = True

    if 'PREVIEW_AI_API_KEY' in old_ai_settings:
        logger.info("Migrating PREVIEW AI settings to ai_models table...")
        cursor.execute("""
            INSERT INTO ai_models (name, api_key, model_name, endpoint_url, is_preview_generation_model, is_report_generation_model)
            SELECT 'Default Preview & Report Model', ?, ?, ?, 1, 1
            WHERE NOT EXISTS (SELECT 1 FROM ai_models WHERE name = 'Default Preview & Report Model')
        """, (
            old_ai_settings.get('PREVIEW_AI_API_KEY', ''),
            old_ai_settings.get('PREVIEW_AI_MODEL', ''),
            old_ai_settings.get('PREVIEW_AI_ENDPOINT', '')
        ))
        migrated = True

    if migrated:
        logger.info("Deleting old AI settings from settings table...")
        cursor.execute("DELETE FROM settings WHERE key LIKE '%AI_%'")

    # Insert or ignore regular settings
    default_settings = {
        'AUTO_PUBLISH_ON_APPROVAL': 'false',
        'REQUIRE_RISK_REPORT_BEFORE_APPROVAL': 'false'
    }
    for key, value in default_settings.items():
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    # Insert prompts data
    # The initial prompts are now inserted via the main INSERT block.
    # This section is kept for potential future logic but is currently redundant.
    pass

    for sql in insert_data_sqls:
        try:
            cursor.execute(sql)
            logger.info(f"Executed INSERT/UPDATE: {sql.strip().splitlines()[0]}...")
        except sqlite3.IntegrityError as e:
            logger.warning(f"Skipping insert due to integrity error (data likely exists): {e} - SQL: {sql.strip().splitlines()[0]}...")
        except Exception as e:
            logger.error(f"Error executing SQL: {e} - SQL: {sql.strip().splitlines()[0]}...")

    conn.commit()
    conn.close()

def get_setting(key: str) -> str | None:
    """Gets a value from the settings table by key."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row['value'] if row else None

def get_all_settings() -> list[sqlite3.Row]:
    """Gets all system settings."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT key, value FROM settings")
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_setting(key: str, value: str):
    """Updates or inserts a setting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Use INSERT OR REPLACE (or ON CONFLICT DO UPDATE) to handle existing keys
        cursor.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))
        conn.commit()
        logger.info(f"Setting '{key}' updated successfully.")
    except Exception as e:
        logger.error(f"Error updating setting {key}: {e}")
        raise e
    finally:
        conn.close()

def get_prompt(name: str) -> str | None:
    """Gets prompt content by name and automatically replaces language codes."""
    # Late import to avoid circular dependency issues
    from languages import get_lang

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT content FROM prompts WHERE name = ?", (name,))
    row = cursor.fetchone()
    conn.close()
    
    if row and row['content']:
        content = row['content']
        # Check if placeholder exists to avoid unnecessary formatting or errors
        if '{app_lang_code}' in content:
            # get_lang() returns the default language 'en' when there is no user context
            lang_code = get_lang()
            # Check if placeholder exists to avoid unnecessary formatting or errors
        if '{app_lang_code}' in content:
            # get_lang() returns the default language 'en' when there is no user context
            lang_code = get_lang()
            content = content.replace('{app_lang_code}', lang_code)
            return content
        return content
    return None

def add_version(version_data: dict):
    """Adds a new version to the database."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO versions (uuid, session_id, user_request, base_version_uuid, raw_ai_response, html_content, app_template_html)
        VALUES (:uuid, :session_id, :user_request, :base_version_uuid, :raw_ai_response, :html_content, :app_template_html)
    """, version_data)
    conn.commit()
    conn.close()

def get_all_prompts() -> list[sqlite3.Row]:
    """Gets all prompts."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, content FROM prompts ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return rows

def update_prompt(name: str, content: str):
    """Updates prompt content by name."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE prompts SET content = ?, updated_at = ? WHERE name = ?", 
                       (content, datetime.datetime.now(), name))
        conn.commit()
        logger.info(f"Prompt '{name}' updated successfully.")
    except Exception as e:
        logger.error(f"Error updating prompt {name}: {e}")
        raise e
    finally:
        conn.close()

def get_version_html(uuid_str: str) -> str | None:
    """Gets the HTML content of a version by UUID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT html_content FROM versions WHERE uuid = ?", (uuid_str,))
    row = cursor.fetchone()
    conn.close()
    return row['html_content'] if row else None

def update_version_template(uuid_str: str, template_html: str):
    """Updates the application template for a specific version."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE versions SET app_template_html = ? WHERE uuid = ?", (template_html, uuid_str))
    conn.commit()
    conn.close()

def get_version_template(uuid_str: str) -> str | None:
    """Gets the application template HTML content of a version by UUID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT app_template_html FROM versions WHERE uuid = ?", (uuid_str,))
    row = cursor.fetchone()
    conn.close()
    return row['app_template_html'] if row else None

def update_version_details(version_uuid: str, functional_description: str, operating_instructions: str):
    """Updates version details, such as functional description and operating instructions."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE versions
            SET functional_description = ?, operating_instructions = ?
            WHERE uuid = ?
        """, (functional_description, operating_instructions, version_uuid))
        conn.commit()
        logger.info(f"Version {version_uuid} details updated.")
    except Exception as e:
        logger.error(f"Error updating version details for {version_uuid}: {e}")
        raise e
    finally:
        conn.close()

def get_session_versions(session_id: str) -> list[sqlite3.Row]:
    """Gets all versions for a session, sorted by time, including information needed to reconstruct history."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT uuid, base_version_uuid, user_request, raw_ai_response, created_at
        FROM versions
        WHERE session_id = ?
        ORDER BY created_at ASC
    """, (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_application_by_session(session_id: str) -> sqlite3.Row | None:
    """Gets application information for a specific session."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM applications WHERE session_id = ?", (session_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_all_live_applications(lang: str) -> list[sqlite3.Row]:
    """Gets all live applications in the store, including their preview templates."""
    conn = get_db_connection()
    cursor = conn.cursor()
    query = """
        SELECT
            a.app_name,
            a.description,
            a.live_version_uuid,
            u.username as owner_username,
            v.app_template_html,
            v.functional_description,
            v.operating_instructions,
            COALESCE(
                (SELECT GROUP_CONCAT(f.name) FROM app_features f JOIN application_version_features avf ON f.id = avf.feature_id WHERE avf.version_uuid = a.live_version_uuid AND f.type = 'category' AND f.lang = ?),
                (SELECT GROUP_CONCAT(f.name) FROM app_features f JOIN application_version_features avf ON f.id = avf.feature_id WHERE avf.version_uuid = a.live_version_uuid AND f.type = 'category' AND f.lang = 'en')
            ) as categories,
            COALESCE(
                (SELECT GROUP_CONCAT(f.name) FROM app_features f JOIN application_version_features avf ON f.id = avf.feature_id WHERE avf.version_uuid = a.live_version_uuid AND f.type = 'critical_risk' AND f.lang = ?),
                (SELECT GROUP_CONCAT(f.name) FROM app_features f JOIN application_version_features avf ON f.id = avf.feature_id WHERE avf.version_uuid = a.live_version_uuid AND f.type = 'critical_risk' AND f.lang = 'en')
            ) as critical_risks,
            COALESCE(
                (SELECT GROUP_CONCAT(f.name) FROM app_features f JOIN application_version_features avf ON f.id = avf.feature_id WHERE avf.version_uuid = a.live_version_uuid AND f.type = 'medium_risk' AND f.lang = ?),
                (SELECT GROUP_CONCAT(f.name) FROM app_features f JOIN application_version_features avf ON f.id = avf.feature_id WHERE avf.version_uuid = a.live_version_uuid AND f.type = 'medium_risk' AND f.lang = 'en')
            ) as medium_risks,
            COALESCE(
                (SELECT GROUP_CONCAT(f.name) FROM app_features f JOIN application_version_features avf ON f.id = avf.feature_id WHERE avf.version_uuid = a.live_version_uuid AND f.type = 'low_risk' AND f.lang = ?),
                (SELECT GROUP_CONCAT(f.name) FROM app_features f JOIN application_version_features avf ON f.id = avf.feature_id WHERE avf.version_uuid = a.live_version_uuid AND f.type = 'low_risk' AND f.lang = 'en')
            ) as low_risks
        FROM applications a
        JOIN versions v ON a.live_version_uuid = v.uuid
        JOIN users u ON a.owner_user_id = u.id
        WHERE a.status = 4 -- 4: PUBLISHED
        ORDER BY a.published_at DESC
    """
    cursor.execute(query, (lang, lang, lang, lang))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_user_by_username(username: str) -> sqlite3.Row | None:
    """Gets user information by username."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_user_by_id(user_id: int) -> sqlite3.Row | None:
    """Gets single user information by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # Do not select password_hash for security
    cursor.execute("SELECT id, username, email, status FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row

def update_user(user_id: int, username: str, email: str, status: int, password: str | None = None):
    """Updates user information. If a password is provided, it will also be updated."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    now = datetime.datetime.now()
    
    try:
        if password:
            hashed_password = get_password_hash(password)
            cursor.execute("""
                UPDATE users
                SET username = ?, email = ?, status = ?, password_hash = ?, updated_at = ?
                WHERE id = ?
            """, (username, email, status, hashed_password, now, user_id))
        else:
            cursor.execute("""
                UPDATE users
                SET username = ?, email = ?, status = ?, updated_at = ?
                WHERE id = ?
            """, (username, email, status, now, user_id))
        
        conn.commit()
        logger.info(f"User with ID {user_id} updated successfully.")
    except sqlite3.IntegrityError as e:
        logger.error(f"Error updating user {user_id}: {e}")
        raise e
    finally:
        conn.close()

def delete_user(user_id: int):
    """Deletes a user by ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Considering foreign key constraints, a more complex deletion logic might be needed in a real application
        # For example: first handle associated user_groups, applications, etc.
        cursor.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        logger.info(f"User with ID {user_id} deleted successfully.")
    except Exception as e:
        logger.error(f"Error deleting user {user_id}: {e}")
        raise e
    finally:
        conn.close()

def get_all_users() -> list[sqlite3.Row]:
    """Gets a list of all users."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, email, status, created_at FROM users ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    # Convert sqlite3.Row objects to a list of standard dictionaries for robustness
    return [dict(row) for row in rows]

def get_user_permissions(user_id: int) -> set[str]:
    """Gets all permission names for a user by user ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT a.name
        FROM authorities a
        JOIN group_authorities ga ON a.id = ga.authority_id
        JOIN user_groups ug ON ga.group_id = ug.group_id
        WHERE ug.user_id = ?
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return {row['name'] for row in rows}

def get_all_groups() -> list[sqlite3.Row]:
    """Gets all groups."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description FROM groups ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def get_all_authorities() -> list[sqlite3.Row]:
    """Gets all authorities."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, description FROM authorities ORDER BY name")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]
# =================================================================
# Authorities and Groups CRUD
# =================================================================

def create_group(name: str, description: str):
    """Creates a new group."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO groups (name, description) VALUES (?, ?)", (name, description))
        conn.commit()
    finally:
        conn.close()

def update_group(group_id: int, name: str, description: str):
    """Updates a group's information."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE groups SET name = ?, description = ? WHERE id = ?", (name, description, group_id))
        conn.commit()
    finally:
        conn.close()

def delete_group(group_id: int):
    """Deletes a group."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        conn.commit()
    finally:
        conn.close()

def create_authority(name: str, description: str):
    """Creates a new authority."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO authorities (name, description) VALUES (?, ?)", (name, description))
        conn.commit()
    finally:
        conn.close()

def update_authority(authority_id: int, name: str, description: str):
    """Updates an authority's information."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE authorities SET name = ?, description = ? WHERE id = ?", (name, description, authority_id))
        conn.commit()
    finally:
        conn.close()

def delete_authority(authority_id: int):
    """Deletes an authority."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM authorities WHERE id = ?", (authority_id,))
        conn.commit()
    finally:
        conn.close()

def get_group_authorities(group_id: int) -> set[int]:
    """Gets all authority IDs for a group."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT authority_id FROM group_authorities WHERE group_id = ?", (group_id,))
    rows = cursor.fetchall()
    conn.close()
    return {row['authority_id'] for row in rows}

def update_group_authorities(group_id: int, authority_ids: list[int]):
    """Updates a group's authority settings."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        # First, delete the old associations
        cursor.execute("DELETE FROM group_authorities WHERE group_id = ?", (group_id,))
        # Then, insert the new associations
        if authority_ids:
            values = [(group_id, auth_id) for auth_id in authority_ids]
            cursor.executemany("INSERT INTO group_authorities (group_id, authority_id) VALUES (?, ?)", values)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()

def get_user_groups(user_id: int) -> set[int]:
    """Gets all group IDs for a user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT group_id FROM user_groups WHERE user_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return {row['group_id'] for row in rows}

def update_user_groups(user_id: int, group_ids: list[int]):
    """Updates a user's group settings."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        # First, delete the old associations
        cursor.execute("DELETE FROM user_groups WHERE user_id = ?", (user_id,))
        # Then, insert the new associations
        if group_ids:
            values = [(user_id, group_id) for group_id in group_ids]
            cursor.executemany("INSERT INTO user_groups (user_id, group_id) VALUES (?, ?)", values)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
def create_user(username: str, password: str, email: str, org_id: int = None, dept_id: int = None):
    """(For testing) Creates a new user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    hashed_password = get_password_hash(password)
    try:
        cursor.execute("""
            INSERT INTO users (username, password_hash, email, organization_id, department_id)
            VALUES (?, ?, ?, ?, ?)
        """, (username, hashed_password, email, org_id, dept_id))
        conn.commit()
        print(f"User '{username}' created successfully.")
    except sqlite3.IntegrityError:
        print(f"Error: User with username '{username}' or email '{email}' already exists.")
    finally:
        conn.close()

def get_apps_by_owner_id(user_id: int) -> list[sqlite3.Row]:
    """Gets all applications by owner ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.session_id, a.app_name, a.status, v.app_template_html, a.live_version_uuid
        FROM applications a
        LEFT JOIN versions v ON a.latest_submitted_version_uuid = v.uuid
        WHERE a.owner_user_id = ? AND a.status != 6
        ORDER BY a.updated_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_pending_applications() -> list[sqlite3.Row]:
    """Gets all pending applications (status=1)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.app_name, a.session_id, u.username as owner_username, a.submitted_at
        FROM applications a
        JOIN users u ON a.owner_user_id = u.id
        WHERE a.status = 1 -- 1: PENDING_APPROVAL
        ORDER BY a.submitted_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_published_applications() -> list[sqlite3.Row]:
    """Gets all published applications (status=4)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.id, a.app_name, a.session_id, u.username as owner_username, a.published_at
        FROM applications a
        JOIN users u ON a.owner_user_id = u.id
        WHERE a.status = 4 -- 4: PUBLISHED
        ORDER BY a.published_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def archive_application(session_id: str, as_admin: bool = False):
    """
    Archives/unpublishes an application.
    - If operated by the user (as_admin=False), status becomes ARCHIVED (5).
    - If operated by an admin, status becomes REJECTED (3), and live_version_uuid is cleared.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now()
    
    if as_admin:
        # Admin unpublishing is treated as a rejection/revocation of publication
        cursor.execute("""
            UPDATE applications
            SET status = 3, live_version_uuid = NULL, updated_at = ?
            WHERE session_id = ?
        """, (now, session_id))
    else:
        # User archives it themselves
        cursor.execute("""
            UPDATE applications
            SET status = 5, updated_at = ?
            WHERE session_id = ?
        """, (now, session_id))
        
    conn.commit()
    conn.close()

def cancel_submission(session_id: str):
    """Cancels an application's submission for review."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE applications
        SET status = 0, -- 0: DRAFT
            submitted_at = NULL,
            updated_at = ?
        WHERE session_id = ? AND status = 1
    """, (datetime.datetime.now(), session_id))
    conn.commit()
    conn.close()

def publish_application(session_id: str):
    """Publishes an approved application."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT latest_submitted_version_uuid FROM applications WHERE session_id = ? AND status = 2", (session_id,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return

    live_uuid = row['latest_submitted_version_uuid']
    
    cursor.execute("""
        UPDATE applications
        SET status = 4, -- 4: PUBLISHED
            live_version_uuid = ?,
            latest_submitted_version_uuid = ?, -- Keep submitted and live version in sync after publishing
            published_at = ?
        WHERE session_id = ? AND status = 2
    """, (live_uuid, live_uuid, datetime.datetime.now(), session_id))
    conn.commit()
    conn.close()
def add_review(application_id: int, version_uuid: str, reviewer_user_id: int, decision: int, comments: str | None = None):
    """
    Adds a review record and updates the corresponding application status.
    decision: 1 for approved, 2 for rejected
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now()
    
    # Update application status based on the decision
    # 2: APPROVED, 3: REJECTED
    new_status = 2 if decision == 1 else 3

    try:
        # Start transaction
        cursor.execute("BEGIN")

        # 1. Insert a new review record into the reviews table
        cursor.execute("""
            INSERT INTO reviews (application_id, version_uuid, reviewer_user_id, decision, comments, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (application_id, version_uuid, reviewer_user_id, decision, comments, now))

        # 2. Update the status and last reviewed time in the applications table
        cursor.execute("""
            UPDATE applications
            SET status = ?, last_reviewed_at = ?, updated_at = ?
            WHERE id = ?
        """, (new_status, now, now, application_id))

        # Commit transaction
        conn.commit()
        logger.info(f"Review for application {application_id} has been added, status set to {new_status}.")

        # If approved and auto-publish is enabled, publish immediately
        if new_status == 2: # 2: APPROVED
            auto_publish = get_setting('AUTO_PUBLISH_ON_APPROVAL')
            if auto_publish == 'true':
                try:
                    # Get session_id for publishing
                    cursor.execute("SELECT session_id FROM applications WHERE id = ?", (application_id,))
                    app_row = cursor.fetchone()
                    if app_row:
                        session_id = app_row['session_id']
                        logger.info(f"Auto-publishing application {application_id} (session: {session_id}) as per settings.")
                        # Cannot call publish_application directly here because it will create a new connection
                        # We need to complete it in the same transaction
                        cursor.execute("SELECT latest_submitted_version_uuid FROM applications WHERE session_id = ? AND status = 2", (session_id,))
                        publish_row = cursor.fetchone()
                        if publish_row:
                            live_uuid = publish_row['latest_submitted_version_uuid']
                            cursor.execute("""
                                UPDATE applications
                                SET status = 4, -- 4: PUBLISHED
                                    live_version_uuid = ?,
                                    latest_submitted_version_uuid = ?,
                                    published_at = ?
                                WHERE session_id = ? AND status = 2
                            """, (live_uuid, live_uuid, datetime.datetime.now(), session_id))
                            conn.commit()
                            logger.info(f"Application {session_id} auto-published successfully.")
                except Exception as auto_publish_e:
                    logger.error(f"Auto-publishing failed for application {application_id}: {auto_publish_e}")
                    # Do not roll back the main review, just log the error
                    pass


    except Exception as e:
        # If an error occurs, roll back the transaction
        conn.rollback()
        logger.error(f"Failed to add review for application {application_id}: {e}")
        raise e
    finally:
        conn.close()


def create_or_update_application(session_id: str, version_uuid: str, app_name: str, user_id: int):
    """Creates or updates an application and submits it for review."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now()
    cursor.execute("""
        INSERT INTO applications (
            session_id, app_name, description, owner_user_id, latest_submitted_version_uuid,
            status, submitted_at, updated_at, created_at
        )
        VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?)
        ON CONFLICT(session_id) DO UPDATE SET
            app_name = excluded.app_name,
            description = NULL,
            latest_submitted_version_uuid = excluded.latest_submitted_version_uuid,
            status = 1, -- PENDING_APPROVAL
            submitted_at = excluded.submitted_at,
            updated_at = excluded.updated_at
    """, (session_id, app_name, None, user_id, version_uuid, now, now, now))
    conn.commit()
    conn.close()

def create_draft_application(session_id: str, version_uuid: str, user_id: int):
    """If the application does not exist, create a draft application."""
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.datetime.now()
    
    # Try to extract app name from the version's HTML content
    cursor.execute("SELECT html_content FROM versions WHERE uuid = ?", (version_uuid,))
    version_row = cursor.fetchone()
    html_content = version_row['html_content'] if version_row else ''
    
    title_match = re.search(r'<title>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
    app_name = title_match.group(1).strip() if title_match and title_match.group(1).strip() else f"Untitled App-{session_id[:8]}"

    cursor.execute("""
        INSERT INTO applications (session_id, app_name, owner_user_id, latest_submitted_version_uuid, status, created_at, updated_at)
        SELECT ?, ?, ?, ?, 0, ?, ?
        WHERE NOT EXISTS (SELECT 1 FROM applications WHERE session_id = ?)
    """, (session_id, app_name, user_id, version_uuid, now, now, session_id))
    
    conn.commit()
    conn.close()

def update_preview_generation_status(session_id: str, status: int):
    """Updates the application's preview generation status."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE applications
            SET preview_generation_status = ?, updated_at = ?
            WHERE session_id = ?
        """, (status, datetime.datetime.now(), session_id))
        conn.commit()
        logger.info(f"Application {session_id} preview generation status updated to {status}.")
    except Exception as e:
        logger.error(f"Error updating preview generation status for {session_id}: {e}")
        raise e
    finally:
        conn.close()

def increment_preview_generation_retries(session_id: str):
    """Increments the application's preview generation retry count."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            UPDATE applications
            SET preview_generation_retries = preview_generation_retries + 1, updated_at = ?
            WHERE session_id = ?
        """, (datetime.datetime.now(), session_id))
        conn.commit()
        logger.info(f"Application {session_id} preview generation retries incremented.")
    except Exception as e:
        logger.error(f"Error incrementing preview generation retries for {session_id}: {e}")
        raise e
    finally:
        conn.close()

def get_applications_for_preview_generation() -> list[sqlite3.Row]:
    """Gets all applications that need preview generation (status is Pending or Failed, and retry count has not reached the limit)."""
    conn = get_db_connection()
    cursor = conn.cursor()
    # 0: None, 1: Pending, 2: In Progress, 3: Completed, 4: Failed
    cursor.execute("""
        SELECT a.session_id, a.latest_submitted_version_uuid, v.html_content
        FROM applications a
        JOIN versions v ON a.latest_submitted_version_uuid = v.uuid
        WHERE a.preview_generation_status IN (1, 4) -- Pending, Failed (for retry)
          AND a.preview_generation_retries < 5 -- Max 5 retries
        ORDER BY a.updated_at ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_application_preview_status(session_id: str) -> tuple[int, int] | None:
    """Gets the preview generation status and retry count for a specific session_id."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT preview_generation_status, preview_generation_retries
        FROM applications
        WHERE session_id = ?
    """, (session_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return row['preview_generation_status'], row['preview_generation_retries']
    return None

def delete_application(session_id: str):
    """Marks an application as deleted."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE applications
        SET status = 6, updated_at = ? -- 6: DELETED
        WHERE session_id = ?
    """, (datetime.datetime.now(), session_id))
    conn.commit()
    conn.close()

def add_or_get_feature(type: str, name: str, lang: str = 'en') -> int:
    """If the feature does not exist, add it and return its ID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # First, try to get it
        cursor.execute("SELECT id FROM app_features WHERE type = ? AND name = ? AND lang = ?", (type, name, lang))
        row = cursor.fetchone()
        if row:
            return row['id']
        
        # If it does not exist, insert it
        cursor.execute("INSERT INTO app_features (type, name, lang) VALUES (?, ?, ?)", (type, name, lang))
        conn.commit()
        logger.info(f"Added new feature '{name}' of type '{type}' with lang '{lang}' and ID {cursor.lastrowid}.")
        return cursor.lastrowid
    finally:
        conn.close()

def link_feature_to_version(version_uuid: str, feature_id: int):
    """Links a feature to an application version."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO application_version_features (version_uuid, feature_id)
            VALUES (?, ?)
        """, (version_uuid, feature_id))
        conn.commit()
    finally:
        conn.close()

def get_features_for_version(version_uuid: str, lang: str) -> dict[str, list]:
    """Gets all features for a specific version, grouped by type and language."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT f.type, f.name
        FROM app_features f
        JOIN application_version_features v_f ON f.id = v_f.feature_id
        WHERE v_f.version_uuid = ? AND (f.lang = ? OR f.lang = 'en')
    """, (version_uuid, lang))
    rows = cursor.fetchall()
    conn.close()
    
    features = {}
    for row in rows:
        if row['type'] not in features:
            features[row['type']] = []
        features[row['type']].append(row['name'])
    return features

def get_features_by_type(feature_type: str) -> list[str]:
    """Gets all unique feature names by type."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT name FROM app_features WHERE type = ?", (feature_type,))
    rows = cursor.fetchall()
    conn.close()
    return [row['name'] for row in rows]
def get_report_data_by_version(version_uuid: str, lang: str) -> dict | None:
    """
    Retrieves all report-related data for a specific version UUID,
    including categorized risks, categories, and descriptions.
    Returns None if no features are associated with the version.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    # First, get the features
    cursor.execute("""
        SELECT f.type, f.name, f.lang
        FROM app_features f
        JOIN application_version_features v_f ON f.id = v_f.feature_id
        WHERE v_f.version_uuid = ?
    """, (version_uuid,))
    feature_rows = cursor.fetchall()

    # If there are no features, we can assume no report has been generated
    if not feature_rows:
        conn.close()
        return None

    report_data = {
        "critical_risks": [],
        "medium_risks": [],
        "low_risks": [],
        "categories": [],
        "functional_description": "",
        "operating_instructions": ""
    }
    
    # Process features into the dictionary
    for row in feature_rows:
        feature_type = row['type']
        feature_name = row['name']
        feature_lang = row['lang']

        # Map from DB type to JSON key
        if feature_lang == lang or feature_lang == 'en':
            if feature_type == 'critical_risk':
                report_data['critical_risks'].append(feature_name)
            elif feature_type == 'medium_risk':
                report_data['medium_risks'].append(feature_name)
            elif feature_type == 'low_risk':
                report_data['low_risks'].append(feature_name)
            elif feature_type == 'category':
                report_data['categories'].append(feature_name)

    # Second, get the descriptions from the versions table
    cursor.execute("""
        SELECT functional_description, operating_instructions
        FROM versions
        WHERE uuid = ?
    """, (version_uuid,))
    version_row = cursor.fetchone()

    if version_row:
        report_data["functional_description"] = version_row["functional_description"] or ""
        report_data["operating_instructions"] = version_row["operating_instructions"] or ""

    conn.close()
    return report_data

def get_dashboard_stats() -> dict:
    """Gets key statistics for the dashboard."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # Total users (only active users)
        cursor.execute("SELECT COUNT(id) FROM users WHERE status = 1")
        total_users = cursor.fetchone()[0]
        
        # Total applications (excluding deleted ones)
        cursor.execute("SELECT COUNT(id) FROM applications WHERE status != 6")
        total_apps = cursor.fetchone()[0]
        
        # Number of pending applications
        cursor.execute("SELECT COUNT(id) FROM applications WHERE status = 1")
        pending_apps = cursor.fetchone()[0]
        
        # Number of published applications
        cursor.execute("SELECT COUNT(id) FROM applications WHERE status = 4")
        published_apps = cursor.fetchone()[0]
        
        return {
            "total_users": total_users,
            "total_apps": total_apps,
            "pending_apps": pending_apps,
            "published_apps": published_apps,
        }
    except Exception as e:
        logger.error(f"Error getting dashboard statistics: {e}")
        return {
            "total_users": "N/A",
            "total_apps": "N/A",
            "pending_apps": "N/A",
            "published_apps": "N/A",
        }
    finally:
        conn.close()
def get_version_creation_trends():
    """Gets the daily version creation trend."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Query the number of versions created each day and sort by date
        cursor.execute("""
            SELECT DATE(created_at) as creation_date, COUNT(uuid) as version_count
            FROM versions
            GROUP BY creation_date
            ORDER BY creation_date ASC
            LIMIT 30 -- Last 30 days
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting version creation trend: {e}")
        return []
    finally:
        conn.close()

def get_category_distribution():
    """Gets the category distribution of published applications."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Query the number of published applications in each category
        cursor.execute("""
            SELECT
                f.name as category_name,
                COUNT(DISTINCT a.id) as app_count
            FROM applications a
            JOIN application_version_features avf ON a.live_version_uuid = avf.version_uuid
            JOIN app_features f ON avf.feature_id = f.id
            WHERE a.status = 4 -- 4: PUBLISHED
              AND f.type = 'category'
              AND f.lang = 'en'
            GROUP BY f.name
            ORDER BY app_count DESC
        """)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as e:
        logger.error(f"Error getting application category distribution: {e}")
        return []
    finally:
        conn.close()
def create_app_share(version_uuid: str, user_id: int, expires_at: datetime.datetime | None) -> str:
    """Creates a new share link for a specified application version."""
    conn = get_db_connection()
    cursor = conn.cursor()
    share_uuid = str(uuid.uuid4())
    try:
        cursor.execute("""
            INSERT INTO app_shares (share_uuid, version_uuid, user_id, expires_at)
            VALUES (?, ?, ?, ?)
        """, (share_uuid, version_uuid, user_id, expires_at))
        conn.commit()
        logger.info(f"Created share link {share_uuid} for version {version_uuid}.")
        return share_uuid
    finally:
        conn.close()

def get_app_share(share_uuid: str) -> sqlite3.Row | None:
    """Gets valid share information by share UUID."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM app_shares
        WHERE share_uuid = ? AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
    """, (share_uuid,))
    row = cursor.fetchone()
    conn.close()
    return row

def get_user_shares(user_id: int) -> list[sqlite3.Row]:
    """Gets all valid share links and their version numbers created by a specific user."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        WITH VersionNumbers AS (
            SELECT
                uuid,
                session_id,
                ROW_NUMBER() OVER(PARTITION BY session_id ORDER BY created_at) as version_number
            FROM versions
        )
        SELECT
            s.share_uuid,
            s.version_uuid,
            s.expires_at,
            a.app_name,
            vn.version_number
        FROM app_shares s
        JOIN versions v ON s.version_uuid = v.uuid
        JOIN applications a ON v.session_id = a.session_id
        JOIN VersionNumbers vn ON s.version_uuid = vn.uuid
        WHERE s.user_id = ? AND (s.expires_at IS NULL OR s.expires_at > CURRENT_TIMESTAMP)
        ORDER BY s.created_at DESC
    """, (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def delete_app_share(share_uuid: str, user_id: int):
    """Deletes a share link."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM app_shares WHERE share_uuid = ? AND user_id = ?", (share_uuid, user_id))
        conn.commit()
        logger.info(f"Share link {share_uuid} deleted by user {user_id}.")
    finally:
        conn.close()

# =================================================================
# AI Model Management
# =================================================================

def create_ai_model(name: str, api_key: str, model_name: str, endpoint_url: str | None) -> int:
    """Creates a new AI model setting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        now = datetime.datetime.now()
        cursor.execute("""
            INSERT INTO ai_models (name, api_key, model_name, endpoint_url, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (name, api_key, model_name, endpoint_url, now, now))
        conn.commit()
        model_id = cursor.lastrowid
        logger.info(f"AI model '{name}' created with ID {model_id}.")
        return model_id
    finally:
        conn.close()

def get_all_ai_models() -> list[sqlite3.Row]:
    """Gets all AI model settings."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM ai_models ORDER BY created_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

def update_ai_model(model_id: int, name: str, api_key: str, model_name: str, endpoint_url: str | None):
    """Updates an existing AI model setting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        now = datetime.datetime.now()
        cursor.execute("""
            UPDATE ai_models
            SET name = ?, api_key = ?, model_name = ?, endpoint_url = ?, updated_at = ?
            WHERE id = ?
        """, (name, api_key, model_name, endpoint_url, now, model_id))
        conn.commit()
        logger.info(f"AI model ID {model_id} updated successfully.")
    finally:
        conn.close()

def delete_ai_model(model_id: int):
    """Deletes an AI model setting."""
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM ai_models WHERE id = ?", (model_id,))
        conn.commit()
        logger.info(f"AI model ID {model_id} deleted successfully.")
    finally:
        conn.close()

def get_active_model_for_task(task_type: str) -> sqlite3.Row | None:
    """
    Gets the enabled model for a specific task type.
    task_type: 'code_generation', 'preview_generation', 'report_generation'
    """
    field_map = {
        'code_generation': 'is_code_generation_model',
        'preview_generation': 'is_preview_generation_model',
        'report_generation': 'is_report_generation_model'
    }
    column_name = field_map.get(task_type)
    if not column_name:
        raise ValueError(f"Invalid task type: {task_type}")

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM ai_models WHERE {column_name} = 1 LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    return row

def set_active_model_for_task(model_id: int, task_type: str, is_enabled: bool):
    """
    Sets the enabled model for a specific task type.
    task_type: 'code_generation', 'preview_generation', 'report_generation'
    """
    field_map = {
        'code_generation': 'is_code_generation_model',
        'preview_generation': 'is_preview_generation_model',
        'report_generation': 'is_report_generation_model'
    }
    column_name = field_map.get(task_type)
    if not column_name:
        raise ValueError(f"Invalid task type: {task_type}")

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("BEGIN")
        # If enabling, first disable all other models for this task type
        if is_enabled:
            cursor.execute(f"UPDATE ai_models SET {column_name} = 0, updated_at = ? WHERE {column_name} = 1", (datetime.datetime.now(),))
        
        # Update the target model
        cursor.execute(f"UPDATE ai_models SET {column_name} = ?, updated_at = ? WHERE id = ?", (is_enabled, datetime.datetime.now(), model_id))
        
        conn.commit()
        logger.info(f"Model ID {model_id} active status for task '{task_type}' set to {is_enabled}.")
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to set active model for task '{task_type}': {e}")
        raise e
    finally:
        conn.close()