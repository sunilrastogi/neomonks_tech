from crewai import Task
from agents.vikram_singh_infra_admin import vikram_singh

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
    agent=vikram_singh
)
