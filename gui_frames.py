# gui_frames.py
# Contains all the visual frame classes (Views) and the ReviewDialog.

import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk, Toplevel
import os
import sys
import yaml
import glob
import datetime
import threading
import rcs_service

# Import constants and local modules
from checkpoint import read_checkpoint, read_orchestrator_state, create_project, update_checkpoint_file
from git_service import commit_changes as git_commit_changes  # NEW: Import the delegated commit function
from gui_constants import BG_DARK, CARD_DARK, FG_DARK, ACCENT_BLUE, SUCCESS_GREEN, ERROR_RED, LOGS_DIR


# ====================================================================
# HELPER FUNCTION FOR RESILIENT FALLBACK LOGGING (NEW)
# ====================================================================

def _get_ai_content_or_fail(data_dict: dict, key: str, failure_message):
    """
    Retrieves content from the AI dictionary. If content is missing, None, empty string,
    or empty list, it returns the explicit failure message for auditing.
    """
    content = data_dict.get(key)

    # Check if content is provided and non-empty
    if content and (isinstance(content, str) and content.strip()) or \
            (isinstance(content, list) and len(content) > 0):
        return content

    # Return explicit failure message for auditing
    return failure_message

# ====================================================================
# REVIEW DIALOG (MODAL)
# ====================================================================

class ReviewDialog(Toplevel):
    def __init__(self, parent, controller, draft_path):
        super().__init__(parent)
        self.controller = controller
        self.draft_path = draft_path

        self.title("Review & Finalize Checkpoint")
        self.geometry("700x550")
        self.configure(bg=BG_DARK)
        self.transient(parent)
        self.grab_set()

        try:
            with open(draft_path, 'r', encoding='utf-8') as f:
                self.draft_data = yaml.safe_load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Could not read draft file: {e}", parent=self)
            self.destroy()
            return

        self._setup_widgets()

    def _setup_widgets(self):
        main_frame = ttk.Frame(self, style="Card.TFrame", padding=20)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        ttk.Label(main_frame, text="Review Draft", style="Header.TLabel", background=CARD_DARK).pack(anchor="w")
        ttk.Label(main_frame, text="Edit the 'Decisions' field below, then finalize.", style="Card.TLabel").pack(
            anchor="w", pady=(0, 15))

        # --- Display Fields (Read-Only) ---
        self._create_display_field(main_frame, "Summary:", self.draft_data.get('summary', ''))
        self._create_display_field(main_frame, "Next Goal:", self.draft_data.get('context', {}).get('next_goal', ''))
        self._create_display_field(main_frame, "Tasks:", "\n".join(self.draft_data.get('next_steps', [])))

        # --- Decisions Field (Editable) ---
        ttk.Label(main_frame, text="Decisions:", style="CardHeader.TLabel").pack(anchor="w", pady=(10, 5))
        self.decisions_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, height=8, background=BG_DARK,
                                                        foreground=FG_DARK, font=self.controller.default_font)
        self.decisions_text.pack(fill="both", expand=True, pady=5)
        decisions_list = self.draft_data.get('decisions', [])
        self.decisions_text.insert("1.0", "\n".join(decisions_list))

        # --- Action Button ---
        finalize_btn = ttk.Button(main_frame, text="Save & Finalize", style="Accent.TButton",
                                  command=self.save_and_finalize)
        finalize_btn.pack(side="right", pady=10)

    def _create_display_field(self, parent, label_text, value_text):
        frame = ttk.Frame(parent, style="Card.TFrame")
        frame.pack(fill="x", pady=2)
        ttk.Label(frame, text=label_text, style="CardHeader.TLabel").pack(side="left", padx=(0, 10), anchor='n')
        ttk.Label(frame, text=value_text, style="Card.TLabel", wraplength=500, justify=tk.LEFT).pack(side="left",
                                                                                                     fill='x',
                                                                                                     expand=True)

    def save_and_finalize(self):
        decisions_raw = self.decisions_text.get("1.0", tk.END).strip()
        self.draft_data['decisions'] = [line.strip() for line in decisions_raw.split('\n') if line.strip()]

        try:
            with open(self.draft_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(self.draft_data, f, sort_keys=False, default_flow_style=False)
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save changes to draft file: {e}", parent=self)
            return

        proj_name = self.draft_data.get('project')
        new_path = update_checkpoint_file(proj_name)
        if new_path:
            messagebox.showinfo("Success", f"Checkpoint finalized successfully!", parent=self)
            self.controller.frames["CheckpointFrame"].on_show()
            self.destroy()
        else:
            messagebox.showerror("Finalization Failed",
                                 "Could not finalize the checkpoint. Check the console for details.", parent=self)


# ====================================================================
# BASE FRAME
# ====================================================================
class BaseFrame(ttk.Frame):
    def __init__(self, parent, controller):
        super().__init__(parent, style="TFrame")
        self.controller = controller
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

    def on_show(self):
        pass


# ====================================================================
# DASHBOARD VIEW
# ====================================================================
class DashboardFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # --- Status Panel ---
        status_panel = ttk.Frame(self, style="Card.TFrame", padding=20)
        status_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)

        ttk.Label(status_panel, text="Project Status", style="Header.TLabel", background=CARD_DARK).pack(anchor="w",
                                                                                                         pady=(0, 15))
        self.project_selector = ttk.Combobox(status_panel, textvariable=self.controller.current_project,
                                             font=self.controller.default_font, state='readonly')
        self.project_selector.pack(fill="x", pady=(0, 10))
        self.project_selector.bind("<<ComboboxSelected>>", self.on_project_change)

        ttk.Label(status_panel, text="Next Goal:", style="CardHeader.TLabel").pack(anchor="w", pady=(10, 5))
        self.goal_label = ttk.Label(status_panel, text="...", wraplength=400, style="Card.TLabel")
        self.goal_label.pack(fill="x", anchor="w")

        ttk.Label(status_panel, text="Next Tasks:", style="CardHeader.TLabel").pack(anchor="w", pady=(10, 5))
        self.tasks_text = tk.Text(status_panel, wrap=tk.WORD, height=8, background=BG_DARK, foreground=FG_DARK,
                                  font=self.controller.default_font, relief="flat")
        self.tasks_text.pack(fill="both", expand=True)

        # --- File Explorer Panel ---
        explorer_panel = ttk.Frame(self, style="Card.TFrame", padding=20)
        explorer_panel.grid(row=0, column=1, sticky="nsew", pady=10)
        ttk.Label(explorer_panel, text="Project Files", style="Header.TLabel", background=CARD_DARK).pack(anchor="w",
                                                                                                          pady=(0, 15))
        self.file_tree = ttk.Treeview(explorer_panel, show="tree")
        self.file_tree.pack(fill="both", expand=True)

    def on_show(self):
        self.load_project_list()
        self.display_status()
        self.populate_file_tree()

    def on_project_change(self, event=None):
        self.display_status()
        self.populate_file_tree()

    def load_project_list(self):
        try:
            state_data = read_orchestrator_state(self.controller.ORCHESTRATOR_STATE_PATH)
            projects = list(state_data.get('managed_projects', {}).keys())
            self.project_selector['values'] = projects
            if self.controller.current_project.get() not in projects:
                self.controller.current_project.set(projects[0] if projects else "")
        except Exception as e:
            print(f"WARNING: Could not load project list: {e}")

    def display_status(self):
        self.tasks_text.config(state=tk.NORMAL)
        self.tasks_text.delete("1.0", tk.END)
        proj_name, _, _, checkpoint_path = self.controller.get_project_context()
        if not checkpoint_path:
            self.goal_label.config(text="Project not found or configuration error.")
        else:
            latest_checkpoint = read_checkpoint(checkpoint_path)
            if latest_checkpoint:
                goal = latest_checkpoint.get("context", {}).get("next_goal", "No goal defined.")
                self.goal_label.config(text=goal)
                steps = latest_checkpoint.get("next_steps", [])
                self.tasks_text.insert("1.0", "- " + "\n- ".join(steps) if steps else "Checkpoint complete.")
            else:
                self.goal_label.config(text=f"Could not load checkpoint for '{proj_name}'.")
        self.tasks_text.config(state=tk.DISABLED)

    def populate_file_tree(self):
        for i in self.file_tree.get_children():
            self.file_tree.delete(i)

        proj_name = self.controller.current_project.get()
        if not proj_name or proj_name == "PROJECT_ERROR": return

        root_path = f"brains/{proj_name}"
        if not os.path.isdir(root_path): return

        root_node = self.file_tree.insert('', 'end', text=proj_name, open=True)
        self._process_directory(root_node, root_path)

    def _process_directory(self, parent, path):
        for p in sorted(os.listdir(path)):
            abs_path = os.path.join(path, p)
            is_dir = os.path.isdir(abs_path)
            node = self.file_tree.insert(parent, 'end', text=p, open=False)
            if is_dir:
                self._process_directory(node, abs_path)


# ====================================================================
# HISTORY VIEW
# ====================================================================
class HistoryFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=3)

        list_panel = ttk.Frame(self, style="Card.TFrame", padding=20)
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10), pady=10)
        ttk.Label(list_panel, text="Checkpoint Logs", style="Header.TLabel", background=CARD_DARK).pack(anchor="w",
                                                                                                        pady=(0, 15))
        self.log_listbox = tk.Listbox(list_panel, background=BG_DARK, foreground=FG_DARK,
                                      font=self.controller.default_font, relief="flat", selectbackground=ACCENT_BLUE)
        self.log_listbox.pack(fill="both", expand=True)
        self.log_listbox.bind("<<ListboxSelect>>", self.on_log_select)

        content_panel = ttk.Frame(self, style="Card.TFrame", padding=20)
        content_panel.grid(row=0, column=1, sticky="nsew", pady=10)
        ttk.Label(content_panel, text="Log Content", style="Header.TLabel", background=CARD_DARK).pack(anchor="w",
                                                                                                       pady=(0, 15))
        self.content_text = scrolledtext.ScrolledText(content_panel, wrap=tk.WORD, background=BG_DARK,
                                                      foreground=FG_DARK, font=self.controller.default_font,
                                                      state=tk.DISABLED)
        self.content_text.pack(fill="both", expand=True)

    def on_show(self):
        self.populate_log_list()
        self.content_text.config(state=tk.NORMAL)
        self.content_text.delete("1.0", tk.END)
        self.content_text.insert("1.0", "Select a checkpoint log from the list to view its contents.")
        self.content_text.config(state=tk.DISABLED)

    def populate_log_list(self):
        self.log_listbox.delete(0, tk.END)
        proj_name = self.controller.current_project.get()
        if not proj_name or proj_name == "PROJECT_ERROR": return

        log_dir = f"brains/{proj_name}/logs"
        if not os.path.isdir(log_dir): return

        for filename in sorted(os.listdir(log_dir), reverse=True):
            if filename.endswith(".yaml") and "-NEW" not in filename:
                self.log_listbox.insert(tk.END, filename)

    def on_log_select(self, event=None):
        selected_indices = self.log_listbox.curselection()
        if not selected_indices: return

        filename = self.log_listbox.get(selected_indices[0])
        proj_name = self.controller.current_project.get()
        filepath = os.path.join(f"brains/{proj_name}/logs", filename)

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            self.content_text.config(state=tk.NORMAL)
            self.content_text.delete("1.0", tk.END)
            self.content_text.insert("1.0", content)
            self.content_text.config(state=tk.DISABLED)
        except Exception as e:
            print(f"ERROR: Could not read log file '{filepath}': {e}")


# ====================================================================
# CHECKPOINT VIEW
# ====================================================================
class CheckpointFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)

        main_card = ttk.Frame(self, style="Card.TFrame", padding=20)
        main_card.grid(row=0, column=0, sticky="nsew", pady=10)

        ttk.Label(main_card, text="Create New Checkpoint", style="Header.TLabel", background=CARD_DARK).pack(anchor="w",
                                                                                                             pady=(0,
                                                                                                                   15))

        ttk.Label(main_card, text="Summary of Work Completed:", style="CardHeader.TLabel").pack(anchor="w")
        self.summary_entry = ttk.Entry(main_card, width=80, font=self.controller.default_font)
        self.summary_entry.pack(fill="x", pady=5)

        ttk.Label(main_card, text="Overall Goal for NEXT Checkpoint:", style="CardHeader.TLabel").pack(anchor="w",
                                                                                                       pady=(10, 0))
        self.goal_entry = ttk.Entry(main_card, width=80, font=self.controller.default_font)
        self.goal_entry.pack(fill="x", pady=5)

        ttk.Label(main_card, text="Next Tasks (one per line):", style="CardHeader.TLabel").pack(anchor="w",
                                                                                                pady=(10, 0))
        self.next_steps_text = scrolledtext.ScrolledText(main_card, wrap=tk.WORD, height=6, background=BG_DARK,
                                                         foreground=FG_DARK, font=self.controller.default_font)
        self.next_steps_text.pack(fill="both", expand=True, pady=5)

        self.create_draft_button = ttk.Button(main_card, text="Create Draft & Review (AUTO)", command=self.create_draft,
                                              style="Accent.TButton")
        self.create_draft_button.pack(pady=10, anchor="e")

        self.draft_status_label = ttk.Label(main_card, text="Checking for pending drafts...", style="Card.TLabel")
        self.draft_status_label.pack(pady=5, anchor="w")

    def on_show(self):
        self.check_draft_status()
        self.update_ui_mode()

    def update_ui_mode(self):
        status = self.controller.api_status_var.get()
        # Reset colors/styles
        self.create_draft_button.config(style='Accent.TButton', state=tk.NORMAL)

        if "AUTO" in status:
            self.create_draft_button.config(text="Create Draft & Review (AUTO)")
            self.summary_entry.config(state=tk.DISABLED)
            self.goal_entry.config(state=tk.DISABLED)
            self.next_steps_text.config(state=tk.DISABLED)
            # Clear fields in AUTO mode
            self.summary_entry.delete(0, tk.END)
            self.goal_entry.delete(0, tk.END)
            self.next_steps_text.delete("1.0", tk.END)

        elif "MANUAL" in status:
            self.create_draft_button.config(text="Create Draft & Review (MANUAL)", style='Error.TButton')
            self.summary_entry.config(state=tk.NORMAL)
            self.goal_entry.config(state=tk.NORMAL)
            self.next_steps_text.config(state=tk.NORMAL)
            # Prompt the user for manual entry with a guiding template
            if not self.summary_entry.get().strip():
                self.summary_entry.insert(0, "# Paste Web Gemini Summary Here")
            if not self.next_steps_text.get("1.0", tk.END).strip():
                self.next_steps_text.insert("1.0",
                                            "- Task 1: (e.g., Implement function X)\n- Task 2: (e.g., Write unit test for Y)")

    def check_draft_status(self):
        proj_name = self.controller.current_project.get()
        if not proj_name or proj_name == "PROJECT_ERROR": return

        new_draft_pattern = os.path.join(LOGS_DIR, f"*-{proj_name}-checkpoint-NEW.yaml")
        new_files = glob.glob(new_draft_pattern)

        if new_files:
            self.draft_status_label.config(
                text=f"A draft checkpoint is pending finalization. Please resolve it before creating a new one.",
                style='Card.TLabel')
            self.create_draft_button.config(state=tk.DISABLED)
        else:
            self.draft_status_label.config(text="Ready to create a new draft checkpoint.", style='Success.TLabel')
            self.create_draft_button.config(
                state=tk.NORMAL if "CHECKING" not in self.controller.api_status_var.get() else tk.DISABLED)

    def create_draft(self):
        proj_name, _, _, checkpoint_path = self.controller.get_project_context()
        if not checkpoint_path:
            messagebox.showerror("Error", "Cannot create draft. No valid project context found.")
            return

        latest_checkpoint_data = read_checkpoint(checkpoint_path)
        if not latest_checkpoint_data: return

        summary = self.summary_entry.get().strip()
        goal = self.goal_entry.get().strip()
        steps_raw = self.next_steps_text.get("1.0", tk.END).strip()
        next_steps = [line.strip() for line in steps_raw.split('\n') if line.strip()]

        if self.controller.api_status_var.get() == "🔴 MANUAL":
            if not all([summary, goal, next_steps]):
                messagebox.showerror("Error",
                                     "All manual fields (Summary, Goal, Tasks) are required when in MANUAL mode.")
                return

            print("Executing MANUAL mode using user-provided input.")
            new_checkpoint_data = {
                'project': proj_name, 'timestamp': datetime.datetime.now().isoformat(), 'type': 'checkpoint',
                'summary': summary,
                'context': {'previous_checkpoint_summary': latest_checkpoint_data.get('summary', 'N/A'),
                            'previous_next_steps_completed': latest_checkpoint_data.get('next_steps', []),
                            'next_goal': goal},
                'decisions': ["TODO: Fill this in during the review step."],
                'next_steps': next_steps
            }
            self._save_draft_and_open_review(new_checkpoint_data)
            return

        print("Attempting AUTO mode using multi-API fallback...")

        # The build_checkpoint_prompt now generates the unified JSON prompt
        context_prompt = self.controller.build_checkpoint_prompt(proj_name, checkpoint_path)

        # --- NEW: Print the Full Prompt to the Console/Terminal ---
        # The prompt now contains the Unified Context JSON
        print("\n--- AI Checkpoint Prompt (Unified Context JSON) ---")
        print(context_prompt)
        print("--------------------------------------\n")
        # --------------------------------------------------------
        self.create_draft_button.config(text="Generating...", state=tk.DISABLED)

        def run_api_draft_worker():
            from ai_service import get_ai_checkpoint_draft
            ai_draft_data = get_ai_checkpoint_draft(context_prompt)

            self.controller.master.after(0, lambda: self._handle_api_response(
                ai_draft_data, proj_name, latest_checkpoint_data))

        threading.Thread(target=run_api_draft_worker, daemon=True).start()
        return

    def _handle_api_response(self, ai_draft_data, proj_name, latest_checkpoint_data):
        # We call update_ui_mode() later to ensure the button re-enables correctly

        if ai_draft_data is None:
            self.controller.api_status_var.set("🔴 MANUAL")
            self.update_ui_mode()  # Now update UI immediately after setting MANUAL status
            messagebox.showerror("API ERROR",
                                 "All API tiers exhausted. Please use manual mode (fill fields above) and try the automatic check again later.")
            return

        # --- CRITICAL FIX: Use the helper function for Auditable Failure Logging ---
        new_checkpoint_data = {
            'project': proj_name,
            'timestamp': datetime.datetime.now().isoformat(),
            'type': 'checkpoint',
            'summary': _get_ai_content_or_fail(
                ai_draft_data, 'summary', 'AI FAILED TO GENERATE SUMMARY. Review Prompt/Context.'
            ),
            'context': {
                'previous_checkpoint_summary': latest_checkpoint_data.get('summary', 'N/A'),
                'previous_next_steps_completed': latest_checkpoint_data.get('next_steps', []),
                'next_goal': _get_ai_content_or_fail(
                    ai_draft_data, 'next_goal', 'AI FAILED TO GENERATE NEXT GOAL. Review Prompt/Context.'
                )
            },
            'decisions': _get_ai_content_or_fail(
                ai_draft_data, 'decisions', ["AI FAILED TO SUGGEST DECISIONS."]
            ),
            'next_steps': _get_ai_content_or_fail(
                ai_draft_data, 'next_steps', ['AI FAILED TO GENERATE NEXT TASKS.']
            )
        }
        # --------------------------------------------------------------------------

        self.update_ui_mode()
        self._save_draft_and_open_review(new_checkpoint_data)

        # CRITICAL STEP: Hook for RCS to run in the background
        # Note: We pass the checkpoint_data dictionary, which has the summary/goal data.
        threading.Thread(target=rcs_service.process_reflection,
                         args=(proj_name, new_checkpoint_data),
                         daemon=True).start()

    def _save_draft_and_open_review(self, new_checkpoint_data):
        proj_name = new_checkpoint_data.get('project')
        file_timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
        filename = os.path.join(LOGS_DIR, f"{file_timestamp}-{proj_name}-checkpoint-NEW.yaml")

        try:
            # This step converts the JSON-OUT data dictionary back to a YAML file (YAML-STORE)
            with open(filename, 'w', encoding='utf-8') as f:
                yaml.safe_dump(new_checkpoint_data, f, sort_keys=False, default_flow_style=False)

            print(f"Draft created: {os.path.basename(filename)}")
            self.summary_entry.delete(0, tk.END)
            self.goal_entry.delete(0, tk.END)
            self.next_steps_text.delete("1.0", tk.END)
            self.check_draft_status()
            ReviewDialog(self.master, self.controller, filename)

        except Exception as e:
            print(f"ERROR: Failed to save new checkpoint file: {e}")


# ====================================================================
# Other Frames (New Project, Commit)
# ====================================================================
class NewProjectFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        main_card = ttk.Frame(self, style="Card.TFrame", padding=20)
        main_card.grid(row=0, column=0, sticky="nsew", pady=10)
        ttk.Label(main_card, text="Scaffold New Project", style="Header.TLabel", background=CARD_DARK).pack(
            pady=(0, 20), anchor="w")
        ttk.Label(main_card, text="Project Name:", style="CardHeader.TLabel").pack(pady=5, anchor="w")
        self.proj_name_entry = ttk.Entry(main_card, width=50, font=self.controller.default_font)
        self.proj_name_entry.pack(fill="x", pady=5)
        ttk.Label(main_card, text="Paste AI Design Content:", style="CardHeader.TLabel").pack(pady=5, anchor="w")
        self.design_text_widget = scrolledtext.ScrolledText(main_card, wrap=tk.WORD, width=70, height=15,
                                                            background=BG_DARK, foreground=FG_DARK,
                                                            font=self.controller.default_font)
        self.design_text_widget.pack(fill="both", expand=True, pady=10)
        ttk.Button(main_card, text="Scaffold Project", command=self.scaffold_project, style="Accent.TButton").pack(
            pady=10, anchor="e")

    def scaffold_project(self):
        proj_name = self.proj_name_entry.get().strip()
        design_content = self.design_text_widget.get("1.0", tk.END).strip()
        if not proj_name or not design_content:
            messagebox.showerror("Error", "Project Name and design content are required.")
            return
        state_data = read_orchestrator_state(self.controller.ORCHESTRATOR_STATE_PATH)
        if create_project(proj_name, state_data, self.controller.ORCHESTRATOR_STATE_PATH, design_content):
            self.controller.current_project.set(proj_name)
            self.controller.show_frame("DashboardFrame")
        else:
            messagebox.showerror("Error", "Project creation failed. Check the console for details.")


class CommitFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        main_card = ttk.Frame(self, style="Card.TFrame", padding=20)
        main_card.grid(row=0, column=0, sticky="nsew", pady=10)
        ttk.Label(main_card, text="Commit & Push Changes", style="Header.TLabel", background=CARD_DARK).pack(
            pady=(0, 20), anchor="w")
        ttk.Label(main_card,
                  text="This will stage all changes and commit them using the latest finalized checkpoint summary.",
                  wraplength=600, style="Card.TLabel").pack(pady=20)
        ttk.Button(main_card, text="Run Commit & Push", command=self.run_commit_action, style="Accent.TButton").pack(
            pady=20)

    def run_commit_action(self):
        proj_name, _, _, checkpoint_path = self.controller.get_project_context()
        if proj_name == "Project_Orchestrator":
            messagebox.showwarning("Action Blocked",
                                   "Committing the Orchestrator project via the GUI is disabled for safety.")
            return
        if not checkpoint_path:
            messagebox.showerror("Error", f"Could not find checkpoint path for {proj_name}.")
            return

        # 1. Get the summary from the latest checkpoint
        latest_checkpoint = read_checkpoint(checkpoint_path)
        if not latest_checkpoint:
            messagebox.showerror("Error", f"Could not load the latest checkpoint summary.")
            return

        commit_summary = latest_checkpoint.get('summary', 'Automated Checkpoint.')

        if messagebox.askyesno("Confirm Commit",
                               f"Are you sure you want to commit and push changes for '{proj_name}'?\n\nCommit Message: {commit_summary}"):
            # 2. Call the DELEGATED Git Service function
            git_commit_changes(proj_name, commit_summary)