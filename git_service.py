# git_service.py
# Contains all core Git logic: getting diffs, staging, committing, and pushing.

import os
import git
import glob

# Import constants from gui_constants to maintain a single source of truth for paths
from gui_constants import LOGS_DIR

# --- Configuration (Paths and Exclusions) ---
# Files that are constantly changing due to application operations and should be excluded from diffs
# to maintain clean AI context.
EXCLUDE_PATHS = [
    'brains/Project_Orchestrator/project_orchestrator.state.json',
    # Exclude all log files within the current project's log folder
    'brains/*/logs/',
]

# --- Core Functions ---

def _get_repo() -> git.Repo or None:
    """Safely initializes and returns the Git repository object."""
    try:
        # Assumes the script is run from within the Git repository's working tree
        repo = git.Repo(os.getcwd(), search_parent_directories=True)
        return repo
    except git.InvalidGitRepositoryError:
        print("GIT ERROR: Not running inside a valid Git repository.")
        return None
    except Exception as e:
        print(f"GIT ERROR: Failed to initialize Git repository: {e}")
        return None


def get_project_diff(project_name: str) -> str:
    """
    Calculates the Git diff, scoping it to the project directory and excluding
    application-specific noise files.

    This replaces the logic in app_controller.py.
    """
    repo = _get_repo()
    if not repo:
        return "WARNING: Git repository unavailable. Cannot read code changes."

    project_dir = f"brains/{project_name}"
    changed_content = "No uncommitted code changes detected."

    try:
        # Build the list of paths to include and exclude
        diff_paths = [project_dir]

        # Append exclusion filters using the ':!path' syntax
        for p in EXCLUDE_PATHS:
            # We explicitly replace the wildcard if present for clean path matching
            if '*/' in p:
                # Handle the generic 'brains/*/logs/' case by specifically excluding the project's logs
                if p == 'brains/*/logs/':
                    diff_paths.append(f':!{project_dir}/logs/')
                else:
                    print(f"WARNING: Exclusion path '{p}' not handled dynamically for diff.")
            else:
                 diff_paths.append(f':!{p}')


        # Generate the diff between the staging index (None) and the working directory (HEAD)
        changed_content = repo.git.diff(None, *diff_paths)

        if not changed_content:
            return "No uncommitted code changes detected."

    except Exception as e:
        changed_content = f"WARNING: Could not read Git changes. Error: {e}"
        print(changed_content)

    return changed_content


def commit_changes(project_name: str, checkpoint_summary: str):
    """
    Automates Git staging, commit, and push using the checkpoint summary as the message.

    This replaces the logic in checkpoint.py.
    """
    print("\nACTION: Automating Git Commit and Push...")

    repo = _get_repo()
    if not repo:
        print("Commit aborted: Git repository unavailable.")
        return

    # 1. Clean up old, uncommitted -NEW.yaml files before staging
    try:
        new_draft_pattern = os.path.join(LOGS_DIR, f"*-checkpoint-NEW.yaml")
        for file_path in glob.glob(new_draft_pattern):
            if os.path.exists(file_path):
                print(f"INFO: Removing unfinalized draft file: {os.path.basename(file_path)}")
                os.remove(file_path)
    except Exception as e:
         print(f"WARNING: Failed to clean up old draft files: {e}")


    # 2. Check for uncommitted changes
    if not repo.is_dirty(untracked_files=True):
        print("INFO: No changes detected to commit. Git status is clean.")
        return

    # 3. Stage Files (stage all tracked and untracked changes for simplicity in this phase)
    # NOTE: This ensures the logs being committed are the *finalized* ones.
    print("Staging all modified and untracked files...")
    repo.git.add(A=True)

    # 4. Perform Commit
    commit_message = f"feat: Checkpoint - {project_name} - {checkpoint_summary}"
    print(f"Committing with message: '{commit_message}'")

    if not repo.index.diff("HEAD"):
        print("INFO: Index is empty after staging. No changes to commit. Aborting.")
        return

    try:
        repo.index.commit(commit_message)
        print("Commit successful.")

        # 5. Push Changes
        print("Pushing changes to remote...")
        remote = repo.remote(name='origin')
        remote.push()
        print("Push successful. Checkpoint fully recorded.")

    except git.GitCommandError as e:
        print(f"GIT ERROR: A git command failed. Check your remote status or credentials: {e}")
    except Exception as e:
        print(f"CRITICAL ERROR during Git automation: {e}")