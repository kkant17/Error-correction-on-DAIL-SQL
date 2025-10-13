# Read input file and write processed lines to output file
input_file = "D:\Code\AI\Error-correction-on-DAIL-SQL\dataset\process\SPIDER-TEST_SQL_3-SHOT_EUCDISQUESTIONMASK_QA-EXAMPLE_CTX-200_ANS-4096\RESULTS_MODEL-mistral.txt"
output_file = "D:\Code\AI\Error-correction-on-DAIL-SQL\dataset\process\SPIDER-TEST_SQL_3-SHOT_EUCDISQUESTIONMASK_QA-EXAMPLE_CTX-200_ANS-4096\Results_Original.txt"

with open(input_file, "r") as infile, open(output_file, "w") as outfile:
    for line in infile:
        line = line.strip()
        if not line:
            continue  # skip empty lines
        parts = line.split(";", 1)
        if len(parts) > 1:
            clean_line = parts[0] + ";"
        else:
            clean_line = parts[0]
        if clean_line:  # skip if still empty
            outfile.write(clean_line + "\n")
