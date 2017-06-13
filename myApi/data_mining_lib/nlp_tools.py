# -*- coding: utf-8 -*-
import time
import pandas as pd
import jieba
import os
from tgrocery import Grocery
import codecs
from django_api import settings

BASE_DIR = os.path.join(settings.BASE_DIR, 'static')
TEST_FILE = 'motion'


# 读取 filename 路径 的每一行数据 并返回 utf-8
def read_lines(filename):
    fopen = codecs.open(filename, 'r', 'gbk')
    data = []
    for x in fopen.readlines():
        if x.strip() != '':
            data.append(x.strip())
    fopen.close()
    return data


def split_comment(row):
    stop_words = read_lines(os.path.join(BASE_DIR, 'learn', 's_w.txt'))
    content = row['Comment']
    new_sent = list()
    words = jieba.cut(content)
    for word in words:
        if word in stop_words:
            continue
        else:
            new_sent.append(word)
    row['word'] = ' '.join(new_sent)
    return row


def output_file(df_input):
    file_name = 'comment_input_%s' % (str(time.time()).split('.')[0])
    path = os.path.join(BASE_DIR, 'learn', file_name)
    with open(path, 'w') as f:
        for d_index in range(0, len(df_input)):
            text = '%s\t%s\n' % (df_input.iloc[d_index]['Tag'], df_input.iloc[d_index]['Comment'])
            f.write(text.encode('utf-8'))

    return file_name


def learn_model(file_name, test_file_name=None):
    path = os.path.join(BASE_DIR, 'learn', file_name)
    try:
        df = pd.read_excel(path)
    except Exception as e:
        return {'IsErr': True, 'ErrDesc': u'找不到文档或者读取文档出错'}
    try:
        df = df.apply(split_comment, axis=1)
    except Exception as e:
        return {'IsErr': True, 'ErrDesc': u'文档格式有误，应包含Tag（标签名字），Comment（评价内容）'}

    try:
        # 生成学习文档
        learn_file_name = output_file(df)
        tmp_learn_name = os.path.join(BASE_DIR, 'learn', 'model_' + learn_file_name)
        grocery = Grocery(tmp_learn_name)
        path = os.path.join(BASE_DIR, 'learn', learn_file_name)
        grocery.train(path)
        grocery.save()
    except Exception as e:
        return {'IsErr': True, 'ErrDesc': u'学习不成功，没有生产新的模型，请再次尝试。'}

    if test_file_name:
        res = test_sample(tmp_learn_name, test_file_name)
    else:
        res = test_sample(tmp_learn_name, TEST_FILE)

    return {'IsErr': False, 'ErrDesc': u'成功生产新的模型，测试验证的正确率为%s, 模型保存为:%s' % (
        res, os.path.split(tmp_learn_name)[1])}


def test_sample(path, test_path):
    new_grocery = Grocery(path)
    new_grocery.load()
    test_path = os.path.join(BASE_DIR, 'learn', test_path)
    res = new_grocery.test(test_path.encode('utf-8'))
    return str(res)

if __name__ == '__main__':
    print learn_model('learn_01.xls', 'test.txt')

