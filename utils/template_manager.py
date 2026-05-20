import shutil
import os


class TemplateManager:

    @staticmethod
    def copy_template(source, destination):

        if os.path.exists(destination):
            print(f"[SKIPPED] {destination} already exists")
            return

        shutil.copytree(source, destination)

        print(f"[TEMPLATE COPIED] {source} -> {destination}")