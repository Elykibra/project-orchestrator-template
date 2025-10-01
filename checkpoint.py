import argparse
import json
import yaml
import sys
import os

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

    # 1. Load the Orchestrator's Brain to find file paths
    orchestrator_brain = read_brain(PROJECT_BRAIN_PATH)
    if not orchestrator_brain:
        print("CRITICAL: Failed to load Orchestrator's brain. Exiting.")
        return

    # 2. Get the specific project file paths based on CLI argument
    target_brain_path, target_checkpoint_path = get_project_paths(orchestrator_brain, args.project)

    if not target_brain_path:
        # Error message handled in get_project_paths
        return

    if args.action == 'status':
        print("\nACTION: Status Check")

        # --- Core Logic Execution (Using dynamic paths) ---
        target_brain = read_brain(target_brain_path)

        if target_brain:
            target_checkpoint = read_checkpoint(target_checkpoint_path)

            if target_checkpoint:
                print("\nSUCCESS: Target Project Brain and Checkpoint files loaded successfully.")
                print(f"Current Checkpoint Goal: {target_checkpoint.get('context', {}).get('goal', 'N/A')}")
            else:
                print("\nSTATUS: Target Brain is valid, but Checkpoint failed to load.")


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