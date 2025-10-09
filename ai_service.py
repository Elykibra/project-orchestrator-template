# ai_service.py
# This file contains the multi-API fallback logic and structured output definition.

import os
import litellm
from litellm import completion
from pydantic import BaseModel, Field
import instructor
import rcs_service
from openai import OpenAI


# --- New Pydantic Class for the Unified Context Object (JSON-IN) ---
class CheckpointContext(BaseModel):
    """Unified context object sent to the AI, combining all data sources."""
    project_name: str = Field(description="The unique identifier for the active project.")
    # Context from brain.json (High-level intent)
    objectives: list[str] = Field(description="High-level project goals from the brain.json.")
    priority: str = Field(description="Strategic importance from the brain.json.")
    # Context from checkpoint.yaml (Latest state)
    last_goal: str = Field(description="The 'next_goal' from the previous checkpoint.")
    last_summary: str = Field(description="The 'summary' from the previous checkpoint.")
    previous_steps_completed: list[str] = Field(description="The 'next_steps' list from the previous checkpoint.")
    # New input from the system
    code_changes_git_diff: str = Field(description="The Git diff showing uncommitted changes.")
    # Placeholder for the RCS data (Future-proofing)
    rcs_insights_history: list[str] = Field(default=[], description="Recent historical insights from the RCS reflection logs.")


# --- 1. Define the Structured Output Schema (Pydantic) ---
class CheckpointDraft(BaseModel):
    """Structured output for the new checkpoint draft, matching your YAML structure."""
    summary: str = Field(description="A concise, 1-2 sentence summary of the work completed this session.")
    next_goal: str = Field(description="The clear, immediate goal for the NEXT coding session/checkpoint.")
    next_steps: list[str] = Field(description="A list of 3-5 concrete tasks to achieve the next goal.")
    decisions: list[str] = Field(default=["TODO: Fill this in during the review step."],
                                 description="Placeholder for human-made decisions.")

# --- 2. Define the Multi-API Fallback Strategy ---
# This is the BASE list of all available models.
BASE_MODEL_FALLBACK_LIST = [
    "gemini/gemini-2.5-flash",
    "openai/gpt-4o-mini",
    "anthropic/claude-3-haiku"
]


# --- 3. Central Function: Generates the Checkpoint Draft (UPDATED) ---
def get_ai_checkpoint_draft(context_prompt: str) -> dict | None:
    # Check for API keys
    if not any(os.getenv(key) for key in ["GEMINI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"]):
        print("ERROR: API keys not found in environment variables.")
        return None

    # CRITICAL: Fetch the DYNAMICALLY sorted list from the RCS service
    MODEL_FALLBACK_LIST = rcs_service.get_api_priority_list(BASE_MODEL_FALLBACK_LIST)

    # We iterate through the dynamically prioritized list
    for model_name in MODEL_FALLBACK_LIST:
        try:
            print(
                f"INFO: Attempting model: {model_name} (Priority: {MODEL_FALLBACK_LIST.index(model_name) + 1}/{len(MODEL_FALLBACK_LIST)})...")

            # --- START: Instructor/OpenAI Logic (High Reliability Path) ---
            if model_name.startswith("openai/"):
                # Patch the native OpenAI client for reliable structured output
                client = instructor.patch(OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))) # <--- CORRECT LINE ADDED HERE

                # Use Instructor's reliable method which enforces the schema
                response: CheckpointDraft = client.chat.completions.create(
                    model=model_name.split('/')[-1],
                    messages=[{"role": "user", "content": context_prompt}],
                    response_model=CheckpointDraft,
                    temperature=0.8,
                    max_retries=3
                )
                print(f"SUCCESS: Draft generated using {model_name} (Instructor).")
                return response.model_dump()

            else:
                # ... existing LiteLLM logic ...
                response = litellm.completion(
                    model=model_name,
                    messages=[{"role": "user", "content": context_prompt}],
                    response_model=CheckpointDraft,
                    request_timeout=45,
                    temperature=0.8,
                    max_retries=0
                )
                print(f"SUCCESS: Draft generated using {model_name} (LiteLLM).")
                return response.model_dump()

        except Exception as e:
            error_message = str(e).lower()
            error_type = "UNKNOWN_ERROR"

            if "rate limit" in error_message or "resource exhausted" in error_message or "status_code=429" in error_message:
                error_type = "RATE_LIMIT"
                print(f"WARNING: {model_name} failed (Rate Limit Hit). Trying next fallback...")
            else:
                error_type = "VALIDATION_FAILURE"
                print(f"ERROR: {model_name} failed. Skipping. Details: {error_message}")

            #CRITICAL: Hook for RCS to learn from the failure
            rcs_service.log_api_failure(model_name, error_type)

            continue

    # If the loop finishes without returning, all fallbacks have failed.
    print("CRITICAL API FAILURE (Fallback Exhausted): All models failed or hit rate limits.")
    return None

# --- 4. Health Check Function for Monitoring ---
def run_api_health_check() -> str:
    """Tests the primary API for operational status (for the GUI indicator)."""
    # NOTE: Keep this using LiteLLM for a generic check, now testing Gemini since it's stable
    try:
        # PING REQUEST: Use a single model string here
        litellm.completion(
            model="gemini/gemini-2.5-flash",
            messages=[{"role": "user", "content": "Ping"}],
            max_tokens=10,
            request_timeout=5
        )
        return "🟢 AUTO"

    except Exception:
        return "🔴 MANUAL"