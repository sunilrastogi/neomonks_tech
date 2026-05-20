import subprocess


class ShellRunner:

    ALLOWED_COMMANDS = [
        "npm",
        "npx",
        "pip",
        "python",
        "django-admin",
        "git"
    ]

    @staticmethod
    def run(command, cwd=None):

        base_command = command.split()[0]

        if base_command not in ShellRunner.ALLOWED_COMMANDS:
            raise Exception(
                f"Command not allowed: {base_command}"
            )

        print(f"\n[RUNNING] {command}\n")

        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True
        )

        print(result.stdout)

        if result.stderr:
            print(result.stderr)

        return result