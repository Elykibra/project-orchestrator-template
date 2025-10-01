# Mother AI Project Orchestrator Template

This is the core repository for the Mother AI Project Orchestrator utility. This system is designed to manage complex projects by tracking progress through structured **Checkpoints** and maintaining a central knowledge file called the **Project Brain**.

It uses a Hybrid AI/Human workflow where the AI defines the initial structure, and the human uses the CLI to manage continuous development via version-controlled checkpoints.

---

## 🚀 Getting Started

### Prerequisites

1.  **Python 3.10+**
2.  **Git** installed and configured for your repository.
3.  **Required Libraries:** Install dependencies using pip:
    ```bash
    pip install pyyaml GitPython
    ```
4.  **Virtual Environment:** It is recommended to run this project within a Python virtual environment (`.venv`).

### Core Files and Folders

* `checkpoint.py`: The main command-line utility for managing projects and checkpoints.
* `prompts/`: **Contains the core AI prompt templates** that guide the workflow.
* `ai_design.txt`: **[TEMPORARY INPUT FILE]** Used only for the initial creation of a new project. **This file is ignored by Git.**
* `brains/`: Contains all project data.
    * `brains/Project_Orchestrator/`: The self-managing files for the utility itself.
    * `brains/[New_Project_Name]/`: New project folders created by the `create` command.

---

## 💡 Human-AI Workflow: Using the Prompts

The project lifecycle is a continuous loop defined by two core AI prompt templates, which you will find in the `prompts/` directory.

| Workflow Phase | AI Prompt Used (from `prompts/`)| CLI Command |
| :--- | :--- | :--- |
| **Phase 1: Scoping** | **The Project Architect Prompt** | `create` |
| **Phase 2: Iteration** | **The Four-Part AI Briefing Prompt** | `new` and `commit` |

### Phase 1: New Project Scoping (The Architect)

1.  **Preparation:** Paste a vague project idea into **"The Project Architect Prompt."**
2.  **AI Action:** The AI generates the required Project Brain (JSON) and Initial Checkpoint (YAML) content.
3.  **Execution:** Copy the AI's two output blocks into the temporary `ai_design.txt` file.
4.  **CLI Command:** Use the generated project name and the temporary file to initialize the structure:
    ```bash
    python checkpoint.py create --project [Project_Name] --design-file ai_design.txt
    ```
5.  **Finalization:** Manually run the `commit` command to record the new project files in Git.

### Phase 2: Ongoing Work (The Project Manager)

1.  **Preparation:** Upload the current **Project Brain** and the **Latest Checkpoint YAML** to the chat and paste them into **"The Four-Part AI Briefing Prompt."**
2.  **AI Action:** The AI acts as the Project Manager, providing the first task.
3.  **Work Cycle:** Continue working and using the AI until the `next_steps` are exhausted.
4.  **Closing the Session:** When prompted by the AI, use the interactive session to create a new Checkpoint Log:
    ```bash
    python checkpoint.py new --project [Project_Name]
    ```
5.  **Finalization:** Record the session's work in Git:
    ```bash
    python checkpoint.py commit --project [Project_Name]
    ```

---

## 🛠️ Utility Commands

All interactions with the system are done through the `checkpoint.py` script.

| Action | Command Syntax | Description |
| :--- | :--- | :--- |
| **Create Project** | `python checkpoint.py create --project [Name] --design-file [Path]` | Initializes the project structure based on the design file contents. |
| **Commit Changes** | `python checkpoint.py commit --project [Name]` | Creates a Git commit and push using the latest Checkpoint Log summary. |
| **New Checkpoint**| `python checkpoint.py new --project [Name]` | Launches an interactive session to generate the next Checkpoint Log file. |
| **View Status** | `python checkpoint.py status --project [Name]` | Checks the status and displays the immediate next task for the project. |
