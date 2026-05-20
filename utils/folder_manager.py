import os


class FolderManager:

    @staticmethod
    def create_folder(path):

        os.makedirs(path, exist_ok=True)

        print(f"[FOLDER CREATED] {path}")