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
