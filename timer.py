from json import loads, dumps
from time import time
from argparse import ArgumentParser

def start_timer(file_path, timer_name):
    try:
        with open(file_path, "r") as f:
            timers = loads(f.read())
    except FileNotFoundError:
        timers = {}

    timers[timer_name] = {"start": time(), "last_read": time()}

    with open(file_path, "w") as f:
        f.write(dumps(timers))

    print(f"Timer '{timer_name}' started.")

def stop_timer(file_path, timer_name):
    try:
        with open(file_path, "r") as f:
            timers = loads(f.read())
    except FileNotFoundError:
        print(f"Timer '{timer_name}' not found.")
        return

    if timer_name not in timers:
        print(f"Timer '{timer_name}' not found.")
        return
    dto = timers.pop(timer_name)
    elapsed = time() - dto["start"]
    segment = time() - dto["last_read"]

    with open(file_path, "w") as f:
        f.write(dumps(timers))

    print(f"Timer '{timer_name}' stopped. Elapsed time: {elapsed:.2f} seconds. Last segment: {segment:.2f} seconds.")

def get_timer(file_path, timer_name):
    try:
        with open(file_path, "r") as f:
            timers = loads(f.read())
    except FileNotFoundError:
        print(f"Timer '{timer_name}' not found.")
        return

    if timer_name not in timers:
        print(f"Timer '{timer_name}' not found.")
        return

    elapsed = time() - timers[timer_name]["start"]
    segment = time() - timers[timer_name]["last_read"]
    timers[timer_name]["last_read"] = time()
    with open(file_path, "w") as f:
        f.write(dumps(timers))
    print(f"Timer '{timer_name}' elapsed time: {elapsed:.2f} seconds. Last segment: {segment:.2f} seconds.")


def main():
    parser = ArgumentParser(description="Timer utility")
    parser.add_argument("command", choices=["start", "get", "stop"], help="Command to execute")
    parser.add_argument("--file", default="timer.json", help="File to store timer data")
    parser.add_argument("--name", default="default", help="Name of the timer")

    args = parser.parse_args()

    if args.command == "start":
        start_timer(args.file, args.name)
    elif args.command == "stop":
        stop_timer(args.file, args.name)
    elif args.command == "get":
        get_timer(args.file, args.name)

if __name__ == "__main__":
    main()