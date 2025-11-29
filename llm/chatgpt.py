import json.decoder
import requests
import os

import openai
from utils.enums import LLM
import time

# Handle different OpenAI library versions
try:
    # Newer versions (v1.0+)
    from openai import RateLimitError
except ImportError:
    try:
        # Older versions
        from openai.error import RateLimitError
    except (ImportError, AttributeError):
        # If openai.error doesn't exist, create a dummy exception class
        class RateLimitError(Exception):
            pass


def init_chatgpt(OPENAI_API_KEY, OPENAI_GROUP_ID, model, OPENAI_API_BASE=""):
    # if model == LLM.TONG_YI_QIAN_WEN:
    #     import dashscope
    #     dashscope.api_key = OPENAI_API_KEY
    # else:
    #     openai.api_key = OPENAI_API_KEY
    #     openai.organization = OPENAI_GROUP_ID
    openai.api_key = OPENAI_API_KEY
    openai.organization = OPENAI_GROUP_ID
    if OPENAI_API_BASE:
        openai.api_base = OPENAI_API_BASE


def ask_completion(model, batch, temperature):
    response = openai.Completion.create(
        model=model,
        prompt=batch,
        temperature=temperature,
        max_tokens=200,
        top_p=1,
        frequency_penalty=0,
        presence_penalty=0,
        stop=[";"]
    )
    response_clean = [_["text"] for _ in response["choices"]]
    return dict(
        response=response_clean,
        **response["usage"]
    )


def ask_chat(model, messages: list, temperature, n):
    response = openai.ChatCompletion.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=200,
        n=n
    )
    response_clean = [choice["message"]["content"] for choice in response["choices"]]
    if n == 1:
        response_clean = response_clean[0]
    return dict(
        response=response_clean,
        **response["usage"]
    )


def ask_llm(model: str, batch: list, temperature: float, n:int):
    n_repeat = 0
    while True:
        try:
            if model in LLM.TASK_COMPLETIONS:
                # TODO: self-consistency in this mode
                assert n == 1
                response = ask_completion(model, batch, temperature)
            elif model in LLM.TASK_CHAT:
                # batch size must be 1
                assert len(batch) == 1, "batch must be 1 in this mode"
                messages = [{"role": "user", "content": batch[0]}]
                response = ask_chat(model, messages, temperature, n)
                response['response'] = [response['response']]
            elif model in LLM.TASK_OLLAMA:
                # Ollama generate API: POST /api/generate {model, prompt, options}
                assert len(batch) == 1, "batch must be 1 in this mode"
                url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/generate"
                prompt = batch[0]
                all_completions = []
                total_tokens = 0
                for _ in range(max(1, n)):
                    r = requests.post(url, json={
                        "model": model,
                        "prompt": prompt,
                        "options": {
                            "temperature": temperature,
                            "stop": [";"]
                        },
                        "stream": False
                    }, timeout=600)
                    r.raise_for_status()
                    data = r.json()
                    completion = data.get("response", "")
                    all_completions.append(completion)
                    # Ollama returns eval_count (tokens generated) and prompt_eval_count
                    total_tokens += int(data.get("eval_count", 0)) + int(data.get("prompt_eval_count", 0))
                response = {
                    "response": all_completions,
                    "total_tokens": total_tokens
                }
            break
        except RateLimitError:
            n_repeat += 1
            print(f"Repeat for the {n_repeat} times for RateLimitError", end="\n")
            time.sleep(1)
            continue
        except json.decoder.JSONDecodeError:
            n_repeat += 1
            print(f"Repeat for the {n_repeat} times for JSONDecodeError", end="\n")
            time.sleep(1)
            continue
        except requests.RequestException as e:
            n_repeat += 1
            print(f"Repeat for the {n_repeat} times for Ollama error: {e}", end="\n")
            time.sleep(1)
            continue
        except Exception as e:
            n_repeat += 1
            print(f"Repeat for the {n_repeat} times for exception: {e}", end="\n")
            time.sleep(1)
            continue

    return response


class ChatGPT:
    """
    Wrapper class for LLM interactions with system prompt support.

    Provides a clean interface for rule generation with persistent system prompts
    that set constraints and instructions across all interactions.
    """

    def __init__(self, model: str, api_key: str = "not_needed_for_ollama", temperature: float = 0.3):
        """
        Initialize ChatGPT wrapper.

        Args:
            model: Model name (e.g., 'gpt-4', 'llama3.1:8b', 'codellama:7b')
            api_key: OpenAI API key (not needed for Ollama)
            temperature: Sampling temperature
        """
        self.model = model
        self.api_key = api_key
        self.temperature = temperature

        # System prompt for SQL regex rule generation - comprehensive constraints
        self.system_prompt = """You are an expert SQL error correction system that generates regex patterns.

CRITICAL SQL RULES:
1. Replacement MUST be valid SQL with proper clause order: SELECT → FROM → JOIN → WHERE → GROUP BY → HAVING → ORDER BY → LIMIT
2. NEVER create duplicate clauses - if WHERE exists, do NOT add another WHERE
3. NEVER use backslash escapes in SQL replacement (use s.Name NOT s\\.Name, use col_name NOT col\\_name)
4. SQL output MUST start with SELECT (or be a valid SQL fragment that starts with SELECT)
5. Use capture groups (\\1, \\2) ONLY to preserve existing parts, NOT to duplicate them

PYTHON REGEX SYNTAX (STRICT):
- Use capture groups (...) in PATTERN
- Use \\1, \\2, \\3 for backreferences in REPLACEMENT (NOT $1, NOT \\g<name>)
- REPLACEMENT is literal SQL text - do NOT escape dots, underscores, or parentheses
- Escape special chars in PATTERN only: \\. \\+ \\* \\( \\) \\[ \\]
- NO look-behinds, max 2-3 capture groups

CLAUSE ORDERING (MUST FOLLOW):
- WHERE must come BEFORE GROUP BY, ORDER BY, LIMIT
- GROUP BY must come BEFORE HAVING, ORDER BY, LIMIT
- ORDER BY must come BEFORE LIMIT

OUTPUT FORMAT (exactly 5 lines):
PATTERN: <regex pattern>
REPLACEMENT: <replacement with \\1, \\2 - valid SQL>
CORRECTION: <explanation>
ERROR_TYPE: <error type>
CONFIDENCE: <high/medium/low>

GOOD EXAMPLES:
✓ Pattern that captures specific query structure
✓ Replacement: SELECT s.Name FROM singer s WHERE s.Age > 20
✓ Clean SQL with no escape characters

BAD EXAMPLES (NEVER DO):
✗ Pattern that adds WHERE when WHERE already exists in query
✗ Replacement with two ORDER BY clauses
✗ SQL with backslashes: SELECT s\\.Name FROM singer
✗ Replacement starting with WHERE (missing SELECT)
✗ Using $1 instead of \\1 in replacement"""

    def generate(self, prompt: str, temperature: float = None) -> str:
        """
        Generate response with system prompt support.

        Args:
            prompt: User prompt
            temperature: Optional temperature override

        Returns:
            Generated text
        """
        if temperature is None:
            temperature = self.temperature

        if self.model.startswith('gpt') or self.model in ['gpt-4', 'gpt-3.5-turbo', 'gpt-4-turbo']:
            # OpenAI API with system prompt
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": prompt}
            ]
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                temperature=temperature,
                max_tokens=200
            )
            return response.choices[0].message.content

        elif self.model in LLM.TASK_OLLAMA:
            # Ollama API with /api/chat endpoint (supports system prompts)
            url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434") + "/api/chat"
            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "stream": False,
                "options": {
                    "temperature": temperature
                }
            }

            n_repeat = 0
            while n_repeat < 3:
                try:
                    response = requests.post(url, json=data, timeout=600)
                    response.raise_for_status()
                    return response.json()['message']['content']
                except requests.RequestException as e:
                    n_repeat += 1
                    print(f"Ollama request failed (attempt {n_repeat}/3): {e}")
                    time.sleep(1)
            raise Exception(f"Ollama request failed after 3 attempts")

        else:
            # Fallback to ask_llm without system prompt
            response = ask_llm(self.model, [prompt], temperature, 1)
            return response['response'][0]

