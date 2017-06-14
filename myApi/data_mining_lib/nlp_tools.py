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


def output_file(df_input, num_learn):
    time_mark = str(time.time()).split('.')[0]
    learn_file_name = 'input_comment_%s.txt' % time_mark
    path = os.path.join(BASE_DIR, 'learn', learn_file_name)
    with open(path, 'w') as f:
        for d_index in range(0, num_learn-1):
            text = '%s\t%s\n' % (df_input.iloc[d_index]['Tag'], df_input.iloc[d_index]['word'])
            f.write(text.encode('utf-8'))

    test_file_name = 'test_comment_%s.txt' % time_mark
    path = os.path.join(BASE_DIR, 'learn', test_file_name)
    with open(path, 'w') as f:
        for d_index in range(num_learn, len(df_input)):
            text = '%s\t%s\n' % (df_input.iloc[d_index]['Tag'], df_input.iloc[d_index]['word'])
            f.write(text.encode('utf-8'))

    return learn_file_name, test_file_name


def learn_model(file_name):
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
        # 拆分学习组和测试组 3 ：2
        len_learn = len(df) / 5 * 3
        # 生成学习文档和测试文档
        learn_file_name, test_file_name = output_file(df, len_learn)
        tmp_learn_name = os.path.join(BASE_DIR, 'learn', 'model_' + learn_file_name)
        grocery = Grocery(tmp_learn_name)
        path = os.path.join(BASE_DIR, 'learn', learn_file_name)
        grocery.train(path)
        grocery.save()
    except Exception as e:
        return {'IsErr': True, 'ErrDesc': u'学习不成功，没有生产新的模型，请再次尝试。'}

    # 测试
    res = test_sample(tmp_learn_name, test_file_name)

    return {'IsErr': False, 'ErrDesc': u'成功生产新的模型，测试验证的正确率为%s, 模型保存为:%s' % (
        res, os.path.split(tmp_learn_name)[1])}


def test_sample(path, test_path):
    new_grocery = Grocery(path)
    new_grocery.load()
    test_path = os.path.join(BASE_DIR, 'learn', test_path)
    res = new_grocery.test(test_path.encode('utf-8'))
    return str(res)


def predict_test(model_path, data):
    # 加载模型
    try:
        model_path = os.path.join(BASE_DIR, 'learn', model_path)
        new_grocery = Grocery(model_path)
        new_grocery.load()
    except Exception as e:
        return {'IsErr': True, 'ErrDesc': u'学习模型加载不成功，请检查路径'}
    # 整理输入数据
    result = list()
    sentences = data.split(';')
    if sentences[-1] == '':
        sentences.pop()
    if len(sentences) == 0:
        return {'IsErr': True, 'ErrDesc': u'输入的句子结构有错误或没有数据'}

    # 分词，再判断
    stop_words = read_lines(os.path.join(BASE_DIR, 'learn', 's_w.txt'))
    for s in sentences:
        tmp_s = ''
        words = jieba.cut(s)
        for word in words:
            if word in stop_words:
                continue
            else:
                tmp_s += word + ' '
        result.append({
            'tag': str(new_grocery.predict(tmp_s.strip().encode('utf-8'))),
            'sentence': s,
        })
    return {'IsErr': False, 'ErrDesc': u'成功', 'data': result}


if __name__ == '__main__':
    print learn_model('learn_01.xls')

