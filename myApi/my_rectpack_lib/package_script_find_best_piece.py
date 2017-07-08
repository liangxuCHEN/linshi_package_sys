# encoding=utf8
import sys
# sys.path.append("/home/django/linshi_package_sys/")
from datetime import datetime as dt
import json
import urllib2
from urllib import urlencode
import numpy as np
from package import PackerSolution
from myApi import my_settings
from myApi.tools import send_mail
from package_tools import multi_piece
from sql import Mssql, has_same_work, find_skucode, update_new_work, insert_work,\
    update_running_work, insert_same_data, get_data
from mrq.context import log

BEGIN_STATUS = u'新任务'
OK_STATUS = u'运算结束'
CALC_ERROR_STATUS = u'计算出错'
NO_NUM_STATUS = u'没有找到最佳数量'



def find_best_piece(shape_data, bin_data, border=5):

    rate_res = list()
    num_pic = 1
    best_pic = 1
    best_rate = 0
    best_rates = {}

    while True:
        # 创建分析对象
        packer = PackerSolution(
            shape_data,
            bin_data,
            border=border,
            num_pic=num_pic
        )
        if packer.is_valid():
            # 选择几种经常用的算法
            res = packer.find_solution(algo_list=[0, 4, 40, 8, 20, 44, 24])
            # 平均使用率
            total_rate = 0
            for data in res:
                total_rate += data['rate']
            tmp_avg_rate = total_rate / len(res)

            # 记录最大值
            if best_rate < tmp_avg_rate:
                best_rate = tmp_avg_rate
                best_pic = num_pic
                for data in res:
                    best_rates[data['bin_key']] = data['rate']

            if num_pic > my_settings.NUM_SAVE:
                rate_res.append(tmp_avg_rate)
                np_arr = np.array(rate_res[-1 * my_settings.NUM_SAVE:])
                var_rate = np_arr.var()
                if var_rate < my_settings.MAX_VAR_RATE:
                    # 少于阈值返回最佳值
                    return False, {'piece': best_pic, 'rates': best_rates}
            else:
                rate_res.append(tmp_avg_rate)

        else:
            return True, {'info': packer.error_info()}

        num_pic += 1


def http_post(num_piece, shape_data, bin_data, comment=None):
    """
    用于脚步访问自身网络，调用django的自身数据库
    :param num_piece:
    :param shape_data:
    :param bin_data:
    :param comment:
    :return:
    """
    url = my_settings.URL_POST
    # 整理input data
    s_data, b_data = multi_piece(num_piece, shape_data, bin_data)
    # 整理描述
    if comment:
        try:
            comment = json.loads(comment)
            comment['Amount'] = num_piece
            comment = json.dumps(comment, ensure_ascii=False)
        except:
            if type(comment) == type('string'):
                comment += ' 最优利用率推荐生产数量=%d' % num_piece
            else:
                comment = json.dumps(comment, ensure_ascii=False)
    else:
        comment = '最优利用率推荐生产数量=%d' % num_piece
    values = {
        'project_comment': comment.encode('utf8'),
        'border': 5,
        'shape_data': s_data,
        'bin_data': b_data
    }
    data = urlencode(values)
    req = urllib2.Request(url, data)  # 生成页面请求的完整数据
    response = None
    try:
        response = urllib2.urlopen(req)  # 发送页面请求
        result = json.loads(response.read())
    except urllib2.URLError as e:
        code = ''
        reason = ''
        if hasattr(e, 'code'):
            # log.error('there is error in http post,error code:%d' % e.code)
            code = e.code
        if hasattr(e, 'reason'):
            # log.error('there is error in http post,error reason:%s' % e.reason)
            reason = e.reason

        # 如果出错发送邮件通知
        body = '<p>运行 package_script_find_best_piece.py 出错，不能post到服务器生产具体方案</p>'
        body += '<p>http respose code:%s, reason: %s</p>' % (str(code), reason)
        send_mail_process(body)
    finally:
        if result:
            response.close()

    return result['url'], result['rates']


def send_mail_process(body):
    # 如果出错发送邮件通知
    mail_to = 'chenliangxu68@163.com'
    send_mail(mail_to, u"林氏利用率API邮件提醒", body)


def generate_work(input_data):
    """
    接受任务，存入数据库，（然后调出数据库里面需要执行的所有任务），马上执行
    :param input_data:
    :return:
    """
    # 更新日期
    created = dt.today()
    #log_g = log_init('save_works%s.log' % created.strftime('%Y_%m_%d'))
    log.info('Loading data ....')
    try:
        datas = json.loads(input_data['works'])
    except ValueError:
        log.error('can not decode json data ....')
        return {'ErrDesc': u'数据格式错误，不符合json格式', 'IsErr': True, 'data': ''}
    result = list()
    insert_list = list()
    update_list = list()
    log.info('connecting the DB ....')
    for data in datas:
        # 获取任务状态
        try:
            shape_data = json.dumps(data['ShapeData'], ensure_ascii=False)
            bin_data = json.dumps(data['BinData'], ensure_ascii=False)
            product_comment = json.dumps(data['Product'], ensure_ascii=False)
        except KeyError:
            log.error('missing some of data (ShapeData, BinData or Product comment) ....')
            return {'ErrDesc': u'数据中缺少 ShapeData 或者 BinData 的数据', 'IsErr': True, 'data': ''}
        res = has_same_work(shape_data, bin_data)
        # 已存相同的数据，返回任务状态和结果 0:BOMVersion, 1:Status, 2:Url 3:best num
        if res:
            # 如果BOMVersion相同，直接返回结果, BOMVersion不相同，如果状态是运算结束，写入详细结果
            # 如果不行就要重新计算
            if res[0][0] != data['BOMVersion']:
                if res[0][1] == OK_STATUS:
                    insert_same_data(res[0][0], res[0][2], data, shape_data, bin_data, product_comment, res[0][3])
                else:
                    # TODO;有相同数据计算在进行，等一下再查一下
                    insert_list.append({
                        'SkuCode': data['SkuCode'],
                        'Status': 0,
                        'ShapeData': shape_data,
                        'BinData': bin_data,
                        'Created': created,
                        'Product': product_comment,
                        'BOMVersion': data['BOMVersion']
                    })

            else:
                update_list.append({
                    'SkuCode': data['SkuCode'],
                    'Product': product_comment,
                    'BOMVersion': data['BOMVersion'],
                    'Update': created,
                })

            result.append({
                'BOMVersion': data['BOMVersion'],
                'Satuts': res[0][1],
                'Result': res[0][2],
            })

        else:
            # 新任务
            result.append({
                'BOMVersion': data['BOMVersion'],
                'Satuts': 0,
            })

            # 是否有相同的BOMVersion, 有就清除
            find_skucode(data['BOMVersion'])

            # 插入新数据
            insert_list.append({
                'SkuCode': data['SkuCode'],
                'Status': 0,
                'ShapeData': shape_data,
                'BinData': bin_data,
                'Created': created,
                'Product': product_comment,
                'BOMVersion': data['BOMVersion']
            })

    # update db
    log.info('saving the new works into DB ....')

    # 更新数据库
    if len(insert_list) > 0:
        insert_work(insert_list)
    if len(update_list) > 0:
        update_new_work(update_list)
    log.info('-------------finish and return the result----------------')
    return {'ErrDesc': u'操作成功', 'IsErr': False, 'data': result}


# def main_process():
#     end_day = dt.today()
#     log_main = log_init('find_best_piece%s.log' % end_day.strftime('%Y_%m_%d'))
#     log_main.info('connect to the DB and get the jobs....')
#     rows = get_data()
#     log_main.info('there are %d works today' % len(rows))
#
#     for input_data in rows:
#         # 更新另外的数据库,每得到结果更新一次
#         content_2 = {}
#         error, result = find_best_piece(input_data['ShapeData'], input_data['BinData'])
#         content_2['BOMVersion'] = input_data['BOMVersion']
#         content_2['Created'] = dt.today()
#         if error:
#             content_2['status'] = CALC_ERROR_STATUS
#             update_result(content_2)
#             log_main.error('work BOMVersion=%s has error in input data ' % input_data['BOMVersion'])
#             # 如果出错发送邮件通知
#             body = '<p>运行 package_script_find_best_piece.py 出错，输入数据有误</p>'
#             send_mail_process(body)
#         else:
#             log_main.info('finish work BOMVersion=%s, best piece is %d and begin to draw the solution' % (
#                 input_data['BOMVersion'], result['piece']))
#             # 访问API
#             http_response, rates = run_product_rate_func(result['piece'], input_data['ShapeData'],
#                                                          input_data['BinData'], comment=input_data['Product'])
#             result['url'] = my_settings.BASE_URL + http_response if http_response else 'no url'
#             content_2['status'] = OK_STATUS
#             content_2['url'] = result['url']
#             content_2['rates'] = list()
#
#             if content_2['status'] == OK_STATUS:
#                 for skucode, rate in rates.items():
#                     content_2['rates'].append((input_data['SkuCode'], content_2['BOMVersion'], skucode, rate))
#                 # 更新数据结果
#                 update_result(content_2)
#                 log_main.info('finish draw solution BOMVersion=%s' % input_data['BOMVersion'])
#             else:
#                 log_main.info('error in draw solution BOMVersion=%s' % input_data['BOMVersion'])
#
#     log_main.info('-------------------All works has done----------------------------')


# def get_work_and_calc(post_data, only_one=True):
#     """
#     收到任务请求
#     第一步（generate_work）：保存任务到数据库，然后通过比对，过虑重复任务，调用所有需要计算的任务
#     第二步：找出最佳生产数量，然后求这样的数量的板材排列
#     :param post_data:
#     :param only_one:
#     :return:
#     """
#     rows = None
#     if only_one:
#         result = generate_work(post_data)
#         if not result['IsErr']:
#             rows = get_data(bom_version=result['data'][0]['BOMVersion'])
#     else:
#         rows = get_data()
#
#     log.info('connect to the DB and get the data, there are %d works today' % len(rows))
#     # yield u'<p>一共有%d任务</p>' % len(rows)
#     # TODO：队列任务修改，每一个循环一个任务
#     if rows:
#         for input_data in rows:
#             # 更新另外的数据库,每得到结果更新一次
#             content_2 = {}
#             error, result = find_best_piece(input_data['ShapeData'], input_data['BinData'])
#             content_2['BOMVersion'] = input_data['BOMVersion']
#             content_2['SkuCode'] = input_data['SkuCode']
#             content_2['Created'] = dt.today()
#             if error:
#                 content_2['status'] = NO_NUM_STATUS
#                 update_result(content_2)
#                 log.error('work BOMVersion=%s has error in input data ' % input_data['BOMVersion'])
#                 # yield u'<p>运行出错，输入数据有误</p>'
#                 # 如果出错发送邮件通知
#                 body = '<p>运行 package_script_find_best_piece.py 出错，输入数据有误</p>'
#                 send_mail_process(body)
#             else:
#                 log.info('finish work BOMVersion=%s, best piece is %d and begin to draw the solution' % (
#                     input_data['BOMVersion'], result['piece']))
#                 content_2['best_num'] = result['piece']
#                 # TODO:换成函数
#                 try:
#                     http_response, rates, status = run_product_rate_func(
#                         result['piece'], input_data['ShapeData'],
#                         input_data['BinData'], comment=input_data['Product'])
#                 except Exception as e:
#                     log.error(status)
#                     log.error(e)
#                     content_2['status'] = u'生产项目详细页面出错'
#                     update_result(content_2)
#                     yield u'<p>计算BOMVersion:%s 出错</p>' % input_data['BOMVersion']
#                     continue
#
#                 result['url'] = my_settings.BASE_URL + http_response if http_response else 'no url'
#                 content_2['status'] = status
#                 content_2['url'] = result['url']
#                 content_2['rates'] = list()
#                 if content_2['status'] == OK_STATUS:
#                     for skucode, rate in rates.items():
#                         content_2['rates'].append((input_data['SkuCode'], content_2['BOMVersion'], skucode, rate))
#
#                     # 更新数据结果
#                     update_result(content_2)
#                     log.info('finish draw solution BOMVersion=%s' % input_data['BOMVersion'])
#                     # yield u'<p>计算BOMVersion:%s 结束，更新数据</p>' % input_data['BOMVersion']
#                 else:
#                     log.info('error in draw solution BOMVersion=%s' % input_data['BOMVersion'])
#                     # yield u'<p>BOMVersion=%s 画图出错, %s</p>' % (input_data['BOMVersion'], content_2['status'])
#
#         log.info('-------------------All works has done----------------------------')



