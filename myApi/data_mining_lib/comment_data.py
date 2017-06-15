# encoding=utf8
import json
import pandas as pd
import pymssql
from myApi import my_settings
from collections import defaultdict
import sys
reload(sys)
sys.setdefaultencoding("utf-8")


def init_sql():
    conn = pymssql.connect(
        host=my_settings.HOST,
        user=my_settings.HOST_USER,
        password=my_settings.HOST_PASSWORD,
        database=my_settings.DB,
    )
    return conn


def load_data(id_list, begin_date, end_date):
    # 整理数据
    conn = init_sql()
    sql_text = "SELECT * FROM T_DCR_Comment (nolock) " \
               "WHERE TreasureID in %s and RateDate > '%s' and RateDate < '%s';" % (str(id_list), begin_date, end_date)
    return pd.io.sql.read_sql(sql_text, con=conn)


def load_data_with_word(id_list, begin_date, end_date, word):
    # 整理数据
    conn = init_sql()
    sql_text = """SELECT * FROM T_DCR_Comment (nolock) WHERE TreasureID in %s and RateDate > '%s' and RateDate < '%s' and %s;""" %\
               (str(id_list), begin_date, end_date, word)
    return pd.io.sql.read_sql(sql_text, con=conn)


def static_word(data, result):
    if 'a' in data.keys():
        for word in data['a']:
            result['adj'][word] += 1
    if 'v' in data.keys():
        for word in data['v']:
            result['verb'][word] += 1
    if 'n' in data.keys():
        for word in data['n']:
            result['noun'][word] += 1
    return result


def main_process(data):
    try:
        data = json.loads(data)
        for t_id in range(0, len(data['treasure_ids'])):
            data['treasure_ids'][t_id] = str(data['treasure_ids'][t_id])
        if len(data['treasure_ids']) == 1:
            data['treasure_ids'].append('')
        treasure_ids = tuple(data['treasure_ids'])
        begin_date = data['begin_date']
        end_date = data['end_date']
        # 整理包含字符查询
        sql_word = None
        if data.has_key('and_word'):
            tmp_list = list()
            for word in data['and_word']:
                tmp_list.append("CHARINDEX('%s', RateContent)>0" % word)
            sql_word = ' and '.join(tmp_list)

        if data.has_key('or_word'):
            tmp_list = list()
            for word in data['or_word']:
                tmp_list.append("CHARINDEX('%s', RateContent)>0" % word)
            if sql_word:
                sql_word = '(%s and ( %s))' % (sql_word, ' or '.join(tmp_list))
            else:
                sql_word = '(%s)' % ' or '.join(tmp_list)

        # 包含Tag标签查询
        if data.has_key('tag'):
            tmp_list = list()
            for tag in data['tag']:
                tmp_list.append("CHARINDEX('%s', Tag)>0" % tag)

            if sql_word:
                sql_word = '%s and (%s)' % (sql_word, ' or '.join(tmp_list))
            else:
                sql_word = '(%s)' % ' or '.join(tmp_list)

        if sql_word:
            df = load_data_with_word(treasure_ids, begin_date, end_date, sql_word)
        else:
            df = load_data(treasure_ids, begin_date, end_date)
    except Exception as e:
        return {'IsErr': True, 'ErrDesc': u'数据格式错误', 'data': ''}

    if len(df) == 0:
        return {'IsErr': True, 'ErrDesc': u'没有找到相应的评论', 'data': ''}

    result = {}
    for record_data in range(0, len(df)):
        tmp_data = json.loads(df.iloc[record_data]['RateContent'])
        # 记录结果
        # TODO:多标签的分类
        if df.iloc[record_data]['Tag'] in result.keys():
            result[df.iloc[record_data]['Tag']].update(static_word(tmp_data, result[df.iloc[record_data]['Tag']]))
            result[df.iloc[record_data]['Tag']]['motivation'].append(df.iloc[record_data]['Level'])
        else:
            result[df.iloc[record_data]['Tag']] = {
                'adj': defaultdict(lambda: 0),
                'verb': defaultdict(lambda: 0),
                'noun': defaultdict(lambda: 0),
                'motivation': list(),
            }
            result[df.iloc[record_data]['Tag']].update(static_word(tmp_data, result[df.iloc[record_data]['Tag']]))
            result[df.iloc[record_data]['Tag']]['motivation'].append(df.iloc[record_data]['Level'])

    # 排序
    for level in result.keys():
        for character in result[level].keys():
            if character != 'motivation':
                result[level][character] = sorted(result[level][character].items(), key=lambda d: d[1], reverse=True)

    return {'IsErr': False, 'ErrDesc': u'成功操作', 'data': result}

