from utils.shell_runner import ShellRunner


class ProductInitializer:

    @staticmethod
    def initialize_frontend(product_path):

        frontend_path = f"{product_path}/frontend"

        ShellRunner.run(
            "npm create vite@latest . -- --template react-ts",
            cwd=frontend_path
        )

        ShellRunner.run(
            "npm install",
            cwd=frontend_path
        )

    @staticmethod
    def initialize_backend(product_path):

        backend_path = f"{product_path}/backend"

        ShellRunner.run(
            "python -m venv venv",
            cwd=backend_path
        )

        pip_command = (
            "venv\\Scripts\\pip install "
            "django djangorestframework psycopg[binary]"
        )

        ShellRunner.run(
            pip_command,
            cwd=backend_path
        )

        django_command = (
            "venv\\Scripts\\django-admin startproject core ."
        )

        ShellRunner.run(
            django_command,
            cwd=backend_path
        )