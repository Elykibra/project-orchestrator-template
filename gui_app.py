import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk, Toplevel
import os
import sys
import json
import datetime
import yaml
import glob
from ttkthemes import ThemedTk

# --- Setup path to import checkpoint.py ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from checkpoint import (
    read_orchestrator_state,
    read_checkpoint,
    get_project_paths,
    create_project,
    commit_changes,
    update_checkpoint_file,
)

# --- UI Constants ---
BG_DARK = '#111827'
CARD_DARK = '#1F2937'
FG_DARK = '#E5E7EB'
ACCENT_BLUE = '#3B82F6'
ACCENT_BLUE_ACTIVE = '#2563EB'
BORDER_DARK = '#374151'
SUCCESS_GREEN = '#10B981'
ERROR_RED = '#EF4444'

# --- File Path Constants ---
ORCHESTRATOR_STATE_PATH = "brains/Project_Orchestrator/project_orchestrator.state.json"
LOGS_DIR = "brains/Project_Orchestrator/logs"


# ====================================================================
# CONSOLE REDIRECTION CLASS
# ====================================================================

class ConsoleRedirector:
    """A class to redirect stdout and stderr to a Tkinter widget."""

    def __init__(self, widget):
        self.widget = widget

    def write(self, text):
        self.widget.config(state=tk.NORMAL)
        self.widget.insert(tk.END, text)
        self.widget.see(tk.END)  # Auto-scroll
        self.widget.config(state=tk.DISABLED)

    def flush(self):
        pass  # Required for stream interface


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
        ttk.Label(frame, text=label_text, style="CardHeader.TLabel").pack(side="left", padx=(0, 10))
        ttk.Label(frame, text=value_text, style="Card.TLabel", wraplength=500).pack(side="left")

    def save_and_finalize(self):
        # 1. Update data with decisions from text widget
        decisions_raw = self.decisions_text.get("1.0", tk.END).strip()
        self.draft_data['decisions'] = [line.strip() for line in decisions_raw.split('\n') if line.strip()]

        # 2. Save changes back to the draft file
        try:
            with open(self.draft_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(self.draft_data, f, sort_keys=False, default_flow_style=False)
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save changes to draft file: {e}", parent=self)
            return

        # 3. Run the finalization script
        proj_name = self.draft_data.get('project')
        new_path = update_checkpoint_file(proj_name)
        if new_path:
            messagebox.showinfo("Success",
                                f"Checkpoint finalized successfully!\nNew file: {os.path.basename(new_path)}",
                                parent=self)
            self.controller.frames["CheckpointFrame"].on_show()  # Refresh parent frame
            self.destroy()
        else:
            messagebox.showerror("Finalization Failed",
                                 "Could not finalize the checkpoint. Check the console for details.", parent=self)


# ====================================================================
# CORE APP CLASS
# ====================================================================

class OrchestratorGUI:
    def __init__(self, master):
        self.master = master
        self.master.title("Mother AI Project Orchestrator")
        self.master.geometry("1200x800")
        self.master.minsize(1000, 700)

        # --- Fonts & Styling ---
        self.default_font = ("Segoe UI", 10)
        self.header_font = ("Segoe UI", 18, "bold")
        self.label_font = ("Segoe UI", 11, "bold")
        self._setup_styles()

        self.master.configure(bg=BG_DARK)

        self.current_project = tk.StringVar(master)
        self.frames = {}
        self.nav_buttons = {}

        # --- Top Navigation Bar ---
        self.navbar = ttk.Frame(master, style="Card.TFrame")
        self.navbar.pack(side="top", fill="x", padx=10, pady=(10, 5))
        self._create_navbar()

        # --- Main Content Area ---
        self.container = ttk.Frame(master, padding=(10, 5, 10, 5))
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        # --- Console Panel ---
        self.console_frame = ttk.Frame(master, style="Card.TFrame", height=150)
        self.console_frame.pack(side="bottom", fill="x", padx=10, pady=(5, 10))
        self._setup_console()

        self._load_initial_state()
        self._create_frames()
        self.show_frame("DashboardFrame")

    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('equilux')
        self.style.configure("Card.TFrame", background=CARD_DARK, borderwidth=1, relief="solid")
        self.style.configure('TLabel', background=BG_DARK, foreground=FG_DARK, font=self.default_font)
        self.style.configure('Header.TLabel', font=self.header_font, background=CARD_DARK)
        self.style.configure('Card.TLabel', background=CARD_DARK, foreground=FG_DARK, font=self.default_font)
        self.style.configure('CardHeader.TLabel', font=self.label_font, background=CARD_DARK)
        self.style.configure('Success.TLabel', background=CARD_DARK, foreground=SUCCESS_GREEN, font=self.label_font)
        self.style.configure("Accent.TButton", font=self.label_font, background=ACCENT_BLUE, foreground='white',
                             borderwidth=0, padding=(15, 10))
        self.style.map("Accent.TButton", background=[('active', ACCENT_BLUE_ACTIVE)])

    def _create_navbar(self):
        nav_items = {
            "Dashboard": "DashboardFrame",
            "History": "HistoryFrame",
            "Checkpoint": "CheckpointFrame",
            "New Project": "NewProjectFrame",
            "Commit": "CommitFrame",
        }
        for label, frame_key in nav_items.items():
            btn = ttk.Button(self.navbar, text=label, style="TButton", command=lambda k=frame_key: self.show_frame(k))
            btn.pack(side="left", padx=10, pady=10)
            self.nav_buttons[label] = btn

    def _setup_console(self):
        ttk.Label(self.console_frame, text="Console Output", style="CardHeader.TLabel").pack(anchor="w", padx=10,
                                                                                             pady=5)
        console_widget = scrolledtext.ScrolledText(self.console_frame, height=8, background=BG_DARK, foreground=FG_DARK,
                                                   font=("Consolas", 10), state=tk.DISABLED)
        console_widget.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Redirect stdout and stderr
        sys.stdout = ConsoleRedirector(console_widget)
        sys.stderr = ConsoleRedirector(console_widget)
        print(
            f"Dasmarinas City, Philippines - {datetime.datetime.now().strftime('%A, %B %d, %Y %I:%M %p')}\nWelcome to the Mother AI Orchestrator.\n")

    def _create_frames(self):
        for F in (DashboardFrame, HistoryFrame, CheckpointFrame, NewProjectFrame, CommitFrame):
            page_name = F.__name__
            frame = F(parent=self.container, controller=self)
            self.frames[page_name] = frame
            frame.grid(row=0, column=0, sticky="nsew")

    def show_frame(self, page_name):
        frame = self.frames[page_name]
        frame.tkraise()
        if hasattr(frame, 'on_show'):
            frame.on_show()
        for label, btn in self.nav_buttons.items():
            btn.configure(style="TButton")
        # Correctly find the key associated with the page_name to highlight the button
        for label, key_name in self.nav_buttons.items():
            if self.frames[page_name].__class__.__name__ == key_name.cget(
                    'text'):  # This logic is flawed. Let's fix it.
                pass  # The old logic was incorrect.

        active_label = ""
        for label, frame_class_name in {
            "Dashboard": "DashboardFrame", "History": "HistoryFrame", "Checkpoint": "CheckpointFrame",
            "New Project": "NewProjectFrame", "Commit": "CommitFrame"}.items():
            if frame_class_name == page_name:
                active_label = label
                break

        if active_label and active_label in self.nav_buttons:
            self.nav_buttons[active_label].configure(style="Accent.TButton")

    def _load_initial_state(self):
        try:
            state_data = read_orchestrator_state(ORCHESTRATOR_STATE_PATH)
            active_proj = state_data.get('meta', {}).get('active_project', '')
            self.current_project.set(active_proj)
        except Exception as e:
            print(f"ERROR: Failed to load orchestrator state: {e}")
            self.current_project.set("PROJECT_ERROR")

    def get_project_context(self):
        proj_name = self.current_project.get()
        try:
            state_data = read_orchestrator_state(ORCHESTRATOR_STATE_PATH)
            brain_path, checkpoint_path = get_project_paths(state_data, proj_name)
            return (proj_name, state_data, brain_path, checkpoint_path)
        except Exception as e:
            print(f"ERROR: Could not get context for '{proj_name}': {e}")
            return proj_name, None, None, None


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
        status_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))

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
        explorer_panel.grid(row=0, column=1, sticky="nsew")
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
            state_data = read_orchestrator_state(ORCHESTRATOR_STATE_PATH)
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
                # FIX: Get 'next_goal' from its correct nested location inside 'context'.
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
        self.grid_columnconfigure(1, weight=3)  # Content gets more space

        # --- File List Panel ---
        list_panel = ttk.Frame(self, style="Card.TFrame", padding=20)
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 10))
        ttk.Label(list_panel, text="Checkpoint Logs", style="Header.TLabel", background=CARD_DARK).pack(anchor="w",
                                                                                                        pady=(0, 15))
        self.log_listbox = tk.Listbox(list_panel, background=BG_DARK, foreground=FG_DARK,
                                      font=self.controller.default_font, relief="flat", selectbackground=ACCENT_BLUE)
        self.log_listbox.pack(fill="both", expand=True)
        self.log_listbox.bind("<<ListboxSelect>>", self.on_log_select)

        # --- Content Viewer Panel ---
        content_panel = ttk.Frame(self, style="Card.TFrame", padding=20)
        content_panel.grid(row=0, column=1, sticky="nsew")
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
        main_card.grid(row=0, column=0, sticky="nsew")

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

        self.create_draft_button = ttk.Button(main_card, text="Create Draft & Review", command=self.create_draft,
                                              style="Accent.TButton")
        self.create_draft_button.pack(pady=10, anchor="e")

        self.draft_status_label = ttk.Label(main_card, text="Checking for pending drafts...", style="Card.TLabel")
        self.draft_status_label.pack(pady=5, anchor="w")

    def on_show(self):
        self.check_draft_status()

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
            self.create_draft_button.config(state=tk.NORMAL)

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

        if not all([summary, goal, steps_raw]):
            messagebox.showerror("Error", "All fields are required to create a draft.")
            return

        # Build data and save to file
        next_steps = [line.strip() for line in steps_raw.split('\n') if line.strip()]
        new_checkpoint_data = {
            'project': proj_name, 'timestamp': datetime.datetime.now().isoformat(), 'type': 'checkpoint',
            'summary': summary,
            'context': {'previous_checkpoint_summary': latest_checkpoint_data.get('summary', 'N/A'),
                        'previous_next_steps_completed': latest_checkpoint_data.get('next_steps', []),
                        'next_goal': goal},
            'decisions': ["TODO: Fill this in during the review step."], 'next_steps': next_steps
        }
        file_timestamp = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
        filename = os.path.join(LOGS_DIR, f"{file_timestamp}-{proj_name}-checkpoint-NEW.yaml")

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                yaml.safe_dump(new_checkpoint_data, f, sort_keys=False, default_flow_style=False)

            print(f"Draft created: {os.path.basename(filename)}")
            # Clear fields and open review dialog
            self.summary_entry.delete(0, tk.END)
            self.goal_entry.delete(0, tk.END)
            self.next_steps_text.delete("1.0", tk.END)
            self.check_draft_status()
            ReviewDialog(self.master, self.controller, filename)

        except Exception as e:
            print(f"ERROR: Failed to save new checkpoint file: {e}")


# ====================================================================
# Other Frames (New Project, Commit) - Largely unchanged but inherit BaseFrame
# ====================================================================

class NewProjectFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        main_card = ttk.Frame(self, style="Card.TFrame", padding=20)
        main_card.grid(row=0, column=0, sticky="nsew")
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
        state_data = read_orchestrator_state(ORCHESTRATOR_STATE_PATH)
        if create_project(proj_name, state_data, ORCHESTRATOR_STATE_PATH, design_content):
            self.controller.current_project.set(proj_name)
            self.controller.show_frame("DashboardFrame")
        else:
            # Errors are now printed to the GUI console
            messagebox.showerror("Error", "Project creation failed. Check the console for details.")


class CommitFrame(BaseFrame):
    def __init__(self, parent, controller):
        super().__init__(parent, controller)
        main_card = ttk.Frame(self, style="Card.TFrame", padding=20)
        main_card.grid(row=0, column=0, sticky="nsew")
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
        if messagebox.askyesno("Confirm Commit",
                               f"Are you sure you want to commit and push changes for '{proj_name}'?"):
            commit_changes(proj_name, checkpoint_path)


# ====================================================================
# RUN APP
# ====================================================================
if __name__ == "__main__":
    root = ThemedTk(theme="equilux", themebg=True)
    app = OrchestratorGUI(root)
    root.mainloop()