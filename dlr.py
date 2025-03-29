import requests
import subprocess

def delete_releases(owner, repo, token):
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }

    # 获取所有发行版
    response = requests.get(f"https://api.github.com/repos/{owner}/{repo}/releases", headers=headers)
    response.raise_for_status()
    releases = response.json()

    # 删除每个发行版
    for release in releases:
        release_id = release["id"]
        response = requests.delete(f"https://api.github.com/repos/{owner}/{repo}/releases/{release_id}", headers=headers)
        if response.status_code == 204:
            print(f"Deleted release {release_id}")
        else:
            print(f"Failed to delete release {release_id}: {response.status_code}")

def delete_tags(owner, repo, token):
    # 获取所有标签
    tags = subprocess.check_output(["git", "ls-remote", "--tags", f"https://github.com/{owner}/{repo}.git"]).decode("utf-8").splitlines()
    tags = [tag.split("/")[-1].strip("^{}") for tag in tags]

    # 删除每个标签
    for tag in tags:
        subprocess.run(["git", "tag", "-d", tag])
        subprocess.run(["git", "push", "origin", "--delete", tag])
        print(f"Deleted tag {tag}")

if __name__ == "__main__":
    import os
    owner = os.getenv("GITHUB_REPOSITORY_OWNER")
    repo = os.getenv("GITHUB_REPOSITORY").split("/")[1]
    token = os.getenv("GITHUB_TOKEN")
    delete_releases(owner, repo, token)
    delete_tags(owner, repo, token)
