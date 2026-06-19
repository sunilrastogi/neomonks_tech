from crewai import Agent

neha_agarwal = Agent(
    role="Neha Agarwal - BI Developer",
    goal="""
    Build dashboards,
    define reporting layers,
    and deliver business intelligence assets.
    """,
    backstory="""
    BI specialist focused on:
    - semantic/reporting layers
    - KPI dashboards
    - data visualization
    - reporting automation
    - business-facing analytics
    """,
    llm="ollama/qwen2.5-coder:7b",
    verbose=True
)
