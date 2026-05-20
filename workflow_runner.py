from importlib.metadata import files

from crewai import Crew

from agents.infra_admin import infra_admin
from tasks.product_bootstrap_tasks import bootstrap_product_task

from utils.output_parser import OutputParser
from utils.file_writer import FileWriter
from utils.folder_manager import FolderManager
from workflows.product_initializer import ProductInitializer


def bootstrap_product():

    print("\\n=== PRODUCT BOOTSTRAP STARTED ===\\n")

    crew = Crew(
        agents=[infra_admin],
        tasks=[bootstrap_product_task],
        verbose=True
    )

    result = crew.kickoff()

    result_text = str(result)

    print("\n===== RAW AGENT OUTPUT =====\n")
    print(result_text)
    print("\n============================\n")

    folders = OutputParser.extract_folders(result_text)

    print("\nEXTRACTED FOLDERS:")
    print(folders)

    for folder in folders:
        FolderManager.create_folder(folder)

    files = OutputParser.extract_files(result_text)

    print("\nEXTRACTED FILES:")
    print(files)

    for file in files:
        FileWriter.write_file(
            file["path"],
            file["content"]
        )

    product_path = "products/expense_tracker"

    print("\\n=== Initializing Frontend ===\\n")
    ProductInitializer.initialize_frontend(product_path)
    
    print("\\n=== Initializing Backend ===\\n")
    ProductInitializer.initialize_backend(product_path)

    print("\\n=== PRODUCT BOOTSTRAP COMPLETE ===\\n")


if __name__ == "__main__":
    bootstrap_product()