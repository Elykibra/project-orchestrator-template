# app_controller.py
# Contains the core OrchestratorGUI class (the controller/model logic)

import tkinter as tk
from tkinter import scrolledtext, ttk, Toplevel, messagebox
import os
import sys
import datetime
import threading

# Import local modules
from checkpoint import (
    read_orchestrator_state,
    read_checkpoint,
    read_brain,
    get_project_paths,
    create_project,
    update_checkpoint_file,
    get_truncated_history,
)
from ai_service import get_ai_checkpoint_draft, run_api_health_check, CheckpointContext
from git_service import get_project_diff
from gui_frames import DashboardFrame, HistoryFrame, CheckpointFrame, NewProjectFrame, CommitFrame, ReviewDialog
from gui_constants import BG_DARK, CARD_DARK, FG_DARK, ACCENT_BLUE, SUCCESS_GREEN, ERROR_RED, ORCHESTRATOR_STATE_PATH, \
    LOGS_DIR


# ====================================================================
# CORE APP CONTROLLER CLASS
# ====================================================================

class OrchestratorGUI:
    # Attach constants to the class instance (self)
    ORCHESTRATOR_STATE_PATH = ORCHESTRATOR_STATE_PATH
    LOGS_DIR = LOGS_DIR

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

        # API Status Variable and Color Configuration
        self.api_status_var = tk.StringVar(master, value="🟡 CHECKING")
        self.api_status_var.trace_add("write", self.update_status_color)

        # --- UI Setup ---
        self.navbar = ttk.Frame(master, style="Card.TFrame")
        self.navbar.pack(side="top", fill="x", padx=10, pady=(10, 5))
        self._create_navbar()

        self.status_label = ttk.Label(self.navbar, textvariable=self.api_status_var, style='CardHeader.TLabel')
        self.status_label.pack(side="right", padx=15, pady=10)

        self.container = ttk.Frame(master, padding=(10, 5, 10, 5))
        self.container.pack(fill="both", expand=True)
        self.container.grid_rowconfigure(0, weight=1)
        self.container.grid_columnconfigure(0, weight=1)

        self.console_frame = ttk.Frame(master, style="Card.TFrame", height=150)
        self.console_frame.pack(side="bottom", fill="x", padx=10, pady=(5, 10))
        self._setup_console()

        self._load_initial_state()
        self._create_frames()
        self.show_frame("DashboardFrame")

        # Start the periodic background check loop
        self.start_periodic_check()

    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('equilux')
        self.style.configure("Card.TFrame", background=CARD_DARK, borderwidth=1, relief="solid")
        self.style.configure('TLabel', background=BG_DARK, foreground=FG_DARK, font=self.default_font)
        self.style.configure('Header.TLabel', font=self.header_font, background=CARD_DARK)
        self.style.configure('Card.TLabel', background=CARD_DARK, foreground=FG_DARK, font=self.default_font)
        self.style.configure('CardHeader.TLabel', font=self.label_font, background=CARD_DARK)
        self.style.configure('Success.TLabel', background=CARD_DARK, foreground=SUCCESS_GREEN, font=self.label_font)
        self.style.configure('Error.TLabel', background=CARD_DARK, foreground=ERROR_RED, font=self.label_font)

        self.style.configure("Accent.TButton", font=self.label_font, background=ACCENT_BLUE, foreground='white',
                             borderwidth=0, padding=(15, 10))
        self.style.map("Accent.TButton", background=[('active', '#2563EB')])  # Use direct color code

    def update_status_color(self, *args):
        """Safely updates the status label color based on the api_status_var content."""
        status = self.api_status_var.get()
        if "AUTO" in status:
            self.status_label.configure(style='Success.TLabel')
            # Trigger UI update on Checkpoint frame when status changes to AUTO
            self.frames["CheckpointFrame"].update_ui_mode()
        elif "MANUAL" in status or "ERROR" in status:
            self.status_label.configure(style='Error.TLabel')
            self.frames["CheckpointFrame"].update_ui_mode()
        else:
            self.status_label.configure(style='CardHeader.TLabel')

    def _run_health_check_worker(self):
        """Worker thread to run the potentially long-running API check."""
        print("INFO: Running API health check...")
        status = run_api_health_check()
        self.master.after(0, lambda: self.api_status_var.set(status))
        print(f"INFO: API Status updated to {status}.")

    def start_periodic_check(self):
        """Schedules the health check thread and repeats."""
        if self.api_status_var.get() == "🟡 CHECKING" or self.api_status_var.get() == "🔴 MANUAL":
            threading.Thread(target=self._run_health_check_worker, daemon=True).start()

        # Schedule the next check in 60 minutes (3,600,000 ms)
        self.master.after(3600000, self.start_periodic_check)

    def _create_navbar(self):
        nav_items = {
            "Dashboard": DashboardFrame.__name__,
            "History": HistoryFrame.__name__,
            "Checkpoint": CheckpointFrame.__name__,
            "New Project": NewProjectFrame.__name__,
            "Commit": CommitFrame.__name__,
        }
        for label, frame_key in nav_items.items():
            btn = ttk.Button(self.navbar, text=label, style="TButton", command=lambda k=frame_key: self.show_frame(k))
            btn.pack(side="left", padx=10, pady=10)
            self.nav_buttons[label] = btn

    def _setup_console(self):
        # Console Redirection setup
        console_widget = scrolledtext.ScrolledText(self.console_frame, height=8, background=BG_DARK, foreground=FG_DARK,
                                                   font=("Consolas", 10), state=tk.DISABLED)
        console_widget.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        # Redirect stdout and stderr
        class ConsoleRedirector:
            def __init__(self, widget):
                self.widget = widget

            def write(self, text):
                self.widget.config(state=tk.NORMAL)
                self.widget.insert(tk.END, text)
                self.widget.see(tk.END)
                self.widget.config(state=tk.DISABLED)

            def flush(self): pass

        sys.stdout = ConsoleRedirector(console_widget)
        sys.stderr = ConsoleRedirector(console_widget)
        print(f"Welcome to the Mother AI Orchestrator.\n")

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

        active_label = ""
        for label, frame_key in self.nav_buttons.items():
            if frame_key.cget('text') == page_name:
                active_label = label
                break

        for label, btn in self.nav_buttons.items():
            if label == active_label:
                btn.configure(style="Accent.TButton")
            else:
                btn.configure(style="TButton")

    def _load_initial_state(self):
        try:
            state_data = read_orchestrator_state(self.ORCHESTRATOR_STATE_PATH)
            active_proj = state_data.get('meta', {}).get('active_project', '')
            self.current_project.set(active_proj)
        except Exception as e:
            print(f"ERROR: Failed to load orchestrator state: {e}")
            self.current_project.set("PROJECT_ERROR")

    def get_project_context(self):
        proj_name = self.current_project.get()
        try:
            state_data = read_orchestrator_state(self.ORCHESTRATOR_STATE_PATH)
            brain_path, checkpoint_path = get_project_paths(state_data, proj_name)
            return (proj_name, state_data, brain_path, checkpoint_path)
        except Exception as e:
            print(f"ERROR: Could not get context for '{proj_name}': {e}")
            return proj_name, None, None, None

    # --- REFOCUSED: Unified Context JSON Generation (JSON-IN) ---
    def build_checkpoint_prompt(self, proj_name, checkpoint_path):
        """Builds the prompt by serializing a unified CheckpointContext object for AI analysis."""

        # 1. Load Data
        _, state_data, brain_path, _ = self.get_project_context()
        latest_checkpoint = read_checkpoint(checkpoint_path)
        brain_data = read_brain(brain_path)

        if not latest_checkpoint or not brain_data:
            print("CRITICAL: Missing Brain or Checkpoint data for prompt. Aborting.")
            return "ERROR_CONTEXT_MISSING"

        # 2. Get Git Changes (DELEGATED TO SERVICE)
        # Assuming the placeholder for Git diff has been moved to git_service.py
        import git_service
        changed_content = git_service.get_project_diff(proj_name)

        # 3. Get Truncated History (NEW)
        truncated_history = get_truncated_history(proj_name)

        # 4. Populate CheckpointContext (JSON-IN) - UPDATED
        context_data = CheckpointContext(
            project_name=proj_name,
            objectives=brain_data.get('objectives', ['N/A']),
            priority=brain_data.get('priority', 'N/A'),
            last_goal=latest_checkpoint.get('context', {}).get('next_goal', 'No previous goal.'),
            last_summary=latest_checkpoint.get('summary', 'No previous summary.'),
            previous_steps_completed=latest_checkpoint.get('next_steps', []),
            code_changes_git_diff=changed_content,
            recent_history=truncated_history,  # NEW: Added to Context JSON
            rcs_insights_history=[],
        )

        # 4. Serialize Context to JSON string
        context_json = context_data.model_dump_json(indent=2) # Use Pydantic to enforce structure

        # 5. Generate Final Prompt (System Instruction)
        prompt = f"""
        You are the Mother AI Orchestrator. Your task is to analyze the complete project context provided below. You MUST strictly adhere to the JSON schema for the CheckpointDraft object.

        --- PROJECT CONTEXT (UNIFIED JSON) ---
        {context_json}

        --- INSTRUCTION ---
        1. Analyze the 'code_changes_git_diff' in relation to the 'last_goal'.
        2. Generate a concise **summary** of the work completed.
        3. Propose the **next_goal** and 3-5 concise **next_steps**.
        4. Your response MUST be valid JSON that perfectly matches the CheckpointDraft schema.
        """
        return prompt