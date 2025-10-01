# Mother AI Project Orchestrator 🧠✨

A **self-contained, visual development environment** built with **Python** and **Tkinter** that enforces a structured, checkpoint-driven methodology for software development. It integrates project management, version control, and a disciplined logging system into a single, seamless GUI.

---

## 🚀 Core Features

* **Visual Project Dashboard:** At-a-glance view of the current project's status, next goal, and upcoming tasks.
* **Seamless Checkpoint Workflow:** A guided, multi-step process for logging work, defining future tasks, and reviewing key decisions.
* **Automated Git Integration:** Dedicated "Commit" view to automatically stage changes, format commit messages from checkpoint summaries, and push to your remote repository.
* **Checkpoint History Viewer:** Instantly access and review the contents of any previously finalized checkpoint log.
* **Integrated File Explorer & Live Console:** Built-in directory tree for immediate context and a dedicated panel for transparent, real-time feedback and debugging.

---

## 💡 The Checkpoint Methodology

The system codifies project history by using two core data structures stored in the `brains/` directory:

1.  **The Project Brain (`.brain.v1.json`):** Stores the project's long-term configuration, architectural constants, and core objectives.
2.  **Checkpoint Logs (`.yaml`):** Immutable, timestamped YAML files that document a single development session, including **work completed**, **key decisions made**, and **goals for the next session**.

---

## 🛠️ Getting Started

### Prerequisites
* **Python 3.10+**
* **Git** installed and configured.

### Installation & Launch

1.  **Clone the repository:**
    ```bash
    git clone [https://github.com/your-username/project-orchestrator-template.git](https://github.com/your-username/project-orchestrator-template.git)
    cd project-orchestrator-template
    ```
2.  **Install dependencies:**
    ```bash
    python -m venv .venv
    # Windows: .venv\Scripts\activate
    # macOS/Linux: source .venv/bin/activate
    pip install pyyaml GitPython ttkthemes
    ```
3.  **Run the application:**
    ```bash
    python gui_app.py
    ```

---

## 🗺️ The Development Cycle (GUI Workflow)

The entire process is managed through the application's tabs:

1.  **View Status (Dashboard Tab):** Select your project to view your primary goal and immediate tasks.
2.  **Create a Checkpoint (Checkpoint Tab):** Fill in the form detailing finished work and outlining the goals for the next session.
3.  **Review & Finalize (Pop-up Window):** Write down **key decisions** made during the session. This action creates the permanent, numbered checkpoint log.
4.  **Commit Your Work (Commit Tab):** Click **"Run Commit & Push"** to automatically stage all changes, create a structured commit message from your latest checkpoint summary, and push to remote.
