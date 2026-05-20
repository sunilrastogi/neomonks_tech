from crewai import Task
from agents.infra_admin import infra_admin

bootstrap_product_task = Task(
    description="""
    Setup a new product workspace called:

    expense_tracker

    STRICT RULES:
    - Return ONLY machine-readable output
    - Do NOT explain anything
    - Do NOT use bullet points
    - Do NOT add commentary
    - Do NOT add markdown outside code blocks

    REQUIRED OUTPUT FORMAT:

    CREATE_FOLDER: products/expense_tracker/frontend
    CREATE_FOLDER: products/expense_tracker/backend
    CREATE_FOLDER: products/expense_tracker/infra
    CREATE_FOLDER: products/expense_tracker/docs
    CREATE_FOLDER: products/expense_tracker/tests

    CREATE_FILE: products/expense_tracker/README.md
    ```md
    # Expense Tracker
    ```

    CREATE_FILE: products/expense_tracker/.env.example
    ```env
    DEBUG=True
    ```

    ONLY return output in this format.
    """,
    expected_output="""
    Strictly structured filesystem output.
    """,
    agent=infra_admin
)