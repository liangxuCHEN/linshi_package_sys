# encoding=utf8
import os
from django import forms
from django_api import settings
# ALGO_STYLE = (("1", u"算法1"), ("2", u"算法2"), ("3", u"算法3"))


class AlgoForm(forms.Form):
    algo_style = list()
    for i in range(0, 120):
        algo_style.append((str(i), u'算法%d' % i))
    algo_style = tuple(algo_style)
    algo_list = forms.MultipleChoiceField(
        label=u'算法类型',
        choices=algo_style,
        widget=forms.CheckboxSelectMultiple())


class LearnCommentForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(LearnCommentForm, self).__init__(*args, **kwargs)
        path = os.path.join(settings.BASE_DIR, 'static', 'learn')
        path_dir = os.listdir(path)
        learn_file_list = list()

        for file_name in path_dir:
            if 'learn' in file_name:
                learn_file_list.append((file_name, file_name))

        learn_file_list = tuple(learn_file_list)
        self.fields['learn_list'].choices = learn_file_list

    learn_list = forms.ChoiceField(
        label=u'学习文档',
        widget=forms.RadioSelect,
    )


class PredictForm(forms.Form):
    def __init__(self, *args, **kwargs):
        super(PredictForm, self).__init__(*args, **kwargs)
        path = os.path.join(settings.BASE_DIR, 'static', 'learn')
        path_dir = os.listdir(path)
        model_file_list = list()

        for file_name in path_dir:
            if 'model' in file_name:
                model_file_list.append((file_name, file_name))

        model_file_list = tuple(model_file_list)
        self.fields['model_list'].choices = model_file_list

    model_list = forms.ChoiceField(
        label=u'选择模型',
        widget=forms.RadioSelect,
    )

