import os


class FileWriter:

    @staticmethod
    def write_file(path, content):

        os.makedirs(os.path.dirname(path), exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"[FILE WRITTEN] {path}")