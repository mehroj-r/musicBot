import subprocess
import time


def valid_filename(filename: str) -> str:

    illegal_chars = ["\\", "/", ":", "*", "?", "\"", "<", ">", "|"]

    valid = ""
    for i in filename:
        if i in illegal_chars:
            valid += "_"
        else:
            valid += i
    return valid.strip(".")


def run_subprocess(command: list[str]) -> list[str]:

    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    while result.returncode != 0:
        time.sleep(3)
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    return result.stdout.split('\n')
