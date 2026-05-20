from git import Repo


class GitManager:

    def __init__(self, repo_path="."):
        self.repo = Repo(repo_path)

    def create_branch(self, branch_name):

        existing_branches = [b.name for b in self.repo.branches]

        if branch_name not in existing_branches:
            self.repo.git.checkout("-b", branch_name)
            print(f"[BRANCH CREATED] {branch_name}")
        else:
            self.repo.git.checkout(branch_name)
            print(f"[BRANCH SWITCHED] {branch_name}")

    def commit_all(self, message):

        self.repo.git.add(A=True)

        if self.repo.is_dirty():
            self.repo.index.commit(message)
            print(f"[COMMIT CREATED] {message}")
        else:
            print("[NO CHANGES TO COMMIT]")

    def push_branch(self, branch_name):

        origin = self.repo.remote(name="origin")
        origin.push(branch_name)

        print(f"[BRANCH PUSHED] {branch_name}")