# encoding=utf8
import json
import pandas as pd
import pymssql
from myApi import my_settings
from collections import defaultdict


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
        treasure_ids = tuple(data['treasure_ids'])
        begin_date = data['begin_date']
        end_date = data['end_date']
        df = load_data(treasure_ids, begin_date, end_date)
    except Exception as e:
        return {'IsErr': True, 'ErrDesc': u'数据格式错误', 'data': ''}

    if len(df) == 0:
        return {'IsErr': True, 'ErrDesc': u'没有找到相应的评论', 'data': ''}
    result = {
        'positive': {
            'adj': defaultdict(lambda: 0),
            'verb': defaultdict(lambda: 0),
            'noun': defaultdict(lambda: 0),
        },
        'neutral': {
            'adj': defaultdict(lambda: 0),
            'verb': defaultdict(lambda: 0),
            'noun': defaultdict(lambda: 0),
        },
        'negative': {
            'adj': defaultdict(lambda: 0),
            'verb': defaultdict(lambda: 0),
            'noun': defaultdict(lambda: 0),
        }
    }
    for record_data in range(0, len(df)):
        tmp_data = json.loads(df.iloc[record_data]['RateContent'])
        # 记录结果
        if df.iloc[record_data]['Level'] > 0.2:
            result['positive'].update(static_word(tmp_data, result['positive']))
        elif df.iloc[record_data]['Level'] > 0.1:
            result['neutral'].update(static_word(tmp_data, result['neutral']))
        else:
            result['negative'].update(static_word(tmp_data, result['negative']))
    # 排序
    for level in result.keys():
        for character in result[level].keys():
            result[level][character] = sorted(result[level][character].items(), key=lambda d: d[1], reverse=True)

    return {'IsErr': False, 'ErrDesc': u'成功操作', 'data': result}

