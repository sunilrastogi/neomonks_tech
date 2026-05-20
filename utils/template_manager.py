import shutil
import os


class TemplateManager:

    @staticmethod
    def copy_template(source, destination):

        if os.path.exists(destination):
            #delete existing destination folder
            shutil.rmtree(destination)

        shutil.copytree(source, destination)

        print(f"[TEMPLATE COPIED] {source} -> {destination}")