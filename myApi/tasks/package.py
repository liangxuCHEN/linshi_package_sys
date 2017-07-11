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
from myApi.my_rectpack_lib.package_tools import run_product_rate_task, package_main_function
from myApi.my_rectpack_lib.package_script_find_best_piece import generate_work, find_best_piece, multi_piece
from myApi.my_rectpack_lib.sql import get_data


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
            return result

        if params["source_name"] == 'ProductRate':
            row_id = params.get('row_id')
            job_id = queue_job("tasks.package.%s" % params["source_name"], {
                "data": params["post_data"],
                'path': params["path"],
                'filename': params["filename"],
                'row_id': row_id
            }, queue='product_rate')
            return json.dumps({'job_id': str(job_id)})

        if params["source_name"] == 'FindBestPieceQueen':
            job_id = queue_job("tasks.package.%s" % params["source_name"], {
                "data": params["post_data"],
                'only_one': params["only_one"],
            }, queue='best_num')

            return json.dumps({'job_id': str(job_id)})


class SingleUseRate(Task):
    def run(self, params):
        res = use_rate_data_is_valid(params.get("data"))
        if res['error']:
            return json.dumps(res)

        res = main_process(params.get("data"), params.get("path"))
        return res


class ProductRate(BaseTask):

    def run(self, params):
        # 混排任务调度
        self.connect()
        # has row id, need to save the result in other db
        row_id = params.get("row_id")

        log.info('row id = %s' % row_id)
        from myApi.models import Project
        from myApi.views import create_project
        from myApi.my_rectpack_lib.sql import update_mix_status_result, update_mix_status

        # 如果没有row_id 就不需要保存运行状态，而且没有对比过是否有相同数据，所以要比较一下
        if not row_id:
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
                url_res = my_settings.BASE_URL + 'project_detail/' + str(project.id)
                content['url'] = url_res
                content['project_id'] = str(project.id)

                return json.dumps(content)

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

        # 求出结果，返回数据
        if res['error']:
            log.info(res['info'])
        else:
            try:
                project_id = create_project(res, params.get("data"), params.get("filename"))
                url_res = my_settings.BASE_URL + 'project_detail/' + str(project_id)
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
        rows = None
        output_data = list()
        if params.get('only_one'):
            # 先插入数据库  generate_work
            res_data = generate_work(params.get("data"))
            if not res_data['IsErr']:
                rows = get_data(bom_version=res_data['data'][0]['BOMVersion'])
        else:
            rows = get_data()

        if rows:
            for input_data in rows:
                job_id = queue_job("tasks.package.FindBestPiece", {
                    'input_data': input_data
                }, queue='best_num')
                log.info('job_id = %s' % str(job_id))
                output_data.append({'job_id': str(job_id)})
        return json.dumps(output_data)


class FindBestPiece(BaseTask):

    def run(self, params):
        """
        找最佳生产数量任务
        :param params:
        :return:
        """
        self.connect()
        from myApi.views import create_project
        from myApi.models import Project
        from myApi.my_rectpack_lib.sql import update_result
        content_2 = {}
        input_data = params.get("input_data")
        # 寻找最佳生产数量
        error, result = find_best_piece(input_data["ShapeData"], input_data["BinData"])

        content_2['BOMVersion'] = input_data['BOMVersion']
        content_2['SkuCode'] = input_data['SkuCode']
        content_2['Created'] = dt.today()

        if error:
            content_2['status'] = my_settings.NO_NUM_STATUS
            update_result(content_2)
            log.error('work BOMVersion=%s has error in input data ' % input_data['BOMVersion'])
            return content_2

        else:
            log.info('finish work BOMVersion=%s, best piece is %d and begin to draw the solution' % (
                input_data['BOMVersion'], result['piece']))
            content_2['best_num'] = result['piece']
            # new post product rate job, 拿到job id 等待计算结束，取得project id， 再去找结果
            try:
                res_product, values, filename = run_product_rate_func(Project,
                                                                      result['piece'],
                                                                      input_data['ShapeData'],
                                                                      input_data['BinData'],
                                                                      comment=input_data['Product'])

            except Exception as e:
                log.error(e)
                content_2['status'] = u'生产项目详细页面出错'
                update_result(content_2)
                return content_2

            if res_product['error']:
                log.error(res_product)
                content_2['status'] = u'生产项目详细页面出错'
                update_result(content_2)
                return content_2

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
                            return content_2
                    except:
                        log.error('has error during calculating the rates')
                        log.error(res_product)
                        content_2['status'] = u'保存项目展示页面出错'
                        update_result(content_2)
                        return content_2
                else:
                    rates = res_product['rates']

                # 返回正确结果，保存数据到数据库
                content_2['status'] = my_settings.OK_STATUS
                content_2['url'] = res_product['url']
                content_2['rates'] = list()
                if content_2['status'] == my_settings.OK_STATUS:
                    for skucode, rate in rates.items():
                        content_2['rates'].append((input_data['SkuCode'], content_2['BOMVersion'], skucode, rate))

                update_result(content_2)
                return content_2


def run_product_rate_func(project_model, num_piece, shape_data, bin_data, comment):
    """
    生产详细排版信息
    :param project_model: django Project model
    :param num_piece:  最佳生产数量
    :param shape_data:
    :param bin_data:
    :param comment:
    :return:
    """
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

        url = my_settings.BASE_URL + 'project_detail/' + str(project.id)
        # 需要rate
        rates = {}
        for p in all_products:
            tmp_list = p.rates.split(', ')
            tmp_list = [float(x) for x in tmp_list]
            rates[str(p.sheet_name.split(' ')[0])] = sum(tmp_list) / len(tmp_list)

        return {'url': url, 'rates': rates, 'error': False}, None, None

    filename = str(time.time()).split('.')[0]
    path = os.path.join(my_settings.BASE_DIR, 'static')
    path = os.path.join(path, filename)
    values = {
        'project_comment': comment,
        'border': 5,
        'shape_data': s_data,
        'bin_data': b_data
    }
    # 创建子任务：根据最佳数量，做详细的排版展示，
    subtask = wait_for_job
    results = subtask("tasks.package.ProductRate", {
        "data": values,
        'path': path,
        'filename': filename,
    }, queue='product_rate')

    return results, values, filename
