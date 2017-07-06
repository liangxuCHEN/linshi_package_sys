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

