# encoding=utf8
import sys
sys.path.append("/home/django/linshi_package_sys")
from mrq.task import Task
from mrq.context import run_task, log
from mrq.job import queue_job, get_job_result
import json
import time
from myApi.my_rectpack_lib.single_use_rate import main_process, use_rate_data_is_valid
from myApi.my_rectpack_lib.package_tools import run_product_rate_task, package_data_check

BASE_URL = 'http://119.145.166.182:8090/'


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

        if params["source_name"] == 'SingleUseRate':

            result = subtask("tasks.package.%s" % params["source_name"], {
                "data": params["post_data"],
                'path': params["path"],
            })

            if not result['error']:
                result = subtask("tasks.gather_data.SaveUseRate", {
                    "rate": result["rate"],
                    'filename': params["filename"],
                })

        if params["source_name"] == 'ProductRate':

            result = subtask("tasks.package.%s" % params["source_name"], {
                "data": params["post_data"],
                'path': params["path"],
                'filename': params["filename"],
            })

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


class ProductRate(Task):
    def connect(self):
        import os, django
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_api.settings")
        django.setup()

    def run(self, params):
        res_check = package_data_check(params.get("data"))
        if res_check['error']:
            # 出错退出
            return res_check
        elif not res_check['row_id']:
            # 所有条件相同直接退出
            return res_check

        # 是否参数相同
        from myApi.models import Project
        from myApi.views import create_project
        from myApi.my_rectpack_lib.sql import update_mix_status_result, update_mix_status

        project = Project.objects.filter(data_input=params.get("data")['shape_data'] + params.get("data")['bin_data']).last()
        if project:
            if project.comment != params.get("data")['project_comment']:
                project.comment = params.get("data")['project_comment']
                all_products = project.products.all()
                # 新建一个项目，与原来项目一样，只是换了一个描述
                project.pk = None
                project.save()
                for product in all_products:
                    project.products.add(product)

                project.save()

            content = BASE_URL + 'project_detail/' + str(project.id)
            # 更新数据库
            update_mix_status_result(res_check['row_id'], content)
            return content

        res = run_product_rate_task(
            params.get("data"),
            res_check['row_id'],
            params.get("path"),
        )
        if res['error']:
            log.info('has some error during the work')
            update_mix_status(guid=res_check['row_id'], status=res['info'])
        else:
            try:
                project_id = create_project(res, params.get("data"), params.get("filename"))
                url_res = BASE_URL + 'project_detail/' + str(project_id)
                # 更新数据库
                update_mix_status_result(res_check['row_id'], url_res)
            except:
                update_mix_status(guid=res_check['row_id'], status=u'保存结果出错')
        return res