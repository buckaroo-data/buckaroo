from pathlib import Path
import os

def ensure_file_exists(file_path):
    if not os.path.exists(file_path):
        # Create the file and write an empty string to it
        with open(file_path, 'w') as file:
            file.write('')
        print(f"File '{file_path}' did not exist. An empty file has been created.")
    else:
        print(f"File '{file_path}' already exists.")

print("os.getcwd()", os.getcwd(), "__file__", __file__)

ensure_file_exists(Path(__file__).parent.parent.parent / "buckaroo" / "static" / "compiled.css")
