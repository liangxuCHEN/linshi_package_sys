# encoding=utf8
import json
import numpy as np

from matplotlib.backends.backend_agg import FigureCanvasAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as patches
from datetime import datetime as dt

from package import PackerSolution
import single_use_rate
from base_tools import draw_one_pic, use_rate, find_the_same_position, log_init
from sql import update_mix_status, update_mix_status_time, insert_mix_status, Mssql

from mrq.context import log


EMPTY_BORDER = 5
SIDE_CUT = 10  # 板材的切边宽带
EFFECTIVE_RATE = 0.5  # 余料的有效率
NUM_SAVE = 5
MAX_VAR_RATE = 0.0001   # produce env  MAX_VAR_RATE = 0.00001


def empty_ares(empty_section):
    """
    求余料面积总和
    :param empty_section:
    :return:
    """
    total_ares = 0
    for empty_place in empty_section:
        total_ares += empty_place[2] * empty_place[3]
    return total_ares


def draw_many_pics(positions, width, height, path, border=0):
    """
    现在没有使用
    :param positions:
    :param width:
    :param height:
    :param path:
    :param border:
    :return:
    """
    i_p = 0
    for position in positions:
        fig1 = Figure(figsize=(12, 6))
        FigureCanvas(fig1)
        ax1 = fig1.add_subplot(111)
        output_obj = list()
        for v in position:
            output_obj.append(patches.Rectangle((v[0], v[1]), v[2], v[3], edgecolor='m', facecolor='blue', lw=border))

        for p in output_obj:
            ax1.add_patch(p)
        ax1.set_xlim(0, width)
        ax1.set_ylim(0, height)
        fig1.savefig('%s_pic%d.png' % (path, i_p), dpi=200)
        i_p += 1


def can_merge_place(place_v1, place_v2):
    """
    判断两个空间是否能合并
    :param place_v1:
    :param place_v2:
    :return:
    可以合并，返回True 和 合并的新空间
    不可以，返回False 和 None
    现在没有使用
    """
    if place_v1[0] == place_v2[0] and place_v1[2] == place_v2[2] and (
                    place_v1[1] == place_v2[3] or place_v1[3] == place_v2[1]):
        if place_v1[3] > place_v2[3]:
            return True, (place_v2[0], place_v2[1], place_v2[2], place_v1[3])
        else:
            return True, (place_v2[0], place_v1[1], place_v2[2], place_v2[3])
    if place_v1[1] == place_v2[1] and place_v1[3] == place_v2[3] and (
                    place_v1[0] == place_v2[2] or place_v1[2] == place_v2[0]):
        if place_v1[2] > place_v2[2]:
            return True, (place_v2[0], place_v2[1], place_v1[2], place_v2[3])
        else:
            return True, (place_v1[0], place_v2[1], place_v2[2], place_v2[3])
    return False, None


def tidy_shape(shapes, shapes_num, texture, vertical):
    """
    默认是竖直放置, shape_x 是 宽 ， shape_y 是 长, 由大到小排序
    当有纹理并且是竖直摆放的时候，要选择矩形
    现在没有使用
    :param shapes: 记录各矩形的长宽
    :param shapes_num:  记录矩形的数量
    :param texture:  是否有纹理，0：没有，1：有
    :param vertical: 摆放方式，当有纹理的时候有用，0:水平摆放，1:竖直摆放
    :return:
    """
    tmp_list = list()
    if texture == 1 and vertical == 0:
        # 这里是水平放置
        for shape in shapes:
            shape_x = shape[0]
            shape_y = shape[1]
            if shape_x < shape_y:
                shape_x, shape_y = shape_y, shape_x
            tmp_list.append((shape_x, shape_y))
    else:
        for shape in shapes:
            shape_x = shape[0]
            shape_y = shape[1]
            if shape_x > shape_y:
                shape_x, shape_y = shape_y, shape_x
            tmp_list.append((shape_x, shape_y))

    # 结合数量，合并成一个新的队列
    index_shape = 0
    new_list = list()
    for shape in tmp_list:
        for num in range(0, shapes_num[index_shape]):
            new_list.append(shape)
        index_shape += 1
    return new_list, tmp_list, shapes_num


def find_small_shape(shape_list):
    """
    现在没有使用
    :param shape_list:
    :return:
    """
    min_size = shape_list[0][0] * shape_list[0][1]

    for j in range(1, len(shape_list)):
        # 找最小面积
        if shape_list[j][0] * shape_list[j][1] < min_size:
            min_size = shape_list[j][0] * shape_list[j][1]
            min_shape = shape_list[j]

    return min_shape


def write_desc_doc(shapes, shapes_num, path, width, height, positions, num_list, rates, avg_rate, empty_positions):
    """
    描述这个方案的整体结果的文档, 现在没有使用
    """
    with open('%s_desc.txt' % path, 'w') as f:
        f.write('# : %d x %d  Qty: %d  Rate: %s \n' % (width, height, len(positions), str(avg_rate)))
        for i_shape in range(0, len(shapes)):
            f.write('%d : %d x %d  Qty: %d \n' % (i_shape, shapes[i_shape][0], shapes[i_shape][1], shapes_num[i_shape]))
        f.write('------------- \n')
        f.write('Detail: \n')
        f.write('------------- \n')
        f.write('#  Rate  Qty  \n')
        i_pic = 0
        for i_p in range(0, len(positions)):
            if num_list[i_p] != 0:
                f.write('B%d  %s  %d \n' % (i_pic, str(rates[i_p]), num_list[i_p]))
                i_pic += 1
                # TODO: 组件在每个板材的位置和数量
        f.write('------------- \n')
        f.write('Empty place: \n')
        f.write('------------- \n')
        i_place = 0
        for em_places in empty_positions:
            for em_place in em_places:
                f.write('E%d %d x %d \n' % (i_place, em_place[2], em_place[3]))
                i_place += 1


def detail_text(shape_list, situation_list, num_list):
    result = list()

    for shape in shape_list:
        data_dict = {}
        data_dict['width'] = str(shape[0])
        data_dict['height'] = str(shape[1])
        data_dict['num_list'] = list()
        id_situation = 0
        for situation in situation_list:
            if num_list[id_situation] != 0:
                # 统计每块板有多少个shape一样的图形
                count = 0
                for position in situation:
                    if shape == (position[2], position[3]) or shape == (position[3], position[2]):
                        count += 1

                data_dict['num_list'].append(count)
            id_situation += 1

        result.append(data_dict)

    return json.dumps(result)


def detail_empty_sections(empty_sections, shape_list, border, is_texture, is_vertical):
    # 求余料的组件利用情况
    counts = {}
    for e_places in empty_sections:
        for e_p in e_places:
            max_l = max(e_p[2], e_p[3])
            min_l = min(e_p[2], e_p[3])

            c_id = "%sx%s" % ([str(max_l), int(max_l)][int(max_l) == max_l],
                              [str(min_l), int(min_l)][int(min_l) == min_l])
            if c_id in counts.keys():
                counts[c_id]['num'] += 1
            else:
                # 每块余料看可以放哪些单品
                package_list = list()
                for shape in shape_list:
                    if max(shape[0], shape[1]) < max_l and min(shape[0], shape[1]) < min_l:
                        tmp_data = {
                            'shape_x': shape[0],
                            'shape_y': shape[1],
                            'width': max_l - EMPTY_BORDER,
                            'height': min_l - EMPTY_BORDER,
                            'border': border,
                            'is_texture': is_texture,
                            'is_vertical': is_vertical,
                        }
                        tmp_res = single_use_rate.main_process(tmp_data, None, EMPTY_BORDER)
                        if not tmp_res['error']:
                            package_list.append({
                                'amount': tmp_res['amount'],
                                'rate': tmp_res['rate']
                            })
                    else:
                        package_list.append({
                            'amount': 0,
                            'rate': 0
                        })

                counts[c_id] = {
                    'num': 1,
                    'ares': e_p[2] * e_p[3],
                    'shape_package': package_list
                }
    result = list()
    for key, value in counts.items():
        value['name'] = key
        result.append(value)
    return json.dumps(result)


def package_main_function(input_data, pathname):
    bins_num = None
    min_size = None
    min_height = None
    min_width = None
    cut_linear_p = 30  # 切割线重要系数
    empty_section_p = 70  # 余料重要系数
    if 'bins_num' in input_data.keys():
        if input_data['bins_num'] != '':
            bins_num = input_data['bins_num']
            min_size = int(input_data['min_size'])
            min_height = int(input_data['min_height'])
            min_width = int(input_data['min_width'])

    if 'use_rate_p' in input_data.keys():
        cut_linear_p = int(input_data['cut_linear_p'])
        empty_section_p = int(input_data['empty_section_p'])

    if 'effective_rate' in input_data.keys():
        effective_rate = float(input_data['empty_section_p'])
    else:
        effective_rate = EFFECTIVE_RATE

    # 创建分析对象
    packer = PackerSolution(
        input_data['shape_data'],
        input_data['bin_data'],
        border=int(input_data['border']),
        bins_num=bins_num,
        empty_section_min_size=min_size,
        empty_section_min_height=min_height,
        empty_section_min_width=min_width,
        cut_linear_p=cut_linear_p,
        empty_section_p=empty_section_p
    )

    algo_list = None
    if 'algo_list' in input_data.keys():
        algo_list = [int(x) for x in input_data.getlist('algo_list')]

    # 若数据没有错，返回结果
    if packer.is_valid():
        res = packer.find_solution(algo_list=algo_list)
        statistics_data = []  # 汇总报告
        for data in res:
            best_solution = data['solution']
            empty_sections = data['empty_sections']
            bins_list = data['bins_list']
            shape_list = packer.get_bin_data(data['bin_key'], key='shape_list')
            shape_num = packer.get_bin_data(data['bin_key'], key='shape_num')
            name = packer.get_bin_data(data['bin_key'], key='name')

            # 计算总利用率 = 余料使用率/2 + 组件利用率 ，余料面积的1/2 有效余料
            rate_list = list()  # 组件使用率
            total_rate_list = list()  # 总利用率
            empty_ares_list = list()  # 余料面积
            for s_id in range(0, len(best_solution)):
                r = use_rate(best_solution[s_id], bins_list[s_id][0], bins_list[s_id][1])
                empty_r = use_rate(empty_sections[s_id], bins_list[s_id][0], bins_list[s_id][1])
                rate_list.append(r)
                total_rate_list.append(float("%0.4f" % (empty_r * effective_rate + r)))
                # 余料总面积
                empty_ares_list.append(empty_ares(empty_sections[s_id]))

            title = 'average rate: %s' % str(data['rate'])
            # 返回唯一的排版列表，以及数量
            same_bin_list = find_the_same_position(best_solution)

            draw_one_pic(best_solution, rate_list, bins_list=bins_list,
                         path=pathname + data['bin_key'], border=1, num_list=same_bin_list, title=title,
                         shapes=shape_list, empty_positions=data['empty_sections'])

            # 保存统计信息
            statistics_data.append({
                'error': False,
                'rate': data['rate'],
                'num_sheet': len(best_solution),
                'detail': detail_text(shape_list, best_solution, same_bin_list),
                'num_shape': str(shape_num)[1:-1],
                'same_bin_list': str(same_bin_list)[1:-1],
                'sheet_num_shape': str([len(s) for s in best_solution])[1:-1],
                'rates': str(rate_list)[1:-1],
                'sheet': name,
                'name': data['bin_key'] + ' ' + name + u' 切割线(mm):%s' % str(data['cut_linear']),
                'bin_type': data['bin_key'],
                'pic_url': pathname + data['bin_key'] + '.png',
                'empty_sections': detail_empty_sections(
                    empty_sections,
                    shape_list,
                    packer.get_border(),
                    packer.get_bin_data(data['bin_key'], key='is_texture'),
                    packer.get_bin_data(data['bin_key'], key='is_vertical')
                ),
                'algo_id': data['algo_id'],
                'total_rates': str(total_rate_list)[1:-1],
                'empty_section_ares': str(empty_ares_list)[1:-1],
            })
        # 返回结果
        return {'statistics_data': statistics_data, 'error': False}
    else:
        # 有错误，返回错误信息
        return {'error': True, 'info': packer.error_info()}


def find_best_piece(input_data):
    # 保存之前的五个结果，求方差
    rate_res = list()
    num_pic = 1
    best_pic = 1
    best_rate = 0
    best_rates = None
    while True:
        # 创建分析对象
        packer = PackerSolution(
            input_data['shape_data'],
            input_data['bin_data'],
            border=int(input_data['border']),
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
                best_rates = [(data['bin_key'], data['rate']) for data in res]

            if num_pic > NUM_SAVE:
                rate_res.append(tmp_avg_rate)
                np_arr = np.array(rate_res[-1 * NUM_SAVE:])
                var_rate = np_arr.var()
                if var_rate < MAX_VAR_RATE:
                    # 少于阈值返回最佳值
                    return {
                        'error': False,
                        'piece': best_pic,
                        'rates': best_rates
                    }
            else:
                rate_res.append(tmp_avg_rate)

        else:
            return {'error': True, 'info': packer.error_info()}

        num_pic += 1


def package_data_check(input_data):
    # 数据库连接-检查数据库
    try:
        parm = {
            'comment': input_data['project_comment'],
            'shape_data': input_data['shape_data'],
            'bin_data': input_data['bin_data'],
        }

        other = json.dumps({
            'border': input_data['border']
        })
        user = input_data['userName']
    except Exception as e:
        update_mix_status(status=u'缺少参数')
        return {'error': True, 'info': u'缺少参数'}
    # 是否有重复
    conn = Mssql()
    sql_text = """SELECT Guid, CreateUser FROM T_BOM_PlateUtilMixedState WHERE
    Comment='{comment}' and  ShapeData='{shape_data}' and BinData='{bin_data}' and Paramets='{other}'""".format(
        comment=parm['comment'], shape_data=parm['shape_data'],
        bin_data=parm['bin_data'], other=other)
    log.info(sql_text)
    res = conn.exec_query(sql_text)
    row_id = None
    if len(res) > 0:
        has_same_user = False
        user_guid = None
        for row_data in res:
            if row_data[1] == user:
                has_same_user = True
                user_guid = row_data[0]
                break

        if has_same_user:
            # 更新-更新时间,不返回guid
            update_mix_status_time(user_guid)
        else:
            # 新任务
            row_id = insert_mix_status(parm, user, other)
    else:
        # 新任务
        row_id = insert_mix_status(parm, user, other)

    return {'error': False, 'row_id': row_id}


def run_product_rate_task(input_data, guid, path):
    created = dt.today()
    # log_run = log_init('mix_rate%s.log' % created.strftime('%Y_%m_%d'))
    log.info('read the db...')
    update_mix_status(guid=guid, status=u'计算中')
    # yield '<p>Working on the job guid=%s </p>' % guid
    log.info('Working on the job guid=%s ' % guid)

    # file_name = str(time.time()).split('.')[0]
    # path = os.path.join(settings.BASE_DIR, 'static')
    # path = os.path.join(path, file_name)
    results = package_main_function(input_data, path)
    if results['error']:
        log.info('has some error during the work')
        # yield '<p>has some error during the work</p>'
        update_mix_status(guid=guid, status=results['info'])
        return results
    else:
        return results
        #try:
            #log.info('create a project...')
            # yield '<p>create a project...</p>'
            # post url
            # project_id = create_project(results, input_data, file_name)
            # log.info('project save ..')
            # yield '<p>project save ...</p>'
            # url_res = my_settings.BASE_URL + 'project_detail/' + str(project_id)
            # 更新数据库
            # update_mix_status_result(guid, url_res)
            # yield '<p>finish the job...</p>'
        #except:
            #log_run.info('can not create a project...')
            #yield '<p>can not create a project...</p>'
            #update_mix_status(guid=guid, status=u'保存结果出错')


# TODO：改成Http post
# def create_project(results, post_data, filename):
#     # save project
#     project = Project(
#         comment=post_data['project_comment'],
#         data_input=post_data['shape_data'] + post_data['bin_data']
#     )
#     project.save()
#     # save product
#     for res in results['statistics_data']:
#         product = ProductRateDetail(
#             sheet_name=res['name'],
#             num_sheet=res['num_sheet'],
#             avg_rate=res['rate'],
#             rates=res['rates'],
#             detail=res['detail'],
#             num_shape=res['num_shape'],
#             sheet_num_shape=res['sheet_num_shape'],
#             pic_url='static/%s%s.png' % (filename, res['bin_type']),
#             same_bin_list=res['same_bin_list'],
#             empty_sections=res['empty_sections'],
#             algorithm=res['algo_id'],
#             empty_section_ares=res['empty_section_ares'],
#             total_rates=res['total_rates']
#         )
#         product.save()
#         project.products.add(product)
#     project.save()
#     return project.id


def multi_piece(num_piece, shape_data, bin_data):
    shape_data = shape_data.encode('utf-8')
    bin_data = bin_data.encode('utf-8')
    shape_data = json.loads(shape_data)
    for shape in shape_data:
        shape['Amount'] = shape['Amount'] * num_piece
    shape_data = json.dumps(shape_data)
    return shape_data, bin_data




# def http_post_test(num_piece, shape_data, bin_data, comment=None):
#     url = my_settings.URL_PRO_TEST
#     # 整理input data
#     s_data, b_data = multi_piece(num_piece, shape_data, bin_data)
#     # 整理描述
#     if comment:
#         try:
#             comment = json.loads(comment)
#             comment['Amount'] = num_piece
#             comment = json.dumps(comment, ensure_ascii=False)
#         except:
#             if type(comment) == type('string'):
#                 comment += ' 最优利用率推荐生产数量=%d' % num_piece
#             else:
#                 comment = json.dumps(comment, ensure_ascii=False)
#     else:
#         comment = '最优利用率推荐生产数量=%d' % num_piece
#     values = {
#         'project_comment': comment.encode('utf8'),
#         'border': 5,
#         'shape_data': s_data,
#         'bin_data': b_data,
#         'userName': 'Test'
#     }
#     data = urlencode(values)
#     req = urllib2.Request(url, data)  # 生成页面请求的完整数据
#     try:
#         response = urllib2.urlopen(req)  # 发送页面请求
#         text = response.read()
#     except urllib2.URLError as e:
#         pass

if __name__ == '__main__':
    pass


