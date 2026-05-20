import re


class OutputParser:

    @staticmethod
    def extract_files(text):

        pattern = r"CREATE_FILE:\s*(.*?)\n```[a-zA-Z]*\n(.*?)```"

        matches = re.findall(pattern, text, re.DOTALL)

        files = []

        for path, content in matches:

            files.append({
                "path": path.strip(),
                "content": content.strip()
            })

        return files

    @staticmethod
    def extract_folders(text):

        pattern = r"CREATE_FOLDER:\s*(.*)"

        matches = re.findall(pattern, text)

        return [m.strip() for m in matches]