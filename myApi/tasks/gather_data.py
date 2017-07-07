# encoding=utf-8
from mrq.task import Task
from mrq.context import log


class SaveUseRate(Task):
    def connect(self):
        import os, django
        import sys
        sys.path.append("/home/django/linshi_package_sys/")
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_api.settings")
        django.setup()
        
    def run(self, params):
        self.connect()
        from myApi.models import Userate
        log.info(params['rate'])
        file_name = 'static/%s.png' % params['filename']
        new_use_rate = Userate(name=file_name, rate=params['rate'])
        new_use_rate.save()
        log.info('save the  single use rate')


class SaveProductRate(Task):
    def connect(self):
        import os, django
        import sys
        sys.path.append("/home/django/linshi_package_sys/")
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "django_api.settings")
        django.setup()

    def run(self, params):
        self.connect()
        from myApi.models import Project, ProductRateDetail
        project = Project(
            comment=params['data']['project_comment'],
            data_input=params['data']['shape_data'] + params['data']['bin_data']
        )
        project.save()
        # save product
        for res in params['results']['statistics_data']:
            product = ProductRateDetail(
                sheet_name=res['name'],
                num_sheet=res['num_sheet'],
                avg_rate=res['rate'],
                rates=res['rates'],
                detail=res['detail'],
                num_shape=res['num_shape'],
                sheet_num_shape=res['sheet_num_shape'],
                pic_url='static/%s%s.png' % (params['filename'], res['bin_type']),
                same_bin_list=res['same_bin_list'],
                empty_sections=res['empty_sections'],
                algorithm=res['algo_id'],
                empty_section_ares=res['empty_section_ares'],
                total_rates=res['total_rates']
            )
            product.save()
            project.products.add(product)
        project.save()
        # TODO:数据库操作转移
        url_res = my_settings.BASE_URL + 'project_detail/' + str(project_id)
        # 更新数据库
        update_mix_status_result(guid, url_res)
