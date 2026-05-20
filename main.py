from crewai import Crew

from agents.frontend_dev import frontend_dev
from tasks.frontend_tasks import frontend_login_task

crew = Crew(
    agents=[frontend_dev],
    tasks=[frontend_login_task],
    verbose=True
)

result = crew.kickoff()

print(result)