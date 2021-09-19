from gitlab_intg import ReleaseNotes, MergeReleaseOperations
from gitlab import Gitlab
import requests
import os

def get_project_id(project):
    project_dict = {"main_gitlab_project_id" : os.environ.get('main_gitlab_project_id'),
                    "secondary_gitlab_project_id" : os.environ.get('secondary_gitlab_project_id')
                    }
    return project_dict[project]

# command = grn {mr_id} -> Get Release Notes
# command = amt {mr_id} -> approve, merge MR and trigger pipeline
# command = am  {mr_id} -> approve, merge MR 

def run(cmd, mr_id, response_url=None):
    print(f"Workflow is being run {mr_id} {response_url}")
    project_id = get_project_id("main_gitlab_project_id")

    private_token = os.environ.get('gitlab_private_token')
    user = os.environ.get('gitlab_rm_user')

    g=Gitlab(url="https://gitlab.com", private_token=private_token)
    project = g.projects.get(id=project_id)
    engine_project = g.projects.get(id=get_project_id('secondary_gitlab_project_id'))

    summary = f"Unsupported command {cmd}"

    if cmd == "grn":
        release_notes = ReleaseNotes(project, mr_id, engine_project)
        summary = release_notes.get_release_summary()
    
    elif cmd == "am" or cmd == "amt":
        mr_operations = MergeReleaseOperations(project, mr_id, user)
        op = [c for c in cmd.upper()]
        result = mr_operations.perform_mr_operations(operations=op, MAX_ITERATIONS=14, wait_time_sec=60)
        summary = f"Status of perform operations {op} is {result}"

    if response_url is not None:
        print(f"Response URL : {response_url}")
        payload = {'text' : summary}
        response = requests.post(url=response_url, json=payload)
        print(f"Posted Release summary to slack with response status {response.ok} and content {response.content}")
    print("Returning Summary")
    return summary

if __name__ == '__main__':
    #result = run("grn", 797)
    result = run("am", 797)
    print(result)
