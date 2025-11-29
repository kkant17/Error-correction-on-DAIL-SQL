import argparse
import os
import json

import openai
from tqdm import tqdm

from llm.chatgpt import init_chatgpt, ask_llm
from utils.enums import LLM
from torch.utils.data import DataLoader

from utils.post_process import process_duplication, get_sqls

# MODIFICATION: Import the evaluation function and other necessary modules
from eval.exec_eval import eval_exec_match
import asyncio

QUESTION_FILE = "questions.json"


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--question", type=str, required=True)
    parser.add_argument("--openai_api_key", type=str, required=True)
    parser.add_argument("--openai_group_id", type=str, default="org-ktBefi7n9aK7sZjwc2R9G1Wo")
    parser.add_argument("--openai_api_base", type=str, default="", help="Custom API base URL for Ollama or other OpenAI-compatible APIs")
    parser.add_argument("--model", type=str, choices=[LLM.TEXT_DAVINCI_003, 
                                                      LLM.GPT_35_TURBO,
                                                      LLM.GPT_35_TURBO_0613,
                                                      LLM.GPT_4,
                                                      LLM.OLLAMA_CODELLAMA_7B,
                                                      LLM.OLLAMA_DEEPSEEK_CODER_6_7B,
                                                      LLM.OLLAMA_MISTRAL_7B,
                                                      LLM.OLLAMA_PHI3_INSTRUCT,
                                                      LLM.OLLAMA_QWEN_2_5_CODER_7B,
                                                      LLM.OLLAMA_DEEPSEEK_V2_LITE],
                        default=LLM.GPT_35_TURBO)
    parser.add_argument("--start_index", type=int, default=0)
    parser.add_argument("--end_index", type=int, default=1000000)
    parser.add_argument("--temperature", type=float, default=0)
    parser.add_argument("--mini_index_path", type=str, default="")
    parser.add_argument("--batch_size", type=int, default=1)
    parser.add_argument("--n", type=int, default=1, help="Size of self-consistent set")
    parser.add_argument("--db_dir", type=str, default="dataset/spider/database", help="Path to the database directory")
    args = parser.parse_args()

    # check args (Ollama path currently supports only batch_size==1)
    assert args.model in LLM.BATCH_FORWARD or \
           args.model in LLM.TASK_OLLAMA or \
           args.model not in LLM.BATCH_FORWARD and args.batch_size == 1, \
        f"{args.model} doesn't support batch_size > 1"

    questions_json = json.load(open(os.path.join(args.question, QUESTION_FILE), "r"))
    
    # MODIFICATION: We need the full question objects, not just the prompts
    all_questions_data = questions_json["questions"]

    # init openai api
    init_chatgpt(args.openai_api_key, args.openai_group_id, args.model, args.openai_api_base)

    if args.start_index == 0:
        mode = "w"
    else:
        mode = "a"

    safe_model = args.model.replace(":", "_").replace("/", "_")

    if args.mini_index_path:
        mini_index = json.load(open(args.mini_index_path, 'r'))
        # MODIFICATION: Filter the full data objects
        all_questions_data = [all_questions_data[i] for i in mini_index]
        out_file = f"{args.question}/RESULTS_MODEL-{safe_model}_MINI.txt"
    else:
        out_file = f"{args.question}/RESULTS_MODEL-{safe_model}.txt"

    # MODIFICATION: Create evaluation results file path
    eval_out_file = os.path.join("results", f"eval_{safe_model}.txt")

    # The DataLoader will now handle dictionaries
    question_loader = DataLoader(all_questions_data, batch_size=args.batch_size, shuffle=False, drop_last=False)

    # MODIFICATION: Add counters for live evaluation
    total_questions = 0
    correct_predictions = 0

    token_cnt = 0
    with open(out_file, mode) as f, open(eval_out_file, mode) as eval_f:
        # MODIFICATION: Enumerate provides an index starting from 0
        for i, batch_data in enumerate(tqdm(question_loader)):
            
            # The DataLoader might return lists of values for each key if batch_size > 1
            # We need to reconstruct the list of dicts
            batch_prompts = batch_data['prompt']
            
            current_batch_index = i * args.batch_size
            if current_batch_index < args.start_index:
                continue
            if current_batch_index >= args.end_index:
                break
                
            try:
                res = ask_llm(args.model, batch_prompts, args.temperature, args.n)
            except openai.error.InvalidRequestError:
                print(f"The question batch starting at index {current_batch_index} has too many tokens! Returning empty string.")
                res = {"response": ["" for _ in batch_prompts], "total_tokens": 0}

            token_cnt += res["total_tokens"]

            # Process each item in the batch
            final_sqls_for_batch = []
            if args.n == 1:
                for sql in res["response"]:
                    sql = sql.replace("```", " ")
                    idx = sql.upper().find("SELECT")
                    if idx != -1:
                        sql = sql[idx:]
                    sql = " ".join(sql.replace("\n", " ").split())
                    sql = process_duplication(sql)
                    if not sql.upper().startswith("SELECT"):
                        sql = "SELECT " + sql
                    final_sqls_for_batch.append(sql)
            else: # Self-consistency voting
                results_for_voting = []
                db_ids_batch = batch_data['db_id']
                for j in range(len(batch_prompts)):
                    sqls = res["response"][j] # res["response"] is a list of lists if n > 1
                    processed_sqls = []
                    for sql in sqls:
                        sql = sql.replace("```", " ")
                        idx = sql.upper().find("SELECT")
                        if idx != -1:
                            sql = sql[idx:]
                        sql = " ".join(sql.replace("\n", " ").split())
                        sql = process_duplication(sql)
                        if not sql.upper().startswith("SELECT"):
                            sql = "SELECT " + sql
                        processed_sqls.append(sql)
                    
                    results_for_voting.append({
                        'db_id': db_ids_batch[j],
                        'p_sqls': processed_sqls
                    })
                
                final_sqls_for_batch = get_sqls(results_for_voting, args.n, args.db_dir)

            # MODIFICATION: Live evaluation for each predicted SQL in the batch
            for j, predicted_sql in enumerate(final_sqls_for_batch):
                item_index = current_batch_index + j
                
                # Write to file first to save the prediction
                f.write(predicted_sql + "\n")

                # Get corresponding gold query and db_id from the batch_data
                gold_response = batch_data['response'][j]
                gold_sql = "SELECT " + gold_response
                db_id = batch_data['db_id'][j]
                
                db_path = os.path.join(args.db_dir, db_id, db_id + ".sqlite")

                # Perform evaluation
                try:
                    # eval_exec_match is not async, so we don't need to run it in an event loop here.
                    # It handles its own asyncio.run call internally.
                    exec_score = eval_exec_match(
                        db=db_path,
                        p_str=predicted_sql,
                        g_str=gold_sql,
                        plug_value=False,
                        keep_distinct=False,
                        progress_bar_for_each_datapoint=False
                    )
                except Exception as e:
                    print(f"Error evaluating question {item_index}: {e}")
                    exec_score = 0 # Consider it incorrect if evaluation fails

                total_questions += 1
                if exec_score == 1:
                    correct_predictions += 1
                    result_msg = f"Question {item_index} - CORRECT"
                    print(result_msg)
                    eval_f.write(result_msg + "\n")
                else:
                    result_msg = f"Question {item_index} - INCORRECT"
                    gold_msg = f"  - Gold: {gold_sql}"
                    pred_msg = f"  - Pred: {predicted_sql}"
                    print(result_msg)
                    print(gold_msg)
                    print(pred_msg)
                    eval_f.write(result_msg + "\n")
                    eval_f.write(gold_msg + "\n")
                    eval_f.write(pred_msg + "\n")

                # Calculate and print running accuracy
                if total_questions > 0:
                    running_accuracy = (correct_predictions / total_questions) * 100
                    accuracy_msg = f"Running Accuracy: {running_accuracy:.2f}% ({correct_predictions}/{total_questions})"
                    print(accuracy_msg)
                    eval_f.write(accuracy_msg + "\n")
            
            # Ensure the file is written to disk after each batch
            f.flush()
            eval_f.flush()

    # MODIFICATION: Print and save final results
    separator = "\n" + "="*20
    header = "      FINAL RESULTS      "
    print(separator)
    print(header)
    print("="*20)

    with open(eval_out_file, "a") as eval_f:
        eval_f.write(separator + "\n")
        eval_f.write(header + "\n")
        eval_f.write("="*20 + "\n")

        if total_questions > 0:
            final_accuracy = (correct_predictions / total_questions) * 100
            total_msg = f"Total Questions Evaluated: {total_questions}"
            correct_msg = f"Correct Predictions: {correct_predictions}"
            accuracy_msg = f"Final Execution Accuracy: {final_accuracy:.2f}%"

            print(total_msg)
            print(correct_msg)
            print(accuracy_msg)

            eval_f.write(total_msg + "\n")
            eval_f.write(correct_msg + "\n")
            eval_f.write(accuracy_msg + "\n")
        else:
            no_eval_msg = "No questions were evaluated."
            print(no_eval_msg)
            eval_f.write(no_eval_msg + "\n")