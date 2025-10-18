import json.decoder
import requests
import os

import openai
from utils.enums import LLM
import time


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
        except openai.error.RateLimitError:
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

