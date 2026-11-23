import json
from typing import Any


def _build_ai_prompt(
    schema_info: dict,
    validation_summary: dict,
    sample_data: list[dict],
    prompt_template: str,
    details: str = ""
) -> str:
    """Build the prompt for AI analysis."""

    # Summarize schema
    schema_text = "\n".join(
        f"- {table}: {', '.join(cols)}"
        for table, cols in schema_info.items()
    )

    # Summarize validation results
    total_errors = sum(r.get("critical_count", 0) for r in validation_summary.values())
    total_warnings = sum(r.get("warning_count", 0) for r in validation_summary.values())

    validation_text = f"""
Validation Results Summary:
- Total critical errors: {total_errors}
- Total warnings: {total_warnings}
"""

    # Add per-table breakdown
    for table, results in validation_summary.items():
        if results.get("critical_count", 0) > 0 or results.get("warning_count", 0) > 0:
            validation_text += f"\n{table}: {results.get('critical_count', 0)} critical, {results.get('warning_count', 0)} warnings"

    # Sample data (limited for token efficiency)
    sample_limit = min(len(sample_data), 20)
    sample_text = json.dumps(sample_data[:sample_limit], indent=2, default=str)

    details_section = f"\n\nAdditional Context:\n{details}" if details else ""

    full_prompt = f"""{prompt_template}

Schema:
{schema_text}

{validation_text}

Sample Data (first {sample_limit} rows):
{sample_text}

{details_section}

Please return your findings as a JSON list with this structure:
[
  {{
    "finding_type": "anomaly|pattern|recommendation|data_quality",
    "description": "Clear description of the finding",
    "severity": "info|warning|critical",
    "affected_columns": ["column1", "column2"],
    "confidence": "high|medium|low"
  }}
]

Only include genuine findings. Do not repeat issues already flagged by predefined checks unless you have additional insight."""

    return full_prompt
# I can never seem to get the AI to actually ignore the predefined checks, no matter how I pass them to the prompt. Just need to accept it'll find other things. 


# Never actually got around to injecting the baseURL from secrets.md. 
# That was planned, but didn't feel that important for a non production showcase.

def call_llm_lmstudio(
    config: dict,
    prompt: str
) -> list[dict]:
    """Call LM Studio local API for analysis."""

    try:
        import requests
    except ImportError:
        raise ImportError("requests is required. Install with: pip install requests")

    base_url = config.get("base_url", "http://127.0.0.1:1234/v1")
    api_key = config.get("api_key", "lm-studio")
    model = config.get("model", "")

    headers = {
        "Content-Type": "application/json"
    }

    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    messages = [
        {"role": "system", "content": "You are a data quality analyst. Analyze datasets for anomalies and issues."},
        {"role": "user", "content": prompt}
    ]

    payload = {
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 4096
    }

    if model:
        payload["model"] = model

    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=300
    )

    if response.status_code != 200:
        raise RuntimeError(f"AI API error ({response.status_code}): {response.text}")

    result = response.json()
    message = result["choices"][0]["message"]
    content = message.get("content", "")
    
    # Some reasoning models put content in reasoning_content
    if not content and message.get("reasoning_content"):
        content = message["reasoning_content"]

    return _parse_ai_response(content)


# Tested by swapping out to lm Studio endpoint. But I've never actually open AI's endpoint myself. And this piece was added by open code likely templated on my LM Studio function. I asked it to add this and anthropic as llm sources.
def call_llm_openai(
    config: dict,
    prompt: str
) -> list[dict]:
    """Call OpenAI-compatible API for analysis."""

    try:
        import requests
    except ImportError:
        raise ImportError("requests is required. Install with: pip install requests")

    base_url = config.get("base_url", "https://api.openai.com/v1")
    api_key = config.get("api_key", "")
    model = config.get("model", "gpt-4o-mini")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a data quality analyst. Analyze datasets for anomalies and issues."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
        "response_format": {"type": "json_object"}
    }

    response = requests.post(
        f"{base_url}/chat/completions",
        headers=headers,
        json=payload,
        timeout=300
    )

    if response.status_code != 200:
        raise RuntimeError(f"AI API error ({response.status_code}): {response.text}")

    result = response.json()
    message = result["choices"][0]["message"]
    content = message.get("content", "")
    
    # Some reasoning models put content in reasoning_content
    if not content and message.get("reasoning_content"):
        content = message["reasoning_content"]

    return _parse_ai_response(content)

# This was added by opencode. I haven't tested it, and didn't write this function myself so I've disabled it. 
# def call_llm_anthropic(
#     config: dict,
#     prompt: str
# ) -> list[dict]:
#     """Call Anthropic API for analysis."""

#     try:
#         import requests
#     except ImportError:
#         raise ImportError("requests is required. Install with: pip install requests")

#     api_key = config.get("api_key", "")
#     model = config.get("model", "claude-3-haiku-20240307")

#     headers = {
#         "Content-Type": "application/json",
#         "x-api-key": api_key,
#         "anthropic-version": "2023-06-01"
#     }

#     payload = {
#         "model": model,
#         "max_tokens": 2048,
#         "messages": [
#             {"role": "user", "content": prompt}
#         ],
#         "temperature": 0.3
#     }

#     response = requests.post(
#         "https://api.anthropic.com/v1/messages",
#         headers=headers,
#         json=payload,
#         timeout=120
#     )

#     if response.status_code != 200:
#         raise RuntimeError(f"AI API error ({response.status_code}): {response.text}")

#     result = response.json()
#     content = result["content"][0]["text"]

#     return _parse_ai_response(content)




def _parse_ai_response(content: str) -> list[dict]:
    """Parse AI response, extracting JSON findings."""

    # Try to find JSON in the response (handle markdown code blocks)
    text = content.strip()

    if "```json" in text:
        start = text.index("```json") + 7
        end = text.rindex("```")
        text = text[start:end].strip()
    elif "```" in text:
        start = text.index("```") + 3
        end = text.rindex("```")
        text = text[start:end].strip()

    try:
        data = json.loads(text)

        if isinstance(data, list):
            return data

        # Some models wrap in an object with a "findings" key
        if isinstance(data, dict):
            for key in ["findings", "analysis", "results"]:
                if key in data and isinstance(data[key], list):
                    return data[key]

            # Try to convert single finding object to list
            if any(k in data for k in ["finding_type", "description"]):
                return [data]

    except json.JSONDecodeError:
        pass

    # Return empty list if parsing fails
    return []


def run_ai_analysis(
    ai_config: dict,
    schema_info: dict,
    validation_summary: dict,
    sample_data: list[dict],
    table_details: str = ""
) -> list[dict]:
    """
    Run AI analysis on the dataset.

    Args:
        ai_config: Configuration from get_ai_config().
        schema_info: Dict of table_name -> column_names.
        validation_summary: Summary of predefined check results.
        sample_data: Sample rows for analysis.
        table_details: Optional additional context/caveats.

    Returns:
        List of AI findings as dicts.
    """

    if not ai_config.get("enabled", False):
        return []

    prompt = _build_ai_prompt(
        schema_info=schema_info,
        validation_summary=validation_summary,
        sample_data=sample_data,
        prompt_template=ai_config.get("prompt_template", ""),
        details=table_details or ai_config.get("details", "")
    )

    provider = ai_config.get("provider", "").lower()

    if provider == "openai":
        return call_llm_openai(ai_config, prompt)

    elif provider == "anthropic":
        return call_llm_anthropic(ai_config, prompt)

    elif provider in ("lmstudio", "local"):
        return call_llm_lmstudio(ai_config, prompt)

    else:
        raise ValueError(f"Unsupported AI provider: {provider}")
