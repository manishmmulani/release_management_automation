from gitlab_intg import ReleaseNotes, MergeReleaseOperations
from gitlab import Gitlab
import requests
import os

def get_project_id(project):
    project_dict = {"main_gitlab_project_id" : os.environ.get('main_gitlab_project_id'),
                    "secondary_gitlab_project_id" : os.environ.get('secondary_gitlab_project_id')
                    }
    return project_dict[project]

def approval_merge_pipeline_summary(result):

    pipeline_status = result['PIPELINE_STATUS']
    pipeline_summary = 'N/A'

    if pipeline_status is not None:
        if pipeline_status['job_created'] is not None:
            pipeline_summary = f"Job created {pipeline_status['job_url']}"
        else:
            pipeline_summary = f"Job creation failed for pipeline {pipeline_status['pipeline_id']}"

    summary_builder = "```"
    summary_builder = summary_builder + f"Approval Status : {result['APPROVAL_STATUS']}\n"
    summary_builder = summary_builder + f"Merge Status : {result['MERGE_STATUS']}\n"
    summary_builder = summary_builder + f"Pipeline Status : {pipeline_summary}"
    summary_builder = summary_builder + "```"

    return summary_builder

def notify(summary, url):
    if url is not None:
        print(f"Notification Endpoint : {url}")
        payload = {'text' : summary}
        response = requests.post(url=url, json=payload)
        print(f"Posted summary to notification endpoint and got response status {response.ok} and content {response.content}")

# command = grn {mr_id} -> Get Release Notes
# command = amt {mr_id} -> approve, merge MR and trigger pipeline
# command = am  {mr_id} -> approve, merge MR 

# response_url is the slack webhook to post back the response (to the channel where the request originated)
# workflow_status_webhook could be different for response_url, as approval/merge/pipeline status needs to be published there

def run(cmd, mr_id, response_url=None, workflow_status_webhook=None):
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
        notify(summary=summary, url=response_url)
    
    elif cmd == "am" or cmd == "amt":
        mr_operations = MergeReleaseOperations(project, mr_id, user)
        op = [c for c in cmd.upper()]
        result = mr_operations.perform_mr_operations(operations=op, MAX_ITERATIONS=14, wait_time_sec=60)
        summary = approval_merge_pipeline_summary(result)
        notify(summary=summary, url=workflow_status_webhook)

    else:
        notify(summary=summary, url=response_url)

    print("Returning Summary")
    return summary

if __name__ == '__main__':
    #result = run("grn", 797)
    result = run("am", 797)
    print(result)
