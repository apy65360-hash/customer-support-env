import subprocess
import sys

def start_server():
    command = [sys.executable, '-m', 'uvicorn', 'myapp:app']  # Use sys.executable
    subprocess.Popen(command)

if __name__ == '__main__':
    start_server()