[English](README.md) | [正體中文](README.zh-TW.md) | [简体中文](README.zh-CN.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

# Vibe: AI-Powered Low-Code Application Platform

## 📄 Overview

Vibe is a dynamic, web-based platform that empowers users to create, manage, and share single-page web applications using the power of Artificial Intelligence. Users can simply describe the tool or interface they need, and the AI backend generates the necessary HTML, CSS, and JavaScript code. This project is designed to bridge the gap between idea and implementation, allowing for rapid prototyping and deployment of simple web tools.

The platform features a complete ecosystem, including a secure user authentication system, a workspace for developers to manage their creations, an "App Store" to browse and use published applications, and a comprehensive management center for administrators to oversee users, review submissions, and configure the system.

## 🖼️ Screenshots

| Feature                 | Preview                                               |
| ----------------------- | ----------------------------------------------------- |
| **Login Page**          | <img src="example/login_page.png" width="400"/>       |
| **App Store**           | <img src="example/app_store_page.png" width="400"/>   |
| **My Apps Page**        | <img src="example/my_app_page.png" width="400"/>      |
| **Interactive App Editor**| <img src="example/application_edit_page.png" width="400"/> |
| **Share Page**          | <img src="example/share_page.png" width="400"/>       |
| **Management Dashboard**| <img src="example/management_dashboard_page.png" width="400"/>|
| **User Management**     | <img src="example/management_user_management_page.png" width="400"/>|
| **Group Management**    | <img src="example/management_user_group_page.png" width="400"/>|
| **Permission Settings** | <img src="example/management_permission_page.png" width="400"/>|
| **App Review Queue**    | <img src="example/management_app_review_page.png" width="400"/>|
| **Published Apps**      | <img src="example/management_published_app_page.png" width="400"/>|
| **System Configuration**| <img src="example/management_setting_page.png" width="400"/>|

## ✨ Key Features

*   **Conversational AI Development**: At the heart of Vibe is an interactive, chat-based interface where users bring their ideas to life. By simply conversing with the AI, you can describe the application you want to build, request changes, and iteratively refine its functionality. The AI handles the coding, allowing you to focus on the design and purpose of your tool. This process is fully version-controlled, so you can always go back to a previous state.

*   **User and Session Management**: Secure login system with password hashing. Authenticated users have dedicated sessions and workspaces to manage their applications.

*   **Application Lifecycle Management**:
    *   **Drafting & Versioning**: Every change creates a new version, with a complete history available. Users can revert to any previous version.
    *   **Review & Approval Workflow**: Developers can submit their applications for review. Administrators can approve or reject submissions based on functionality and safety.
    *   **Publishing**: Approved applications can be made "live" and will appear in the public App Store for all users to access.

*   **App Store**: A central place for all users to discover, browse, and use published applications. Each app includes a description, a preview, and developer information.

*   **Comprehensive Management Center**: A permission-controlled backend for administrators and reviewers, featuring:
    *   **System Dashboard**: View key statistics like user count, app status distribution, and creation trends.
    *   **User Management**: Create, edit, and manage users, their statuses, and group memberships.
    *   **Group and Permission Control**: Fine-grained access control by assigning users to groups with specific permissions (e.g., `develop_app`, `review_app`, `system_admin`).
    *   **AI Configuration**: Manage AI models, API keys, and system-level prompts for different tasks (code generation, risk analysis).

*   **Risk Analysis & Content Moderation**: AI-driven analysis to identify potential security risks (e.g., script injection) and categorize applications before they are published.

*   **Internationalization (i18n)**: The system supports five languages: English, Traditional Chinese, Simplified Chinese, Japanese, and Korean.


## 🏗️ Project Structure

The project is primarily organized into two main components, which work together with a database and helper modules.

*   **`main.py`**: This is the core of the application and serves as the main entry point. It is responsible for:
    *   Initializing the `NiceGUI` web server and UI.
    *   Handling all user-facing pages, such as the login screen (`/login`), the app creation/editing interface (`/session/{session_id}`), the app store (`/store`), and personal app management pages (`/my-apps`, `/my-shares`).
    *   Managing the AI interaction logic, sending user prompts to an AI service and processing the generated HTML.
    *   Serving published applications and shared links.

*   **`management_pages.py`**: This file defines the entire backend administration interface. It is a distinct section of the application accessible only to users with the appropriate permissions (`system_admin` or `review_app`). Its responsibilities include:
    *   Rendering the management dashboard with system analytics.
    *   Providing the UI and logic for managing users, groups, and permissions.
    *   Defining the application review workflow, allowing administrators to view submitted apps, generate risk reports, and approve or reject them.
    *   Handling system-level configurations, such as AI model settings and prompt templates.

These two files interact with `database.py`, which manages all data persistence in a SQLite database, and `languages.py`, which provides translation services for the UI.

## 📋 Prerequisites

To run this project, you will need to have the Python libraries listed in `requirements.txt` installed.

## 🚀 Installation

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/felixszeto/nice-vibe-coding.git
    cd nice-vibe-coding
    ```

2.  **Install the dependencies:**
    It is recommended to use a virtual environment.
    ```bash
    # Create and activate a virtual environment (optional but recommended)
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`

    # Install the required packages
    pip install -r requirements.txt
    ```

## 💻 Usage

1.  **Initialize the Database:**
    The first time you run the application, it will automatically create a `app_data.db` file with the necessary tables and initial data, including a default admin user.
    *   **Default Admin Credentials**:
        *   Username: `admin`
        *   Password: `admin123`
    *   **Default User Credentials**:
        *   Username: `tester`
        *   Password: `admin123`
        *   (This user has basic permissions and can only use published applications. Use the `admin` account to create users with different roles.)

2. **Pre-loaded Examples:**
   The database comes pre-loaded with a few example applications to demonstrate the platform's capabilities. You can find them in the App Store after logging in:
    *   Salary Calculator
    *   Document Compressor
    *   To-Do List
    *   Computer Simulation
    *   QR Code Generator
    *   Payment Recorder

3.  **Run the Application:**
    Execute the `main.py` file to start the web server.
    ```bash
    python main.py
    ```
    The application will be available at `http://127.0.0.1:8462` by default.

4.  **Using the Platform:**
    *   **Login**: Access the application URL in your browser and log in with the admin credentials or any other user you create.
    *   **Create an App**: Navigate to "My Apps" and click the "add" button to start a new creation session. Use the chat interface to describe the application you want to build.
    *   **Manage Apps**: From the "My Apps" page, you can view your existing applications, check their status (Draft, In Review, Published), and enter a session to manage them.
    *   **Admin Functions**: Log in as `admin` and navigate to the "Management Center" from the side drawer to access all administrative functions.

## 🤖 AI Model Recommendations

For optimal performance, we recommend using the following models, which can be configured in the Management Center. However, you are welcome to experiment with any other models that are compatible with the platform.

*   **Code Generation Model**: `DeepSeek-V3.1 / DeepSeek-R1 / Qwen3-Coder-480B / Gemini-2.5-pro / GPT-5`
*   **Preview Generation Model**: `DeepSeek-V3.1 / DeepSeek-R1 / Qwen3-Coder-480B / Gemini-2.5-pro / GPT-5`
*   **Report Generation Model**: `DeepSeek-V3.1 / DeepSeek-R1 / Qwen3-Coder-480B / Gemini-2.5-pro / GPT-5`

Happy building!

---

## 📜 License

This project is licensed under the [Creative Commons Attribution-NonCommercial 4.0 International License (CC BY-NC 4.0)](https://creativecommons.org/licenses/by-nc/4.0/).

![CC BY-NC 4.0](https://i.creativecommons.org/l/by-nc/4.0/88x31.png)

**You are free to:**

*   **Share** — copy and redistribute the material in any medium or format
*   **Adapt** — remix, transform, and build upon the material

**Under the following terms:**

*   **Attribution** — You must give appropriate credit, provide a link to the license, and indicate if changes were made. You may do so in any reasonable manner, but not in any way that suggests the licensor endorses you or your use.
*   **NonCommercial** — You may not use the material for commercial purposes.

This license does not grant you rights to use the trade names, trademarks, service marks, or product names of the licensor, except as required for reasonable and customary use in describing the origin of the material and reproducing the content of the a notice.