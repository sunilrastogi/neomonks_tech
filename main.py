from crewai import Crew

from agents.priya_nair_frontend_dev import priya_nair
from tasks.frontend_tasks import frontend_login_task

crew = Crew(
    agents=[priya_nair],
    tasks=[frontend_login_task],
    verbose=True
)

result = crew.kickoff()

print(result)
