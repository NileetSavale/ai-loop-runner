import git


def git_commit(repo_path: str, message: str) -> str:
    repo = git.Repo(repo_path)
    repo.git.add(A=True)
    commit = repo.index.commit(message)
    return commit.hexsha
