import sys
sys.path.append("/home/louis/django_1.10/linshi_package_sys")
from mrq.context import connections, log
from mrq.job import queue_job
from mrq.task import Task
from mrq.queue import Queue
from mrq.context import retry_current_job
import time
from myApi.my_rectpack_lib.single_use_rate import main_process, use_rate_data_is_valid
import json

class Fetch(Task):
    def run(self, params):
        t = params['url']
        time.sleep(len(t))
        return len(t)


class Add(Task):

    def run(self, params):
        log.info("adding", params)
        res = params.get("a", 0) + params.get("b", 0)

        if params.get("sleep", 0):
            log.info("sleeping", params.get("sleep", 0))
            time.sleep(params.get("sleep", 0))

        return res

class SingleUseRate(Task):
    def run(self, params):
    	res = use_rate_data_is_valid(params.get("data"))
    	if res['error']:
    		return json.dumps(res)

        res = main_process(params.get("data"), params.get("path"))
        return res['rate']


# class BaseTask(Task):

#   retry_on_http_error = True

#   def validate_params(self, params):
#     """ Make sure some standard parameters are well-formatted """
#     if "url" in params:
#       assert "://" in params["url"]

#   def run_wrapped(self, params):
#     """ Wrap all calls to tasks in init & safety code. """

#     self.validate_params(params)

#     try:
#       return self.run(params)

#     # Intercept HTTPErrors in all tasks and retry them by default
#     except urllib2.HTTPError, e:
#       if self.retry_on_http_error:
#         retry_current_job()