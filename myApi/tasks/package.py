import sys
sys.path.append("/home/django/linshi_package_sys")
from mrq.task import Task
from mrq.context import run_task, log
from mrq.job import queue_job, get_job_result
import json
import time
from myApi.my_rectpack_lib.single_use_rate import main_process, use_rate_data_is_valid

# Creates end-to-end tasks

def wait_for_job(path, params, **kwargs):
    job_id = queue_job(path, params, **kwargs)

    while True:
        time.sleep(5)
        res = get_job_result(job_id)
        if res["status"] == "success":
            return res.get("result")
        elif res["status"] not in ["queued", "started", "interrupt"]:
            raise Exception("Job %s was in status %s" % (
                path, res.get("status")
            ))


class CreateTask(Task):
    def run(self, params):
        subtask = wait_for_job
        result = subtask("tasks.package.%s" % params["source_name"], {
            "data": params["data"],
            'path': params["path"],
        })

        # result = json.loads(result)
        if params["source_name"] == 'SingleUseRate':
            if not result['error']:
                result = subtask("tasks.gather_data.SaveUseRate", {
                    "rate": result["rate"],
                    'filename': params["filename"],
                })



class SingleUseRate(Task):
    def run(self, params):
        res = use_rate_data_is_valid(params.get("data"))
        if res['error']:
            return json.dumps(res)

        res = main_process(params.get("data"), params.get("path"))
        return res
