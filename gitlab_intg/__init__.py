import pandas as pd
import functools
import time
from tabulate import tabulate

class Approvals:
    def __init__(self, project, mr_id):
        self.project = project
        self.mr = project.mergerequests.get(mr_id)

    def get_approval_rules(self):
        approval_rule_mgr = self.project.approvalrules

        rules = {}
        if approval_rule_mgr is not None:
            for rule in approval_rule_mgr.list():
                if len(rule.eligible_approvers) > 0:
                    rules[rule.name] = list(map(lambda approver : approver['username'], rule.eligible_approvers))
        return rules

    def get_approvers(self):
        approval_mgr = self.mr.approvals
        approval = approval_mgr.get()
        return list(map(lambda user : user['user']['username'], approval.approved_by))

    def get_approval_status(self):
        approved_by = self.get_approvers()
        approval_rules = self.get_approval_rules()

        is_rm_approved = 'RM' not in approval_rules or any(approver in approval_rules['RM'] for approver in approved_by)
        is_pm_approved = 'PM' not in approval_rules or any(approver in approval_rules['PM'] for approver in approved_by)

        if is_rm_approved and is_pm_approved:
            return 'RM_PM_APPROVED'
        if is_rm_approved:
            return 'RM_APPROVED'
        if is_pm_approved:
            return 'PM_APPROVED'
        return 'PENDING_APPROVAL'


class ReleaseNotes:
    def __init__(self, project, mr_id, engine_project):
        self.project = project
        self.engine_project = engine_project
        self.mr = project.mergerequests.get(mr_id)
        self.mr_id = mr_id

    # UTILITY METHOD to transform a string into a pandas DataFrame
    def str2frame(self, estr, sep = '|', lineterm = '\n', set_header = True):
        dat = [x.split(sep) for x in estr.split(lineterm)][1:-1]
        cdf = pd.DataFrame(dat)
        if set_header:
            cdf = cdf.T.set_index(0, drop = True).T # flip, set ix, flip back
            cdf.columns = cdf.columns.str.strip()
            
        return cdf.iloc[1:]

    def get_raw_notes_df(self):
        notes_mgr = self.mr.notes
        notes_list = list(filter(lambda note : 'Release Details' in note.body, notes_mgr.list()))
        if len(notes_list) > 0:
            mr_note = notes_list[0]
            return self.str2frame(mr_note.body)

        print(f"Could not find Release Notes for MR with id {self.mr_id}")
        return None

    def get_release_notes_df(self):
        df = self.get_raw_notes_df()
        df['New Version'] = df['New Version'].str.extract(r'.*-(.*)-SNAPSHOT.*')
        df['Current Version'] = df['Current Version'].apply(lambda version : '-N/A-SNAPSHOT' if version.strip() == 'N/A' else version).str.extract(r'.*-(.*)-SNAPSHOT.*')
        df['Env'] = df['Client Name'].apply(lambda client : 'UAT' if 'uat' in client else 'PROD')
        df['New Version Branch'] = df['New Version'].apply(self.get_branch_name)
        df['Current Version Branch'] = df['Current Version'].apply(self.get_branch_name)

        return df

    def get_commit_diffs(self):
        diffs = list(map(lambda change : {'path' : change['new_path'], 'diff' : change['diff']}, self.mr.changes()['changes']))
        diff_builder = ""
        for diff in diffs:
            diff_builder = diff_builder + f'{diff["path"]}\n'
            diff_builder = diff_builder + f'{diff["diff"]}\n'
        return diff_builder

    @functools.lru_cache(maxsize=100)
    def get_branch_name(self, version):
        if version == 'N/A':
            return 'N/A'

        commit = self.engine_project.commits.get(version)
        if commit is None:
            return 'N/A'

        release_refs = list(map(lambda r: r['name'], filter(lambda ref: 'release/' in ref['name'], commit.refs())))

        return release_refs[0] if len(release_refs) > 0 else commit.last_pipeline['ref']

    def get_release_summary(self):
        summary_builder = ""
        separator = "\n------------------------------------------------------------------------\n"

        df = self.get_release_notes_df()
        grouped_df = df.groupby(['Env', 'Action', 'New Version', 'New Version Branch', 'Current Version', 'Current Version Branch'])
        result_df = pd.DataFrame(grouped_df.size().reset_index(name='Group Count'))

        summary_builder = summary_builder + "```" + self.get_commit_diffs() + "```"
        summary_builder = summary_builder + separator

        summary_builder = summary_builder + "```" + tabulate(result_df) + "```" + "\n\n"

        approvals = Approvals(self.project, self.mr_id)
        summary_builder = summary_builder + "```" + approvals.get_approval_status() + "\n"
        summary_builder = summary_builder + f"Status of MR : {self.mr.state}```"
        summary_builder = summary_builder + separator

        return summary_builder


class MergeReleaseOperations:
    def __init__(self, project, mr_id, rm_user, gitlab_job_base_url):
        self.project = project
        self.mr = project.mergerequests.get(mr_id)
        self.mr_id = mr_id
        self.approvals = Approvals(project, mr_id)
        self.rm_user = rm_user
        self.gitlab_job_base_url = gitlab_job_base_url

    def approve_mr(self):
        if self.rm_user in self.approvals.get_approvers():
            print(f"MR {self.mr_id} is already approved")
        else:
            self.mr.approve()
            print(f"Approved MR {self.mr_id} successfully")

    def merge_mr(self):
        if self.mr.state == 'merged':
            print(f"MR {self.mr_id} is already merged")
            return True

        print(f"Merge status : {self.mr.merge_status}")
        if self.mr.merge_status == 'can_be_merged':
            self.mr.merge()
            print(f"Merged MR {self.mr_id} successfully")
            return True

        # cannot_be_merged
        return False

    # T => trigger only 'deploy-prod' job
    # F => trigger only 'deploy-wpf-prod' job
    # T,F => trigger both the jobs
    def trigger_pipeline(self, job_aliases=['T']):
        job_name_to_alias_map = {'deploy-prod' : 'T', 'deploy-wpf-prod' : 'F'}
        job_filter_fn = lambda job_name : job_name in job_name_to_alias_map and job_name_to_alias_map[job_name] in job_aliases

        new_pipeline = self.project.pipelines.create({'ref': 'main'})
        print(f"Pipeline with id {new_pipeline.id} successfully created")

        new_ppl_job_list = list(filter(lambda job: job_filter_fn(job.name), new_pipeline.jobs.list()))

        job = None
        job_ids = []
        job_urls = []
        if(len(new_ppl_job_list) > 0):
            for new_ppl_job in new_ppl_job_list:

                print(f"Triggering job with id {new_ppl_job.id}")

                job = self.project.jobs.get(new_ppl_job.id, lazy=True)
                job.play()
                job_ids.append(job.id)
                job_urls.append(f"{self.gitlab_job_base_url}/{job.id}")

        return {"pipeline_id" : new_pipeline.id,
                "job_id" : str(job_ids),
                "job_url" : str(job_urls),
                "job_created" : len(job_ids) > 0}

    def perform_mr_operations(self, operations, MAX_ITERATIONS=10, wait_time_sec=3):
        if 'A' in operations:
            self.approve_mr()

        result = True
        if 'M' in operations:
            count = 0

            result = False
            while(result == False and count < MAX_ITERATIONS):
                count = count+1

                print(f"Checking if MR {self.mr_id} is PM approved. {MAX_ITERATIONS-count} attempts left")
                
                if 'RM_PM_APPROVED' == self.approvals.get_approval_status():
                    result = self.merge_mr()

                if result == False:
                    print("Waiting till update_mr pipeline is complete and MR is ready to be merged")
                    time.sleep(wait_time_sec)

        pipeline_result = None
        if result and ('T' in operations or 'F' in operations):
            # Note operations is a subset of ['A', 'M', 'T', 'F']
            # 'T' and 'F' is all that matters to trigger_pipeline
            pipeline_result = self.trigger_pipeline(job_aliases=operations)

        return {
            'APPROVAL_STATUS' : self.approvals.get_approval_status(),
            'MERGE_STATUS' : self.mr.state,
            'PIPELINE_STATUS' : pipeline_result
        }


