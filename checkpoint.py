import argparse
import json
import yaml
import sys
import os
import git
import datetime

# --- Configuration (Hardcoded for Phase I) ---
# NOTE: These paths will be derived dynamically in later phases.
# The path now points to the file in the new structure:
PROJECT_BRAIN_PATH = "brains/Project_Orchestrator/project_orchestrator.brain.v1.json"
LATEST_CHECKPOINT_PATH = "logs/2025-10-02-orchestrator-checkpoint-1.yaml"


def read_brain(path: str) -> dict | None:
    """Reads the Project Brain JSON file, providing robust error handling."""
    print(f"Loading Project Brain from: {path}...")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            brain_data = json.load(f)
            # Basic validation: Check for essential keys (e.g., 'project')
            if 'project' not in brain_data:
                print("ERROR: The Project Brain file is missing the required 'project' key.")
                return None
            print(f"Project Brain (v{brain_data.get('version', 'N/A')}) loaded successfully.")
            return brain_data

    except FileNotFoundError:
        print(f"ERROR: Project Brain file not found at '{path}'. Check path and file placement.")
        return None
    except json.JSONDecodeError:
        print(f"ERROR: Project Brain file at '{path}' is not valid JSON. Check for formatting errors.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while reading the Project Brain: {e}")
        return None


def read_checkpoint(path: str) -> dict | None:
    """Reads the Latest Checkpoint YAML file, providing robust error handling."""
    print(f"Loading Latest Checkpoint from: {path}...")
    try:
        with open(path, 'r', encoding='utf-8') as f:
            checkpoint_data = yaml.safe_load(f)

            # Basic validation: Check for essential keys (e.g., 'next_steps')
            if not isinstance(checkpoint_data, dict) or 'next_steps' not in checkpoint_data:
                print("ERROR: The Checkpoint file is missing the required 'next_steps' key or is invalid.")
                return None

            print(f"Checkpoint for '{checkpoint_data.get('project', 'N/A')}' loaded successfully.")

            # Show the next task for immediate feedback
            next_task = checkpoint_data.get('next_steps', ['[Check file]'])[0]
            print(f"NEXT TASK: {next_task}")

            return checkpoint_data

    except FileNotFoundError:
        print(f"ERROR: Checkpoint file not found at '{path}'.")
        return None
    except yaml.YAMLError as e:
        print(f"ERROR: Checkpoint file at '{path}' is not valid YAML. Check for formatting errors: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while reading the Checkpoint: {e}")
        return None


def get_project_paths(orchestrator_brain: dict, project_name: str) -> tuple[str, str] | tuple[None, None]:
    """Retrieves the brain and checkpoint paths for a given project from the Orchestrator's brain."""

    managed_projects = orchestrator_brain.get('managed_projects', {})
    project_info = managed_projects.get(project_name)

    if not project_info:
        print(f"ERROR: Project '{project_name}' not found in the Orchestrator's managed_projects list.")
        return None, None

    brain_path = project_info.get('brain_path')
    checkpoint_path = project_info.get('latest_checkpoint')

    if not brain_path or not checkpoint_path:
        print(
            f"ERROR: Missing 'brain_path' or 'latest_checkpoint' for project '{project_name}' in the Orchestrator brain.")
        return None, None

    return brain_path, checkpoint_path


def commit_changes(project_name: str, checkpoint_data: dict):
    """Automates Git staging, commit, and push using data from the checkpoint log."""

    print("\nACTION: Automating Git Commit...")

    # 1. Get Commit Message from Checkpoint Data
    commit_summary = checkpoint_data.get('summary')
    if not commit_summary:
        print("ERROR: Checkpoint log is missing the required 'summary' field for the commit message. Aborting commit.")
        return

    # 2. Get Files to Commit from Checkpoint Data (or assume all staged)
    # NOTE: In a future phase, we would get this from the 'files_updated' field.
    # For now, we will stage ALL changes, which is a safer default.

    try:
        # Initialize the Git repository object. Assumes we are running in the project root.
        repo = git.Repo(os.getcwd())

        # Check for uncommitted changes (index is dirty)
        if not repo.is_dirty(untracked_files=True):
            print("INFO: No changes detected to commit. Git status is clean.")
            return

        # 3. Stage Files (stage all tracked and untracked changes for simplicity in this phase)
        print("Staging all modified and untracked files...")
        repo.git.add(A=True)  # Stages ALL changes (tracked and untracked)

        # 4. Perform Commit
        commit_message = f"feat: Checkpoint - {project_name} - {commit_summary}"
        print(f"Committing with message: '{commit_message}'")

        # Check if index is ready for commit (optional safety check)
        if not repo.index.diff("HEAD"):
            print("INFO: Index is empty after staging. No changes to commit. Aborting.")
            return

        repo.index.commit(commit_message)
        print("Commit successful.")

        # 5. Push Changes
        print("Pushing changes to remote...")
        # Get the active remote (usually 'origin')
        remote = repo.remote(name='origin')
        remote.push()
        print("Push successful. Checkpoint fully recorded on GitHub.")

    except git.GitCommandError as e:
        print(f"GIT ERROR: A git command failed. Check your remote status or credentials: {e}")
    except Exception as e:
        print(f"CRITICAL ERROR during Git automation: {e}")


def create_new_checkpoint(project_name: str, latest_checkpoint_data: dict):
    """Interactively creates and saves a new Checkpoint YAML log."""

    print("\nACTION: Creating New Checkpoint Log...")

    # 1. Gather Interactive Input
    new_summary = input("Enter a summary for the work completed this session: ")
    new_goal = input("Enter the overall goal for the NEXT Checkpoint: ")

    # Gather next steps interactively
    print("\n--- Next Steps ---")
    new_next_steps = []
    print("Enter tasks for the NEXT Checkpoint (one per line). Type 'done' when finished.")
    while True:
        task = input(f"Task {len(new_next_steps) + 1} (or 'done'): ")
        if task.lower() == 'done':
            break
        if task:
            new_next_steps.append(task)

    if not new_next_steps:
        print("WARNING: Next Steps list is empty. Aborting checkpoint creation.")
        return

    # 2. Build New Checkpoint Data Structure
    new_checkpoint_data = {
        'project': project_name,
        'timestamp': datetime.datetime.now().isoformat(),  # We need to import datetime!
        'type': 'checkpoint',
        'summary': new_summary,
        'context': {
            'previous_checkpoint_summary': latest_checkpoint_data.get('summary', 'N/A'),
            'previous_next_steps_completed': latest_checkpoint_data.get('next_steps', []),
            # We can assume these are complete
            'next_goal': new_goal
        },
        'decisions': [],  # Left empty for manual population
        'next_steps': new_next_steps
    }

    # 3. Determine New File Name (Must be unique!)
    # We will use the current date and append a count if needed (a simple version)
    base_filename = f"logs/{datetime.date.today().isoformat()}-{project_name}-checkpoint-NEW.yaml"

    # 4. Save the New Checkpoint File
    try:
        with open(base_filename, 'w', encoding='utf-8') as f:
            # Use safe_dump to write the YAML content
            yaml.safe_dump(new_checkpoint_data, f, sort_keys=False, default_flow_style=False)
        print(f"\nSUCCESS: New Checkpoint log created: {base_filename}")
        print("Remember to review and manually fill the 'decisions' field before committing!")

    except Exception as e:
        print(f"ERROR: Failed to save new checkpoint file: {e}")


def main():
    """Main entry point for the checkpoint utility."""
    parser = argparse.ArgumentParser(
        description="Mother AI Project Checkpoint Utility. Manages structured logs and Git flow."
    )

    # --- CLI Arguments ---
    parser.add_argument(
        'action',
        type=str,
        choices=['status', 'new', 'commit'],
        help='The action to perform: check status, create a new checkpoint, or commit the changes.'
    )

    parser.add_argument(
        '--project',
        type=str,
        default='Project_Orchestrator',
        help='The name of the project being worked on (e.g., Project_Orchestrator or discord_ai_bot).'
    )

    args = parser.parse_args()

    print(f"--- Mother AI Checkpoint Utility (Project: {args.project}) ---")

    # 1. Load the Orchestrator's Brain
    orchestrator_brain = read_brain(PROJECT_BRAIN_PATH)
    if not orchestrator_brain:
        print("CRITICAL: Failed to load Orchestrator's brain. Exiting.")
        return

    # 2. Get the specific project file paths
    target_brain_path, target_checkpoint_path = get_project_paths(orchestrator_brain, args.project)

    if not target_brain_path:
        # Error handled in get_project_paths
        return

    # --- Checkpoint Action Logic ---

    # All actions require the target project's current context
    target_checkpoint = read_checkpoint(target_checkpoint_path)

    if args.action == 'status':
        print("\nACTION: Status Check")
        # For status, we confirm both brain and checkpoint loaded successfully (already done above)
        if target_checkpoint:
            print("\nSUCCESS: Target Project Brain and Checkpoint files loaded successfully.")
            print(f"Current Checkpoint Goal: {target_checkpoint.get('context', {}).get('next_goal', 'N/A')}")
        else:
            print("\nSTATUS: Brain is valid, but Checkpoint failed to load.")

    elif args.action == 'new':
        if not target_checkpoint:
            print("Cannot create a new checkpoint: Failed to load latest checkpoint data.")
            return

        # Pass the latest checkpoint data to the builder function
        create_new_checkpoint(args.project, target_checkpoint)

    elif args.action == 'commit':
        print("\nACTION: Commit Checkpoint")

        if target_checkpoint:
            commit_changes(args.project, target_checkpoint)
        else:
            print("Commit aborted: Could not load the latest Checkpoint log to retrieve commit details.")


if __name__ == "__main__":
    # Ensure this script can run from the project root directory
    if os.path.basename(os.getcwd()) != 'project-orchestrator-template':
        print("INFO: Recommended to run this script from the project root directory.")

    # We now call main and wrap in a try/except for unexpected runtime issues
    try:
        main()
    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")
        sys.exit(1)