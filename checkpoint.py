import argparse
import glob
import json
import yaml
import sys
import os
import datetime
import re

# Import the new Git Service (needed for the commit_changes in the CLI main function)
# NOTE: We keep this import here as the CLI entry point (main) is still in this file.
from git_service import commit_changes  # Import the delegated function

# --- Configuration (Dynamic) ---
# The path to the orchestrator's own brain is the only one that remains relatively static.
ORCHESTRATOR_BRAIN_PATH = "brains/Project_Orchestrator/project_orchestrator.brain.v1.json"
ORCHESTRATOR_STATE_PATH = "brains/Project_Orchestrator/project_orchestrator.state.json"
LOGS_DIR = "brains/Project_Orchestrator/logs"

def get_truncated_history(project_name: str, max_logs: int = 5) -> list[dict]:
    """
    Reads recent checkpoint logs, truncates them to a summary,
    and returns a list of dictionaries to manage the AI's context window.
    """

    print(f"INFO: Truncating historical context to the last {max_logs} logs.")
    log_dir = f"brains/{project_name}/logs"
    history = []

    # 1. Find all finalized logs (excluding -NEW.yaml)
    search_pattern = os.path.join(log_dir, f"*-checkpoint-*.yaml")
    log_files = glob.glob(search_pattern)

    # Filter out -NEW.yaml drafts
    finalized_logs = sorted([f for f in log_files if "-NEW.yaml" not in f],
                            key=os.path.getctime, reverse=True)

    # 2. Process only the MAX_LOGS most recent files
    for filepath in finalized_logs:
        if len(history) >= max_logs:
            break

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)

            # 3. Truncate/Summarize the log to only key fields
            # This is the "summarized version" that saves tokens.
            truncated_entry = {
                'id': os.path.basename(filepath),
                'date': data.get('timestamp', 'N/A'),
                'summary': data.get('summary', 'No summary available.'),
                'next_goal': data.get('context', {}).get('next_goal', 'N/A')
            }
            history.append(truncated_entry)

        except Exception as e:
            print(f"WARNING: Skipping corrupted log file {filepath}. Error: {e}")
            continue

    # Return the history in chronological order (oldest first for the AI's flow)
    return history[::-1]

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


def parse_ai_design_content(content: str) -> dict | None:
    """
    Reads the raw text content from the LLM (pasted into the GUI),
    extracts, and validates the JSON (Brain) and YAML (Checkpoint)
    content blocks using robust regex search.
    """
    if not content or content.strip() == "":
        print("ERROR: Design content is empty. Please paste the AI output.")
        return None

    try:
        # 1. FIND and EXTRACT JSON using Regex (most reliable method)
        # Search for: ```json (optional whitespace) { ... } (optional whitespace) ```
        json_pattern = re.compile(r'```json\s*(\{.*?\})\s*```', re.DOTALL)
        json_match = json_pattern.search(content)

        if not json_match:
            print("ERROR: Could not find the JSON block marked by '```json'.")
            return None

        raw_json = json_match.group(1).strip()  # Group 1 is the content inside the braces
        brain_data = json.loads(raw_json)

        # 2. FIND and EXTRACT YAML using Regex
        # Start the search after the JSON block ends
        yaml_search_start_index = json_match.end()
        yaml_pattern = re.compile(r'```yaml\s*(.*?)\s*```', re.DOTALL)
        yaml_match = yaml_pattern.search(content, yaml_search_start_index)

        if not yaml_match:
            print("ERROR: Could not find the YAML block marked by '```yaml'.")
            return None

        raw_yaml = yaml_match.group(1).strip()
        checkpoint_data = yaml.safe_load(raw_yaml)

        # Basic validation check for required data
        if 'project' not in brain_data or 'next_steps' not in checkpoint_data:
            print("ERROR: Parsed design files are missing required 'project' or 'next_steps' keys.")
            return None

        # Return both as a dictionary
        return {
            "brain": brain_data,
            "checkpoint": checkpoint_data
        }

    except json.JSONDecodeError as e:
        print(f"ERROR: Failed to decode the extracted JSON block (Project Brain). Decoding error: {e}")
        return None
    except yaml.YAMLError:
        print("ERROR: Failed to decode the extracted YAML block (Initial Checkpoint).")
        return None
    except Exception as e:
        print(f"CRITICAL ERROR during content parsing: {e}")
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


def read_orchestrator_state(path: str) -> dict | None:
    """Reads the dynamic Orchestrator State JSON file (project list, active_project)."""
    try:
        if not os.path.exists(path):
            # If the state file doesn't exist, create an initial structure
            print("INFO: Orchestrator state file not found. Initializing a new, empty state.")
            return {"managed_projects": {}, "meta": {"active_project": "Project_Orchestrator"}}

        with open(path, 'r', encoding='utf-8') as f:
            state_data = json.load(f)
            # Basic validation
            if 'managed_projects' not in state_data or 'meta' not in state_data:
                print("ERROR: Orchestrator State file is corrupted. Missing required keys.")
                return None
            return state_data

    except json.JSONDecodeError:
        print(f"ERROR: Orchestrator State file at '{path}' is not valid JSON. Check formatting.")
        return None
    except Exception as e:
        print(f"An unexpected error occurred while reading the Orchestrator State: {e}")
        return None


def save_orchestrator_state(path: str, data: dict) -> bool:
    """Saves the dynamic Orchestrator State JSON file."""
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
        return True
    except Exception as e:
        print(f"ERROR: Failed to save Orchestrator State file: {e}")
        return False


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


# --- REMOVED: commit_changes (DELEGATED TO git_service.py) ---

def _get_next_checkpoint_index(project_name: str) -> int:
    """Finds the largest existing checkpoint index and returns the next sequential number."""

    # Updated search pattern to exclude the -NEW.yaml files and target indexed files
    search_pattern = os.path.join(LOGS_DIR, f"*-{project_name}-checkpoint-*.yaml")

    max_index = 0

    for log_file in glob.glob(search_pattern):
        # We only want to process files with a numeric index, not '-NEW'
        if "-NEW.yaml" in log_file:
            continue

        # Regex to find the index (number) right before the '.yaml' extension
        match = re.search(r'-checkpoint-(\d+)\.yaml$', log_file)
        if match:
            current_index = int(match.group(1))
            if current_index > max_index:
                max_index = current_index

    # Checkpoint 0 is the initial log. We start counting at 1 for subsequent logs.
    # The logic correctly returns max_index + 1.
    return max_index + 1


def create_new_checkpoint(project_name: str, latest_checkpoint_data: dict):
    """Interactively creates and saves a new Checkpoint YAML log."""

    print("\nACTION: Creating New Checkpoint Log...")
    current_time = datetime.datetime.now()

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
        'timestamp': current_time.isoformat(),  # Uses full timestamp
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
    file_timestamp = current_time.strftime('%Y-%m-%d-%H%M%S')
    base_filename = f"{LOGS_DIR}/{file_timestamp}-{project_name}-checkpoint-NEW.yaml"

    # 4. Save the New Checkpoint File
    try:
        with open(base_filename, 'w', encoding='utf-8') as f:
            # Use safe_dump to write the YAML content
            yaml.safe_dump(new_checkpoint_data, f, sort_keys=False, default_flow_style=False)
        print(f"\nSUCCESS: New Checkpoint log created: {base_filename}")
        print("Remember to review and manually fill the 'decisions' field before committing!")

    except Exception as e:
        print(f"ERROR: Failed to save new checkpoint file: {e}")


def update_checkpoint_file(project_name: str) -> str or None:
    """
    Finds the latest *-NEW.yaml draft, renames it to the next sequential index,
    and returns the new finalized path. (YAML-STORE)
    """

    # 1. Find the NEW Draft File
    new_draft_pattern = os.path.join(LOGS_DIR, f"*-{project_name}-checkpoint-NEW.yaml")
    new_files = glob.glob(new_draft_pattern)

    if not new_files:
        print("ERROR: Could not find any checkpoint-NEW.yaml draft to finalize.")
        return None

    # Get the most recently modified NEW file
    old_path = max(new_files, key=os.path.getctime)

    # 2. Determine the Next Index
    next_index = _get_next_checkpoint_index(project_name)  # Uses the helper function

    # 3. Define New Name (Replace the '-NEW.yaml' suffix)
    new_path = old_path.replace("-checkpoint-NEW.yaml", f"-checkpoint-{next_index}.yaml")

    # 4. Perform Rename
    try:
        os.rename(old_path, new_path)
        print(f"SUCCESS: Checkpoint finalized and renamed to: {os.path.basename(new_path)}")

        # 5. Load Orchestrator State
        state_data = read_orchestrator_state(ORCHESTRATOR_STATE_PATH)
        if not state_data:
            print("WARNING: State load failed. Cannot update latest_checkpoint path.")
            # Continue running to avoid crashing the whole process
            return new_path

        # 6. Update the 'latest_checkpoint' path
        state_data['managed_projects'][project_name]['latest_checkpoint'] = new_path

        # 7. Save the Orchestrator State
        if save_orchestrator_state(ORCHESTRATOR_STATE_PATH, state_data):
            print("INFO: Orchestrator State updated with new latest_checkpoint path.")
        else:
            print("WARNING: Failed to save Orchestrator State file.")

        # ---------------------------

        print("\nACTION: Please review the finalized file before manually running 'git add' and 'git commit'.")
        return new_path

    except OSError as e:
        print(f"ERROR: Failed to rename the checkpoint file: {e}")
        return None


def create_project(project_name: str, orchestrator_state: dict, orchestrator_state_path: str,
                   design_content: str) -> bool:
    print(f"\nACTION: Scaffolding New Project '{project_name}'...")
    date_stamp = datetime.date.today().isoformat()

    # --- NEW: PARSE THE AI DESIGN FILE ---
    design_data = parse_ai_design_content(design_content)
    if not design_data:
        print("Aborting project creation due to design file errors.")
        return False

    # Validation Check: Ensure the project name in the file matches the command-line argument
    if design_data['brain']['project'] != project_name:
        print(
            f"ERROR: Project name mismatch! Command used '{project_name}', but design file specifies '{design_data['brain']['project']}'. Aborting.")
        return False

    # Get the AI-designed content
    initial_brain_data = design_data['brain']
    initial_log_data = design_data['checkpoint']
    # -------------------------------------

    # 1. Structure Creation (Remains the same)
    project_dir = f"brains/{project_name}"
    project_logs_dir = f"{project_dir}/logs"

    if os.path.exists(project_dir):
        print(f"ERROR: Project directory '{project_dir}' already exists. Aborting creation.")
        return False

    try:
        os.makedirs(project_logs_dir)
        print(f"Created project structure: {project_logs_dir}")
    except OSError as e:
        print(f"CRITICAL ERROR: Failed to create directories: {e}")
        return False

    # Define paths
    brain_filename = f"{project_name}.brain.v1.json"
    brain_path = f"{project_dir}/{brain_filename}"
    checkpoint_filename = f"{date_stamp}-checkpoint-0.yaml"
    checkpoint_path = f"{project_logs_dir}/{checkpoint_filename}"  # We use '0' since it's the start

    # 2. Project Brain File Generation (v1) - USE AI-GENERATED CONTENT
    try:
        with open(brain_path, 'w', encoding='utf-8') as f:
            json.dump(initial_brain_data, f, indent=4)  # Use AI-provided data
        print(f"Created initial Project Brain file using AI design: {brain_path}")
    except Exception as e:
        print(f"ERROR: Failed to write brain file: {e}")
        return False

    # 3. Initial Checkpoint Log (Checkpoint 0) - USE AI-GENERATED CONTENT
    try:
        # Before saving, we must ensure the placeholder timestamp is replaced with the actual timestamp
        if initial_log_data.get('timestamp') == '[SET CURRENT DATETIME]':
            initial_log_data['timestamp'] = datetime.datetime.now().isoformat()

        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            yaml.safe_dump(initial_log_data, f, sort_keys=False, default_flow_style=False)  # Use AI-provided data
        print(f"Created initial Checkpoint Log (Checkpoint 0) using AI design: {checkpoint_path}")
    except Exception as e:
        print(f"ERROR: Failed to write initial checkpoint: {e}")
        return False

    # 4. Mother AI State Update (CRITICAL STEP)
    orchestrator_data = orchestrator_state

    if 'managed_projects' not in orchestrator_data:
        orchestrator_data['managed_projects'] = {}

    orchestrator_data['managed_projects'][project_name] = {
        "status": "initialized",
        "current_version": "v1.0",
        "brain_path": brain_path,
        "latest_checkpoint": checkpoint_path
    }
    orchestrator_data['meta']['active_project'] = project_name

    if not save_orchestrator_state(orchestrator_state_path, orchestrator_data):
        return False  # Abort if save fails
    print(f"Updated Mother AI state with new project and set active_project.")

    # 5. Mother AI Checkpoint & Commit (LOGGING ONLY - actual Git commit is separate)
    # We will log a simple note for the orchestrator's own context.
    print("SUCCESS: Project scaffolding complete.")
    print(f"Next step: Run 'python checkpoint.py commit --project {project_name}' to record changes.")
    return True


def main():
    """Main entry point for the checkpoint utility."""

    parser = argparse.ArgumentParser(
        description="Mother AI Project Checkpoint Utility. Manages structured logs and Git flow."
    )

    # --- CLI Arguments ---
    parser.add_argument(
        'action',
        type=str,
        choices=['status', 'new', 'commit', 'create', 'revert', 'update'],
        help='The action to perform: check status, create a new project, create a new checkpoint, or commit the changes.'
    )

    parser.add_argument(
        '--project',
        type=str,
        default='Project_Orchestrator',
        help='The name of the project being worked on.'
    )

    parser.add_argument(
        '--design-file',
        type=str,
        # Only required when the action is 'create'
        help='[Required for "create" action] Path to the file containing the AI-generated project brain and initial checkpoint content.'
    )

    args = parser.parse_args()

    # --- INPUT VALIDATION ---
    # Add a check to ensure --design-file is provided when 'create' is used
    if args.action == 'create' and not args.design_file:
        print("ERROR: The 'create' action requires the '--design-file' argument.")
        sys.exit(1)

    if args.action == 'update':
        # Simply call the update logic and exit, as its job is done.
        update_checkpoint_file(args.project)
        return  # ***CRITICAL: Exit main() after update is done***

    print(f"--- Mother AI Checkpoint Utility (Project: {args.project}) ---")

    # 1. Load the Orchestrator's Brain (for logic/instructions)
    orchestrator_brain = read_brain(ORCHESTRATOR_BRAIN_PATH)
    if not orchestrator_brain:
        print("CRITICAL: Failed to load Orchestrator's brain. Exiting.")
        return

    # 2. Load the Orchestrator's State (for managed projects list)
    orchestrator_state = read_orchestrator_state(ORCHESTRATOR_STATE_PATH)
    if not orchestrator_state:
        print("CRITICAL: Failed to load Orchestrator's state. Exiting.")
        return

    if args.action == 'create':
        if args.project == 'Project_Orchestrator':
            print("ERROR: Cannot 'create' the orchestrator project itself. Use a specific project name.")
            return

    # 3. Get the specific project file paths
    target_brain_path, target_checkpoint_path = get_project_paths(orchestrator_state, args.project)

    if not target_brain_path:
        # Error handled in get_project_paths (project not found)
        return

    # All actions require the target project's current context
    target_checkpoint = read_checkpoint(target_checkpoint_path)

    if args.action == 'status':
        print("\nACTION: Status Check")
        # Status logic remains the same.

    elif args.action == 'new':
        if not target_checkpoint:
            print("Cannot create a new checkpoint: Failed to load latest checkpoint data.")
            return
        create_new_checkpoint(args.project, target_checkpoint)

    elif args.action == 'commit':
        print("\nACTION: Commit Checkpoint (Delegated to Git Service)")
        # We need to read the latest summary from the checkpoint for the commit message
        latest_checkpoint_data = read_checkpoint(target_checkpoint_path)
        if not latest_checkpoint_data:
            print("Commit aborted: Could not load the latest Checkpoint log to retrieve summary.")
            return

        commit_summary = latest_checkpoint_data.get('summary', 'Automated Checkpoint.')

        # --- NEW: Call the Git Service ---
        commit_changes(args.project, commit_summary)


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