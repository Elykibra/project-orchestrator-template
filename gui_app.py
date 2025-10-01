import tkinter as tk
from tkinter import messagebox, filedialog
import os
import sys

# Add the project directory to the path so we can import checkpoint.py
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the necessary functions from your core utility
# NOTE: We can't use 'main()' as it contains the argparse logic
from checkpoint import (
    read_orchestrator_state,
    read_checkpoint,
    get_project_paths,
    create_new_checkpoint,
    commit_changes  # We'll just define the path constants here for simplicity
)

# Constants (Copied from checkpoint.py)
ORCHESTRATOR_STATE_PATH = "brains/Project_Orchestrator/project_orchestrator.state.json"


class OrchestratorGUI:
    def __init__(self, master):
        self.master = master
        master.title("Mother AI Project Orchestrator")
        master.geometry("500x350")

        self.project_name = tk.StringVar(master, value="Project_Orchestrator")  # Default project

        # --- UI Elements ---

        tk.Label(master, text="Project Name:").pack(pady=5)
        self.project_entry = tk.Entry(master, textvariable=self.project_name, width=40)
        self.project_entry.pack(pady=5)

        # Frame for buttons
        button_frame = tk.Frame(master)
        button_frame.pack(pady=10)

        # 1. Status Button
        tk.Button(button_frame, text="1. Get Project Status", command=self.run_status).pack(side=tk.LEFT, padx=10)

        # 2. New Checkpoint Button (Launches a new window for input)
        tk.Button(button_frame, text="2. Create New Checkpoint", command=self.launch_new_checkpoint_window).pack(
            side=tk.LEFT, padx=10)

        # 3. Commit Button
        tk.Button(button_frame, text="3. Commit Changes", command=self.run_commit).pack(side=tk.LEFT, padx=10)

        # 4. Create Project (File Selection)
        tk.Button(master, text="4. Scaffold NEW Project (Requires File)", command=self.run_create).pack(pady=10)

        # Status Label
        self.status_label = tk.Label(master, text="Ready.", fg="blue")
        self.status_label.pack(pady=20)

    def _get_project_context(self):
        """Internal helper to load state and paths."""
        proj_name = self.project_name.get()
        state_data = read_orchestrator_state(ORCHESTRATOR_STATE_PATH)
        if not state_data:
            return None, None, None

        # Use existing function to get the paths
        brain_path, checkpoint_path = get_project_paths(state_data, proj_name)

        if not brain_path:
            messagebox.showerror("Error", f"Project '{proj_name}' not found in state file.")
            return None, None, None

        return proj_name, brain_path, checkpoint_path

    def run_status(self):
        """Simulates the 'status' command by calling core functions."""
        proj_name, brain_path, checkpoint_path = self._get_project_context()
        if not proj_name:
            return

        latest_checkpoint = read_checkpoint(checkpoint_path)

        if latest_checkpoint:
            next_task = latest_checkpoint.get('next_steps', ['[Check file]'])[0]
            messagebox.showinfo(
                "Project Status",
                f"Project: {proj_name}\nLatest Checkpoint: {os.path.basename(checkpoint_path)}\nNEXT TASK: {next_task}"
            )
        else:
            messagebox.showerror("Error", "Failed to load latest checkpoint data.")

    def run_commit(self):
        """Simulates the 'commit' command."""
        proj_name, _, checkpoint_path = self._get_project_context()
        if not proj_name:
            return

        # NOTE: This uses the existing CLI function commit_changes, which will print to console
        self.status_label.config(text="Running Git Commit and Push... Check console for details.", fg='orange')
        commit_changes(proj_name, checkpoint_path)
        self.status_label.config(text="Commit/Push complete. Check repository.", fg='green')

    def run_create(self):
        """Simulates the 'create' command using a file dialog."""
        proj_name = self.project_name.get()
        if proj_name == "Project_Orchestrator":
            messagebox.showerror("Error", "Cannot create the orchestrator project itself.")
            return

        # Use Tkinter's file dialog to select the AI output file
        design_file_path = filedialog.askopenfilename(
            title="Select AI Design File (ai_design.txt)",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*"))
        )

        if design_file_path:
            self.status_label.config(text=f"Creating Project '{proj_name}'...", fg='orange')
            # Since create_project uses external functions, we need to pass everything it needs
            from checkpoint import create_project  # Import here to avoid circular dependency issues
            state_data = read_orchestrator_state(ORCHESTRATOR_STATE_PATH)

            success = create_project(proj_name, state_data, ORCHESTRATOR_STATE_PATH, design_file_path)

            if success:
                self.status_label.config(text=f"SUCCESS: Project '{proj_name}' scaffolded!", fg='green')
            else:
                self.status_label.config(text="ERROR: Check the terminal for project creation details.", fg='red')
        else:
            self.status_label.config(text="Creation cancelled.", fg='black')

    def launch_new_checkpoint_window(self):
        """Launches a secondary window for gathering interactive 'new' checkpoint input."""
        proj_name, _, checkpoint_path = self._get_project_context()
        if not proj_name:
            return

        # NOTE: Since the original create_new_checkpoint uses input(),
        # this is where you would rewrite that function or pass a mock input
        # handler. For now, we'll demonstrate the new window idea.

        # This is for demonstration. A full implementation requires rewriting
        # checkpoint.create_new_checkpoint to accept arguments instead of input().
        messagebox.showinfo("New Checkpoint",
                            "This would launch a new window with text fields to gather the Summary and Next Steps, replacing the terminal 'input()' prompts.")


if __name__ == "__main__":
    # Ensure all paths start relative to the project root
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    root = tk.Tk()
    app = OrchestratorGUI(root)
    root.mainloop()