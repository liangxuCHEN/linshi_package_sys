# encoding=utf-8
import sys
sys.path.append("/home/django/linshi_package_sys")
from mrq.task import Task
from mrq.context import run_task, log
from mrq.job import queue_job, get_job_result
import json
import time
import os
from datetime import datetime as dt
from myApi import my_settings
from myApi.my_rectpack_lib.single_use_rate import main_process, use_rate_data_is_valid
from myApi.my_rectpack_lib.package_tools import run_product_rate_task, package_data_check, package_main_function
from myApi.my_rectpack_lib.package_script_find_best_piece import generate_work,find_best_piece, multi_piece
from myApi.my_rectpack_lib.sql import get_data

BASE_URL = 'http://192.168.3.172:8089/'
BASE_DIR = '/home/django/linshi_package_sys'


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


class BaseTask(Task):

    def connect(self):
        """
        load django settings for using the model
        :return:
        """
        import django
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_api.settings")
        django.setup()

    def run(self, params):
        pass


class CreateTask(Task):
    def run(self, params):
        subtask = wait_for_job
        result = None
        if params["source_name"] == 'SingleUseRate':

            result = subtask("tasks.package.%s" % params["source_name"], {
                "data": params["data"],
                'path': params["path"],
            })

            # use other task for saving the result into db
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

        if params["source_name"] == 'FindBestPieceQueen':

            result = subtask("tasks.package.%s" % params["source_name"], {
                "data": params["post_data"],
                'only_one': params["only_one"],
            })

        return result


class SingleUseRate(Task):
    def run(self, params):
        res = use_rate_data_is_valid(params.get("data"))
        if res['error']:
            return json.dumps(res)

        res = main_process(params.get("data"), params.get("path"))
        return res


class ProductRate(BaseTask):

    def run(self, params):
        self.connect()
        # has row id, need to save the result in other db
        row_id = None
        if 'userName' in params.get("data").keys():
            res_check = package_data_check(params.get("data"))
            if res_check['error']:
                return res_check
            elif not res_check['row_id']:
                return res_check

            row_id = res_check['row_id']

        from myApi.models import Project
        from myApi.views import create_project
        from myApi.my_rectpack_lib.sql import update_mix_status_result, update_mix_status

        project = Project.objects.filter(data_input=params.get("data")['shape_data'] + params.get("data")['bin_data']).last()
        if project:
            if project.comment != params.get("data")['project_comment']:
                project.comment = params.get("data")['project_comment']
                all_products = project.products.all()
                project.pk = None
                project.save()
                for product in all_products:
                    project.products.add(product)

                project.save()

            content = {}
            url_res = BASE_URL + 'project_detail/' + str(project.id)
            content['url'] = url_res
            content['project_id'] = str(project.id)

            if row_id:
                content['guid'] = row_id
                update_mix_status_result(row_id, content)
            return content

        if row_id:
            res = run_product_rate_task(
                params.get("data"),
                row_id,
                params.get("path"),
            )
        else:
            res = package_main_function(
                params.get("data"),
                params.get("path"),
            )

        if res['error']:
            log.info(res['info'])
        else:
            try:
                project_id = create_project(res, params.get("data"), params.get("filename"))
                url_res = BASE_URL + 'project_detail/' + str(project_id)
                res['url'] = url_res
                res['project_id'] = project_id
                if row_id:
                    res['guid'] = row_id
                    update_mix_status_result(row_id, url_res)
            except:
                if row_id:
                    update_mix_status(guid=row_id, status=u'保存结果出错')
        return res


class FindBestPieceQueen(BaseTask):

    def run(self, params):
        self.connect()
        from myApi.views import create_project
        from myApi.models import Project
        from myApi.my_rectpack_lib.sql import update_result

        rows = None
        output_result = []
        subtask = wait_for_job
        if params.get('only_one'):
            res_data = generate_work(params.get("data"))
            if not res_data['IsErr']:
                rows = get_data(bom_version=res_data['data'][0]['BOMVersion'])
        else:
            rows = get_data()

        if rows:
            for input_data in rows:
                content_2 = {}
                # new task for find best piece
                res_task = subtask("tasks.package.FindBestPiece", {
                    "shape_data": input_data['ShapeData'],
                    'bin_data': input_data['BinData'],
                })
                content_2['BOMVersion'] = input_data['BOMVersion']
                content_2['SkuCode'] = input_data['SkuCode']
                content_2['Created'] = dt.today()
                if res_task['error']:
                    content_2['status'] = my_settings.NO_NUM_STATUS
                    update_result(content_2)
                    log.error('work BOMVersion=%s has error in input data ' % input_data['BOMVersion'])

                else:
                    log.info('finish work BOMVersion=%s, best piece is %d and begin to draw the solution' % (
                        input_data['BOMVersion'], res_task['result']['piece']))
                    content_2['best_num'] = res_task['result']['piece']
                    # new post product rate job, 拿到job id 等待计算结束，取得project id， 再去找结果
                    try:
                        res_product, values, filename = run_product_rate_func(Project,
                            res_task['result']['piece'], input_data['ShapeData'],
                            input_data['BinData'], comment=input_data['Product'])

                    except Exception as e:
                        log.error(e)
                        content_2['status'] = u'生产项目详细页面出错'
                        update_result(content_2)
                        continue

                    if res_product['error']:
                        log.error(res_product)
                        log.error(e)
                        content_2['status'] = u'生产项目详细页面出错'
                        update_result(content_2)

                    else:
                        # 返回每种材料的平均利用率
                        # 如果已经存在相同项目，就直接保存
                        if 'rates' not in res_product.keys():
                            rates = {}
                            try:
                                if 'statistics_data' in res_product.keys():
                                    for res in res_product['statistics_data']:
                                        tmp_list = res['rates'].split(', ')
                                        tmp_list = [float(x) for x in tmp_list]
                                        rates[str(res['name'].split(' ')[0])] = sum(tmp_list) / len(tmp_list)
                                    project_id = create_project(res_product, values, filename)
                                    log.info('finish Bom: %s  and the new project id is %s' % (
                                        input_data['BOMVersion'], str(project_id)))
                                else:
                                    log.error('without statistics_data')
                                    log.error(res_product)
                                    content_2['status'] = u'保存项目展示页面出错, 缺少统计数据'
                                    update_result(content_2)
                                    continue
                            except:
                                log.error('has error during calculating the rates')
                                log.error(res_product)
                                content_2['status'] = u'保存项目展示页面出错'
                                update_result(content_2)
                                continue
                        else:
                            rates = res_product['rates']

                        content_2['status'] = my_settings.OK_STATUS
                        content_2['url'] = res_product['url']
                        content_2['rates'] = list()
                        if content_2['status'] == my_settings.OK_STATUS:
                            for skucode, rate in rates.items():
                                content_2['rates'].append((input_data['SkuCode'], content_2['BOMVersion'], skucode, rate))

                        output_result.append({
                            'Bon_version': str(content_2['BOMVersion']),
                            'url': content_2['url']
                        })
                        update_result(content_2)
                        continue

        return json.dumps(output_result)


class FindBestPiece(Task):

    def run(self, params):
        error, result = find_best_piece(params.get("shape_data"), params.get("bin_data"))
        return {'error': error, 'result': result}


def run_product_rate_func(project_model, num_piece, shape_data, bin_data, comment):
    # 整理input data
    s_data, b_data = multi_piece(num_piece, shape_data, bin_data)

    # 添加最优生产数量
    try:
        comment = json.loads(comment)
        comment['Amount'] = num_piece
        comment = json.dumps(comment, ensure_ascii=False)
    except:
        if type(comment) == type('string'):
            comment += ' 最优利用率推荐生产数量=%d' % num_piece

    # 是否参数相同
    project = project_model.objects.filter(data_input=s_data + b_data).last()
    if project:
        all_products = project.products.all()
        if project.comment != comment:
            project.comment = comment
            project.pk = None
            project.save()
            for product in all_products:
                project.products.add(product)
            project.save()

        url = BASE_URL + 'project_detail/' + str(project.id)
        # 需要rate
        rates = {}
        for p in all_products:
            tmp_list = p.rates.split(', ')
            tmp_list = [float(x) for x in tmp_list]
            rates[str(p.sheet_name.split(' ')[0])] = sum(tmp_list) / len(tmp_list)

        return {'url': url, 'rates': rates, 'error':False}, None, None

    filename = str(time.time()).split('.')[0]
    path = os.path.join(BASE_DIR, 'static')
    path = os.path.join(path, filename)
    values = {
        'project_comment': comment,
        'border': 5,
        'shape_data': s_data,
        'bin_data': b_data
    }
    subtask = wait_for_job
    results = subtask("tasks.package.ProductRate", {
        "data": values,
        'path': path,
        'filename': filename,
    })

    return results, values, filename

