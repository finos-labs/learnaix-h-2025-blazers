import os
import json
import requests
import sys
import traceback
from datetime import datetime

# --- CONFIGURATION ---
MODEL_PATH = "@MOODLE_APP.PUBLIC.MOUNTED/moodledata/student_keystroke_model.yaml" # <-- THIS LINE IS UPDATED
ANALYST_ENDPOINT = "/api/v2/cortex/agent:run"

# --- HELPER FUNCTIONS ---

def _get_url():
    """Constructs the full API URL from environment variables."""
    host = os.getenv("SNOWFLAKE_HOST")
    if not host:
        raise ValueError("SNOWFLAKE_HOST environment variable not set.")
    return f"https://{host}{ANALYST_ENDPOINT}"

def _get_login_token():
    """Fetches the SPCS OAuth token from the standard location."""
    with open("/snowflake/session/token", "r") as f:
        return f.read()

def _parse_input_args(argv):
    """Robustly parses JSON arguments from the command line."""
    if len(argv) < 2:
        raise ValueError("No JSON argument string provided.")
    json_arg_str = argv[1]
    data = json.loads(json_arg_str)
    if isinstance(data, list):
        if not data: raise ValueError("Received an empty list as arguments.")
        args = data[0]
    else:
        args = data
    if not isinstance(args, dict):
        raise TypeError(f"Parsed arguments must be a dictionary, but got {type(args).__name__}.")
    return args

def _send_request(url, token, semantic_model_file, prompt):
    """Sends the prompt to the Cortex Analyst REST API."""
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {token}", "X-Snowflake-Authorization-Token-Type": "OAUTH"}
    request_body = {
        "model": "llama3.1-8b",
        "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
        "tools": [{"tool_spec": {"type": "cortex_analyst_text_to_sql", "name": "Analyst1"}}],
        "tool_resources": {"Analyst1": {"semantic_model_file": semantic_model_file}},
    }
    return requests.post(url, headers=headers, data=json.dumps(request_body))

def _process_api_response(response):
    """Parses the streaming API response to extract the final answer and a full debug log."""
    final_answer = ""
    debug_log = [] # New variable to store all events
    for line in response.text.splitlines():
        if line.startswith('data:'):
            try:
                json_data_str = line.split('data: ', 1)[1]
                if json_data_str:
                    data = json.loads(json_data_str)
                    debug_log.append(data) # Add every parsed event to the log
                    if not isinstance(data, dict):
                        continue
                    delta = data.get('delta', {})
                    if delta.get('role') == 'assistant':
                        final_answer += delta.get('content', '')
            except (json.JSONDecodeError, IndexError):
                continue
    return final_answer.strip(), debug_log # Return both the answer and the log

# --- MAIN EXECUTION LOGIC ---

def main():
    """Main function to process JSON arguments and send request to Cortex Analyst"""
    try:
        args = _parse_input_args(sys.argv)
        question = args.get('question')
        if not question: raise ValueError("'question' field is missing from arguments.")
        
        url = _get_url()
        token = _get_login_token()
        response = _send_request(url, token, MODEL_PATH, question)
        response.raise_for_status()

        final_answer, debug_log = _process_api_response(response)
        
        print(json.dumps({"response": final_answer, "debug_log": debug_log}))
        return 0
    except Exception as e:
        error_details = {"error_type": type(e).__name__, "error_message": str(e), "traceback": traceback.format_exc()}
        print(json.dumps({"error": "An exception occurred", "details": error_details}))
        return 1

if __name__ == "__main__":
    sys.exit(main())