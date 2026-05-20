from crewai import Agent

product_owner = Agent(
    role="Product Owner",
    goal="""
    Analyze requirements,
    create tasks,
    manage sprint workflows,
    and coordinate engineering agents.
    """,
    backstory="""
    Senior technical product manager with deep
    expertise in agile systems, sprint planning,
    and engineering coordination.
    """,
    llm="ollama/qwen2.5-coder:7b",
    verbose=True
)