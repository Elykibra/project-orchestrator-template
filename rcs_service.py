# rcs_service.py
# Implements the Reflective Checkpoint System (RCS) logic for self-assessment and adaptive API switching.

import os
import yaml
import json
import datetime
import random  # Used for initial random prioritization

# Define the path for the adaptive memory store
RCS_LOG_PATH = "brains/Project_Orchestrator/reflection_logs.yaml"


# --- Utility Functions for Persistence ---

def _read_rcs_logs() -> list:
    """Safely reads the reflection_logs.yaml file."""
    try:
        if not os.path.exists(RCS_LOG_PATH):
            return []
        with open(RCS_LOG_PATH, 'r', encoding='utf-8') as f:
            # Load all documents from the YAML file
            return list(yaml.safe_load_all(f))
    except Exception as e:
        print(f"RCS ERROR: Failed to read logs from {RCS_LOG_PATH}. Details: {e}")
        return []


def _append_to_rcs_logs(log_entry: dict):
    """Appends a new reflection entry to the persistent log file."""
    try:
        # Append mode: Write the new document separator (---) and the new entry
        with open(RCS_LOG_PATH, 'a', encoding='utf-8') as f:
            yaml.safe_dump(log_entry, f, default_flow_style=False, sort_keys=False, explicit_start=True)
        print(f"RCS INFO: Reflection data logged for checkpoint.")
    except Exception as e:
        print(f"RCS CRITICAL: Failed to append log entry: {e}")


# --- Adaptive API Switching Logic ---

def get_api_priority_list(base_list: list) -> list:
    """
    Reads historical data to dynamically prioritize the list of models by combining
    efficiency scores and failure penalties. Models with a recent penalty_score (0.1)
    are immediately dropped in priority.
    """
    logs = _read_rcs_logs()

    # Initialize priority map: high score (1.0) means high priority/no bad history
    priority_map = {model: 1.0 for model in base_list}

    # 1. Process all logs to determine model priority based on the latest performance/failure
    # We iterate forward, meaning the latest log entry will overwrite prior entries, which is what we want.
    for entry in logs:
        # A. Check for API_FAILURE Logs (The CRITICAL Fix: Instant Penalty)
        if entry.get('type') == 'API_FAILURE':
            model = entry.get('model')
            penalty = entry.get('penalty_score', 0.1)

            if model in priority_map:
                # Apply the low penalty score (0.1) immediately. This instantly drops the model's priority.
                # We use penalty as the score, ensuring low scores sink to the bottom.
                priority_map[model] = penalty

                # B. Check for Reflection Logs (Simulated Efficiency Scores)
        elif entry.get('type') == 'checkpoint' and entry.get('reflections'):
            # NOTE: We iterate over all models found in the simulated scoring section.
            efficiency_scores = entry['reflections'].get('api_efficiency_scores', {})

            for model, score in efficiency_scores.items():
                if model in priority_map:
                    # If a model succeeded and received a score, we can use it, but only if it
                    # hasn't just been instantly penalized in this same run (not strictly necessary
                    # but good defensive coding).
                    if priority_map[model] > 0.1:
                        # Use the reported score as the current priority value.
                        priority_map[model] = score

                        # 2. Sort the base list by the calculated score (descending)
    # Models with a score of 1.0 (no history), followed by efficiency scores (e.g., 0.8),
    # followed by penalty scores (0.1).
    sorted_list = sorted(base_list, key=lambda model: priority_map.get(model, 0.0), reverse=True)

    # If all models have the same default score, shuffle to prevent provider lock-in
    if all(score == 1.0 for score in priority_map.values()):
        random.shuffle(sorted_list)

    print(f"RCS INFO: Dynamic API Priority Map: {json.dumps(priority_map, indent=4)}")  # New audit print
    print(f"RCS INFO: Dynamic API Priority List generated: {sorted_list}")
    return sorted_list


def log_api_failure(model_name: str, error_type: str):
    """Creates a minimal log entry when an API fails, informing future sorting."""
    # We log a low efficiency score that the next prioritization cycle will detect.
    # This acts as an immediate penalty for that model.
    failure_entry = {
        'date': datetime.datetime.now().isoformat(),
        'type': 'API_FAILURE',
        'model': model_name,
        'error': error_type,
        'penalty_score': 0.1  # A low score to penalize future selection
    }

    # --- EXPANSION: APPEND THE ENTRY TO THE PERSISTENT LOG ---
    _append_to_rcs_logs(failure_entry) # This writes the failure event to reflection_logs.yaml

    # This simple logging needs to be implemented. For now, we print a warning.
    print(f"RCS ALERT: Recorded API failure for {model_name} ({error_type}). This will impact future priority.")
    # NOTE: Full implementation would append this to a separate log or integrate it into _append_to_rcs_logs.


# --- Core Reflection Cycle (Module 2-3 of RCS) ---

def process_reflection(project_name: str, checkpoint_data: dict):
    """
    Executes the full RCS reasoning cycle: calculates scores, generates insights,
    and updates the adaptive memory.
    """
    print(f"\n--- RCS ACTION: Starting Reflection Cycle for {project_name} ---")

    # 1. Reflection Engine (Calculate quantitative scores)
    # NOTE: Full implementation requires LLM analysis of checkpoint_data.
    # For now, we use placeholders based on data presence.

    # Simulate scores based on a predefined target (e.g., 0.9 for clarity, 0.5 for efficiency)
    api_efficiency = 0.5 + random.uniform(-0.1, 0.4)  # Simulate variable API performance

    simulated_reflections = {
        'task_clarity': 0.9 + random.uniform(-0.1, 0.05),
        'goal_alignment': 0.8 + random.uniform(-0.1, 0.1),
        'api_efficiency': round(api_efficiency, 2),
        # Placeholder for scores of all models tried in the session (if available)
        'api_efficiency_scores': {'gemini/gemini-2.5-flash': round(api_efficiency, 2)}
    }

    # 2. Insight Synthesizer (Translates scores to human-readable guidance)
    insights = []
    actions = []

    if simulated_reflections['api_efficiency'] < 0.6:
        insights.append("API inefficiency detected. Response time was suboptimal.")
        actions.append("Next time: Switch API or schedule latency check.")

    if simulated_reflections['goal_alignment'] < 0.7:
        insights.append("Goal alignment score is low. Re-evaluate project context.")
        actions.append("Re-align next goal with main objectives.")

    # 3. Adaptive Memory (Persist results)
    reflection_log_entry = {
        'date': datetime.datetime.now().isoformat(),
        'project': project_name,
        'checkpoint_id': checkpoint_data.get('checkpoint_id', 'N/A'),
        'reflections': simulated_reflections,
        'insights': insights,
        'actions': actions,
        'state_after_reflection': "Stable"
    }

    # Append the new entry to the YAML log
    _append_to_rcs_logs(reflection_log_entry)

    print("--- RCS INFO: Reflection Cycle Complete. Insights Logged. ---")